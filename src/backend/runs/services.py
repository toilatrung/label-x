"""Domain services for QC Run lifecycle, sharding, and idempotency (T-024, E-08)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from audit.services import append_audit_event
from engines.duplicate_overlap import (
    DUPLICATE_OVERLAP_DESCRIPTOR,
    DUPLICATE_OVERLAP_ENGINE_NAME,
)
from engines.geometry import GEOMETRY_DESCRIPTOR, GEOMETRY_ENGINE_NAME
from engines.interface import EngineDescriptor, EngineStatus, NotCheckedReason
from engines.schema_taxonomy import SCHEMA_TAXONOMY_DESCRIPTOR, SCHEMA_TAXONOMY_ENGINE_NAME
from runs.models import ConfigVersion, EngineResult, ModelArtifact, QCRun, WorkUnit
from snapshots.models import Snapshot


class RunDomainError(Exception):
    """Base exception for QC Run domain errors."""


class SnapshotNotFoundError(RunDomainError):
    """Raised when the specified snapshot does not exist."""


class ConfigVersionNotFoundError(RunDomainError):
    """Raised when the specified config version does not exist."""


class BusinessRuleUnmetError(RunDomainError):
    """Raised when business prerequisites are not met (HTTP 422)."""


class InvalidTransitionError(RunDomainError):
    """Raised when state machine transition is illegal (HTTP 409)."""


class IdempotencyKeyReusedError(RunDomainError):
    """Raised when an Idempotency-Key is reused with differing payload (HTTP 409)."""


class ScopeBusyError(RunDomainError):
    """Raised when another final run is already active on the same scope (HTTP 409)."""


KNOWN_ENGINE_DESCRIPTORS: dict[str, EngineDescriptor] = {
    DUPLICATE_OVERLAP_ENGINE_NAME: DUPLICATE_OVERLAP_DESCRIPTOR,
    SCHEMA_TAXONOMY_ENGINE_NAME: SCHEMA_TAXONOMY_DESCRIPTOR,
    GEOMETRY_ENGINE_NAME: GEOMETRY_DESCRIPTOR,
    "detector": EngineDescriptor(
        name="detector",
        version="1.0.0",
        unit="frame",
        required=True,
        needs_model=True,
        needs_reference=False,
        applicability_version="1.0.0",
    ),
    "metric": EngineDescriptor(
        name="metric",
        version="1.0.0",
        unit="frame",
        required=False,
        needs_model=False,
        needs_reference=False,
        applicability_version="1.0.0",
    ),
    "vlm": EngineDescriptor(
        name="vlm",
        version="1.0.0",
        unit="frame",
        required=False,
        needs_model=True,
        needs_reference=False,
        applicability_version="1.0.0",
    ),
}


def _enqueue_run_after_commit(run_id: int) -> None:
    """Xếp shard của run vào Celery sau commit (T-025); tắt bằng ORCHESTRATION_AUTO_DISPATCH."""
    if not getattr(settings, "ORCHESTRATION_AUTO_DISPATCH", True):
        return

    def _dispatch() -> None:
        from orchestration.dispatch import dispatch_run

        dispatch_run(run_id)

    transaction.on_commit(_dispatch)


def compute_shard_idempotency_key(
    *,
    snapshot_id: int,
    engine: str,
    engine_version: str,
    config_version_id: int,
    model_checksum: str | None,
    shard_key: str,
) -> str:
    """Deterministic hash of shard execution provenance.

    Formula: sha256(snapshot_id ‖ engine ‖ engine_version ‖ config_version_id ‖
    model_checksum ‖ shard_key).
    Uses canonical JSON serialization (sorted keys, compact separators, UTF-8 encoded)
    to guarantee zero collision and order independence. Run ID is strictly excluded.
    """
    canonical_payload = {
        "config_version_id": int(config_version_id),
        "engine": str(engine),
        "engine_version": str(engine_version),
        "model_checksum": str(model_checksum) if model_checksum else "",
        "shard_key": str(shard_key),
        "snapshot_id": int(snapshot_id),
    }
    raw = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def canonical_request_hash(data: Mapping[str, Any]) -> str:
    """Canonical SHA-256 hash for HTTP request body idempotency verification."""
    clean_dict = {
        "config_version_id": int(data["config_version_id"]),
        "seed": int(data["seed"]),
        "snapshot_id": int(data["snapshot_id"]),
    }
    raw = json.dumps(clean_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def generate_shards_for_snapshot(
    snapshot: Snapshot,
    config_version: ConfigVersion,
    model_artifact: ModelArtifact | None,
) -> tuple[dict[str, str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Deterministically partition snapshot frames into engine shards.

    Returns:
        (engine_versions_map, work_units_data, engine_results_data)
    """
    config_payload = config_version.payload or {}
    config_engines = config_version.engines or config_payload.get("engines", {})
    shard_size = int(config_payload.get("shard_size", 100))

    enabled_engines: list[str] = []
    if config_engines:
        for eng_name, eng_cfg in config_engines.items():
            if isinstance(eng_cfg, dict) and eng_cfg.get("enabled", True):
                enabled_engines.append(eng_name)
            elif eng_cfg is True:
                enabled_engines.append(eng_name)
    else:
        # Default enabled engines if none specified
        enabled_engines = [DUPLICATE_OVERLAP_ENGINE_NAME, "schema", "geometry"]
        if model_artifact is not None:
            enabled_engines.append("detector")

    enabled_engines.sort()

    # Extract jobs and frames deterministically
    db_jobs = list(snapshot.jobs.order_by("cvat_job_id").prefetch_related("frames"))
    shard_slices: list[str] = []

    if db_jobs:
        for job in db_jobs:
            frames = list(job.frames.order_by("frame_index"))
            if frames:
                for i in range(0, len(frames), shard_size):
                    chunk = frames[i : i + shard_size]
                    shard_slices.append(
                        f"job:{job.cvat_job_id}:frames:{chunk[0].frame_index}-{chunk[-1].frame_index}"
                    )
            else:
                shard_slices.append(f"job:{job.cvat_job_id}:empty")
    else:
        # Check normalized_json fallback
        norm_jobs = (snapshot.normalized_json or {}).get("jobs", [])
        if norm_jobs:
            norm_jobs_sorted = sorted(norm_jobs, key=lambda j: int(j.get("cvat_job_id", 0)))
            for job_data in norm_jobs_sorted:
                job_id = int(job_data.get("cvat_job_id", 0))
                frames_data = sorted(
                    job_data.get("frames", []), key=lambda f: int(f.get("frame_index", 0))
                )
                if frames_data:
                    for i in range(0, len(frames_data), shard_size):
                        norm_chunk = frames_data[i : i + shard_size]
                        start_idx = norm_chunk[0].get("frame_index", 0)
                        end_idx = norm_chunk[-1].get("frame_index", 0)
                        shard_slices.append(f"job:{job_id}:frames:{start_idx}-{end_idx}")
                else:
                    shard_slices.append(f"job:{job_id}:empty")
        else:
            shard_slices.append(f"snapshot:{snapshot.pk}:default")

    shard_slices.sort()

    engine_versions_map: dict[str, str] = {}
    work_units_data: list[dict[str, Any]] = []
    engine_results_data: list[dict[str, Any]] = []

    model_checksum = model_artifact.checksum if model_artifact else None

    for engine_name in enabled_engines:
        descriptor = KNOWN_ENGINE_DESCRIPTORS.get(
            engine_name,
            EngineDescriptor(
                name=engine_name,
                version="1.0.0",
                unit="frame",
                required=True,
                needs_model=False,
                needs_reference=False,
                applicability_version="1.0.0",
            ),
        )
        engine_versions_map[engine_name] = descriptor.version

        if descriptor.needs_model and not model_checksum:
            engine_results_data.append(
                {
                    "engine": engine_name,
                    "status": EngineStatus.NOT_CHECKED,
                    "reason": NotCheckedReason.NO_MODEL,
                    "eligible_units": 0,
                    "completed_units": 0,
                    "failed_units": 0,
                    "not_checked_units": 0,
                    "required": descriptor.required,
                }
            )
            continue

        # Generate work units
        for shard_idx, shard_key in enumerate(shard_slices):
            idem_key = compute_shard_idempotency_key(
                snapshot_id=snapshot.pk,
                engine=engine_name,
                engine_version=descriptor.version,
                config_version_id=config_version.pk,
                model_checksum=model_checksum,
                shard_key=shard_key,
            )
            work_units_data.append(
                {
                    "engine": engine_name,
                    "shard_key": shard_key,
                    "shard_index": shard_idx,
                    "idempotency_key": idem_key,
                    "status": WorkUnit.Status.PENDING,
                    "attempt": 1,
                }
            )

        engine_results_data.append(
            {
                "engine": engine_name,
                "status": EngineStatus.RUNNING if shard_slices else EngineStatus.CHECKED,
                "reason": None,
                "eligible_units": len(shard_slices),
                "completed_units": 0,
                "failed_units": 0,
                "not_checked_units": 0,
                "required": descriptor.required,
            }
        )

    return engine_versions_map, work_units_data, engine_results_data


def create_qc_run(
    *,
    snapshot_id: int,
    config_version_id: int,
    seed: int,
    created_by: User,
    idempotency_key: str | None = None,
    is_final: bool = False,
    origin_run_id: int | None = None,
) -> tuple[QCRun, bool]:
    """Create a QC Run with deterministic sharding and dual idempotency guards.

    Returns:
        (qc_run, created_boolean)
    """
    request_dict = {
        "snapshot_id": snapshot_id,
        "config_version_id": config_version_id,
        "seed": seed,
    }
    req_sha256 = canonical_request_hash(request_dict)

    clean_key = (idempotency_key or "").strip()
    if clean_key:
        existing = QCRun.objects.filter(idempotency_key=clean_key).first()
        if existing is not None:
            if existing.request_sha256 == req_sha256:
                return existing, False
            raise IdempotencyKeyReusedError(
                f"Idempotency-Key '{clean_key}' đã được sử dụng với payload khác."
            )

    # Validate snapshot
    snapshot = Snapshot.objects.filter(pk=snapshot_id).first()
    if snapshot is None:
        raise SnapshotNotFoundError(f"Snapshot {snapshot_id} không tồn tại.")
    if snapshot.status != Snapshot.Status.LOCKED:
        raise BusinessRuleUnmetError(
            f"Snapshot {snapshot_id} chưa ở trạng thái locked (hiện tại: {snapshot.status})."
        )

    # Validate config version
    config_version = ConfigVersion.objects.filter(pk=config_version_id).first()
    if config_version is None:
        raise ConfigVersionNotFoundError(f"Config version {config_version_id} không tồn tại.")
    if config_version.status != ConfigVersion.Status.PUBLISHED:
        raise BusinessRuleUnmetError(
            f"Config version {config_version_id} chưa ở trạng thái published "
            f"(hiện tại: {config_version.status})."
        )

    model_artifact: ModelArtifact | None = None
    config_models = config_version.models or (config_version.payload or {}).get("models", {})
    if config_models:
        model_name = config_models.get("name")
        model_ver = config_models.get("version")
        if model_name and model_ver:
            model_artifact = ModelArtifact.objects.filter(
                name=model_name, version=model_ver
            ).first()

    dataset_id = snapshot.dataset_id
    scope_hash = (
        snapshot.revision_sha256 or hashlib.sha256(str(dataset_id).encode("utf-8")).hexdigest()
    )

    # Scope busy guard for active final runs
    if is_final:
        busy = QCRun.objects.filter(
            dataset_id=dataset_id,
            scope_hash=scope_hash,
            is_final=True,
            status__in=[QCRun.Status.QUEUED, QCRun.Status.RUNNING],
        ).exists()
        if busy:
            raise ScopeBusyError("Đang có run cuối khác đang chạy trên cùng phạm vi.")

    origin_run: QCRun | None = None
    if origin_run_id is not None:
        origin_run = QCRun.objects.filter(pk=origin_run_id).first()

    engine_versions_map, work_units_data, engine_results_data = generate_shards_for_snapshot(
        snapshot, config_version, model_artifact
    )

    try:
        with transaction.atomic():
            run = QCRun.objects.create(
                snapshot=snapshot,
                config_version=config_version,
                model_artifact=model_artifact,
                seed=seed,
                engine_versions=engine_versions_map,
                status=QCRun.Status.QUEUED,
                is_final=is_final,
                origin_run=origin_run,
                dataset_id=dataset_id,
                scope_hash=scope_hash,
                score_version="v1",
                created_by=created_by,
                idempotency_key=clean_key or None,
                request_sha256=req_sha256,
            )

            # Bulk create WorkUnits
            work_unit_objs = [WorkUnit(run=run, **wu) for wu in work_units_data]
            WorkUnit.objects.bulk_create(work_unit_objs)

            # Bulk create EngineResults
            engine_result_objs = [EngineResult(run=run, **er) for er in engine_results_data]
            EngineResult.objects.bulk_create(engine_result_objs)

            # Audit event inside same atomic transaction
            append_audit_event(
                actor=created_by,
                action="run.create",
                object_type="run",
                object_id=run.pk,
                before=None,
                after={
                    "snapshot_id": snapshot_id,
                    "config_version_id": config_version_id,
                    "seed": seed,
                    "status": run.status,
                    "is_final": is_final,
                    "work_units_count": len(work_unit_objs),
                },
                revision=str(run.pk),
            )
            _enqueue_run_after_commit(run.pk)
            return run, True

    except IntegrityError as exc:
        if clean_key:
            existing = QCRun.objects.filter(idempotency_key=clean_key).first()
            if existing is not None:
                if existing.request_sha256 == req_sha256:
                    return existing, False
                raise IdempotencyKeyReusedError(
                    f"Idempotency-Key '{clean_key}' đã được sử dụng với payload khác."
                ) from exc
        raise


def cancel_qc_run(*, run_id: int, actor: User, reason: str = "") -> QCRun:
    """Cancel a queued or running QC Run (state-machines §2). Idempotent if already cancelled."""
    with transaction.atomic():
        run = QCRun.objects.select_for_update().filter(pk=run_id).first()
        if run is None:
            raise RunDomainError(f"Run {run_id} không tồn tại.")

        if run.status == QCRun.Status.CANCELLED:
            return run  # Idempotent 200

        if run.status in (QCRun.Status.COMPLETED, QCRun.Status.PARTIAL, QCRun.Status.FAILED):
            raise InvalidTransitionError(
                f"Không thể huỷ run ở trạng thái terminal '{run.status}' "
                "(chỉ cho phép queued/running)."
            )

        old_status = run.status
        now = timezone.now()
        run.status = QCRun.Status.CANCELLED
        run.cancel_requested_at = now
        run.finished_at = now
        run.save(update_fields=["status", "cancel_requested_at", "finished_at"])

        # Cancel non-terminal work units
        run.work_units.filter(status__in=[WorkUnit.Status.PENDING, WorkUnit.Status.RUNNING]).update(
            status=WorkUnit.Status.CANCELLED, finished_at=now
        )

        append_audit_event(
            actor=actor,
            action="run.cancel",
            object_type="run",
            object_id=run.pk,
            before={"status": old_status},
            after={"status": run.status},
            revision=str(run.pk),
            reason=reason,
        )
        return run


def retry_failed_qc_run(*, run_id: int, actor: User) -> QCRun:
    """Requeue failed work units for a run in partial status (state-machines §2, FR-AGG-02)."""
    with transaction.atomic():
        run = QCRun.objects.select_for_update().filter(pk=run_id).first()
        if run is None:
            raise RunDomainError(f"Run {run_id} không tồn tại.")

        if run.status != QCRun.Status.PARTIAL:
            raise InvalidTransitionError(
                "Chỉ có thể retry-failed cho run ở trạng thái 'partial' "
                f"(hiện tại: '{run.status}')."
            )

        failed_units = list(run.work_units.filter(status=WorkUnit.Status.FAILED))
        for unit in failed_units:
            unit.status = WorkUnit.Status.PENDING
            unit.attempt += 1
            unit.started_at = None
            unit.finished_at = None
            unit.last_error = ""
            unit.save(
                update_fields=["status", "attempt", "started_at", "finished_at", "last_error"]
            )

        old_status = run.status
        run.status = QCRun.Status.RUNNING
        run.finished_at = None
        run.save(update_fields=["status", "finished_at"])

        # Update engine results
        run.engine_results.filter(status=EngineStatus.PARTIAL).update(status=EngineStatus.RUNNING)
        _enqueue_run_after_commit(run.pk)

        append_audit_event(
            actor=actor,
            action="run.retry_failed",
            object_type="run",
            object_id=run.pk,
            before={"status": old_status},
            after={"status": run.status, "requeued_units": len(failed_units)},
            revision=str(run.pk),
        )
        return run
