"""Stage classifier ConvNeXt Tiny phụ thuộc candidate (M04B-03).

Thứ tự: engine sinh candidate chạy xong -> `start_classifier_stage` tạo ClassifierUnit cho mỗi
candidate -> worker suy luận theo batch (tiến trình riêng, backend không import torch). Stage này
chạy sau candidate và trước quyết định gọi VLM (policy pha C đọc kết quả ở đây).

Kết quả là đề xuất của AI: `score` là softmax chưa calibrate, không phải xác suất đúng.
`classifier_unknown` luôn False ở đây; abstention theo ngưỡng thuộc policy định tuyến.
Không tạo ReviewDecision/Adjudication, không làm fail run (engine `classifier` không bắt buộc).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import uuid
from datetime import timedelta
from typing import Any

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from classifier.config import (
    CLASS_MAP_VERSION,
    CLASSES,
    CLASSIFIER_ENGINE,
    artifact_errors,
    classifier_enabled,
    validate_classifier_model_config,
)
from classifier.errors import ClassifierReason, ClassifierRunError
from classifier.runner import BatchResult, ClassifierRunner, CropItem, default_runner
from orchestration.models import CandidateRecord, ClassifierUnit
from orchestration.vlm_stage import _taxonomy_for_run, crop_provider
from runs.models import ModelArtifact, QCRun

logger = logging.getLogger("labelx.orchestration")

_OPEN = (ClassifierUnit.Status.PENDING, ClassifierUnit.Status.RUNNING)
_NON_CLASSIFIED_ENGINES = (CLASSIFIER_ENGINE, "vlm")


def _config_parts(run: QCRun) -> tuple[Any, Any]:
    cfg = run.config_version
    engines = cfg.engines or (cfg.payload or {}).get("engines", {})
    models_cfg = cfg.models or (cfg.payload or {}).get("models", {})
    return engines, models_cfg


def classifier_artifact(run: QCRun) -> ModelArtifact | None:
    """ModelArtifact đã sẵn sàng nếu engine classifier bật và config hợp lệ; ngược lại None."""
    engines, models_cfg = _config_parts(run)
    if not classifier_enabled(engines) or not isinstance(models_cfg, dict):
        return None
    raw = models_cfg.get(CLASSIFIER_ENGINE)
    if not isinstance(raw, dict) or validate_classifier_model_config(raw):
        return None
    artifact = ModelArtifact.objects.filter(pk=raw["model_artifact_id"]).first()
    if artifact is None or artifact_errors(artifact):
        return None
    return artifact


def compute_classifier_idempotency_key(
    *,
    candidate_dedup_key: str,
    crop_identity: str,
    snapshot_revision: str,
    checkpoint_sha256: str,
    class_map_version: str,
) -> str:
    payload = {
        "candidate": candidate_dedup_key,
        "checkpoint_sha256": checkpoint_sha256,
        "class_map_version": class_map_version,
        "crop_identity": crop_identity,
        "snapshot_revision": snapshot_revision,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _annotation_index(run: QCRun) -> dict[tuple[int, int, str], int]:
    """(cvat_task_id, frame_number, shape source id) -> label_id, từ snapshot đã khoá."""
    index: dict[tuple[int, int, str], int] = {}
    for job in (run.snapshot.normalized_json or {}).get("jobs", []):
        for frame in job.get("frames", []):
            for shape in frame.get("shapes", []):
                source = shape.get("source") or {}
                label_id = shape.get("label_id")
                if source.get("id") is not None and isinstance(label_id, int):
                    key = (job.get("cvat_task_id"), frame.get("frame_index"), str(source["id"]))
                    index[key] = label_id
    return index


def _annotated_class_id(
    candidate: CandidateRecord,
    index: dict[tuple[int, int, str], int],
    names: dict[int, str],
) -> int | None:
    """Lớp theo nhãn gốc của annotation; None nếu không truy ra hoặc ngoài class map."""
    objects = (candidate.anchor or {}).get("objects") or []
    for obj in objects:
        label_id = index.get((candidate.cvat_task_id, candidate.frame_number, str(obj.get("id"))))
        name = names.get(label_id) if label_id is not None else None
        if name and name.lower() in CLASSES:
            return CLASSES.index(name.lower())
    return None


def start_classifier_stage(run_id: int) -> int:
    """Khởi động/bổ sung stage classifier sau khi candidate đã sinh. Idempotent.

    Gọi trong transaction đã khoá QCRun (refresh_run). Dispatch Celery chạy sau commit.
    """
    run = QCRun.objects.select_related("config_version", "snapshot").get(pk=run_id)
    artifact = classifier_artifact(run)
    if artifact is None or run.cancel_requested_at:
        return 0
    provider = crop_provider()
    revision = run.snapshot.revision_sha256 or str(run.snapshot_id)
    index = _annotation_index(run)
    taxonomy = _taxonomy_for_run(run) or ()
    names = {
        int(label.class_id): label.class_name for label in taxonomy if label.class_id.isdigit()
    }
    candidates = CandidateRecord.objects.filter(run_id=run_id).exclude(
        engine__in=_NON_CLASSIFIED_ENGINES
    )
    existing = set(
        ClassifierUnit.objects.filter(run_id=run_id).values_list("candidate_id", flat=True)
    )
    new_units = []
    for candidate in candidates.order_by("pk"):
        if candidate.pk in existing:
            continue
        identity = provider.identity(candidate)
        new_units.append(
            ClassifierUnit(
                run_id=run_id,
                candidate=candidate,
                crop_identity=identity,
                annotated_class_id=_annotated_class_id(candidate, index, names),
                checkpoint_sha256=artifact.checksum,
                checkpoint_version=artifact.version,
                class_map_version=CLASS_MAP_VERSION,
                snapshot_revision=revision,
                idempotency_key=compute_classifier_idempotency_key(
                    candidate_dedup_key=candidate.dedup_key,
                    crop_identity=identity,
                    snapshot_revision=revision,
                    checkpoint_sha256=artifact.checksum,
                    class_map_version=CLASS_MAP_VERSION,
                ),
            )
        )
    created = ClassifierUnit.objects.bulk_create(new_units, ignore_conflicts=True)
    if ClassifierUnit.objects.filter(run_id=run_id, status=ClassifierUnit.Status.PENDING).exists():
        transaction.on_commit(lambda: dispatch_classifier_units_safely(run_id))
    return len(created)


def classifier_units_open(run_id: int) -> bool:
    return ClassifierUnit.objects.filter(run_id=run_id, status__in=_OPEN).exists()


def classifier_stage_started(run_id: int) -> bool:
    return ClassifierUnit.objects.filter(run_id=run_id).exists()


def dispatch_classifier_units(run_id: int, stale_after: float | None = None) -> int:
    run = QCRun.objects.get(pk=run_id)
    if run.cancel_requested_at or run.status not in (QCRun.Status.QUEUED, QCRun.Status.RUNNING):
        return 0
    pending = ClassifierUnit.objects.filter(run_id=run_id, status=ClassifierUnit.Status.PENDING)
    if stale_after is not None:
        cutoff = timezone.now() - timedelta(seconds=stale_after)
        pending = pending.filter(dispatched_at__isnull=True) | pending.filter(
            dispatched_at__lte=cutoff
        )
    if not pending.exists():
        return 0
    try:
        run_classifier_units_task.delay(run_id)
    except Exception:
        logger.exception("classifier dispatch failed", extra={"qc_run_id": run_id})
        return 0  # broker không với tới được: giữ PENDING cho sweeper
    pending.update(dispatched_at=timezone.now())
    return 1


def dispatch_classifier_units_safely(run_id: int, stale_after: float | None = None) -> int:
    try:
        return dispatch_classifier_units(run_id, stale_after)
    except Exception:
        logger.exception("classifier dispatch failed", extra={"qc_run_id": run_id})
        return 0


def _batch_size() -> int:
    return max(1, int(getattr(settings, "CLASSIFIER_BATCH_SIZE", 32)))


def _stale_seconds() -> float:
    return float(getattr(settings, "ORCHESTRATION_RUNNING_STALE_SECONDS", 1800))


def _claim_batch(run_id: int) -> tuple[list[ClassifierUnit], str]:
    """Nhận lease cho tối đa một batch; thứ tự khoá QCRun -> ClassifierUnit."""
    with transaction.atomic():
        run = QCRun.objects.select_for_update().get(pk=run_id)
        if run.cancel_requested_at or run.status not in (
            QCRun.Status.QUEUED,
            QCRun.Status.RUNNING,
        ):
            return [], ""
        now = timezone.now()
        stale = now - timedelta(seconds=_stale_seconds())
        units = list(
            ClassifierUnit.objects.select_for_update()
            .filter(run_id=run_id)
            .filter(status=ClassifierUnit.Status.PENDING)
            .order_by("pk")[: _batch_size()]
        )
        stale_running = list(
            ClassifierUnit.objects.select_for_update()
            .filter(run_id=run_id, status=ClassifierUnit.Status.RUNNING, started_at__lte=stale)
            .order_by("pk")[: max(0, _batch_size() - len(units))]
        )
        units += stale_running
        if not units:
            return [], ""
        token = uuid.uuid4().hex
        ClassifierUnit.objects.filter(pk__in=[u.pk for u in units]).update(
            status=ClassifierUnit.Status.RUNNING, started_at=now, lease_token=token
        )
        return units, token


def _settle(unit: ClassifierUnit, token: str, **fields: Any) -> bool:
    with transaction.atomic():
        QCRun.objects.select_for_update().only("id").get(pk=unit.run_id)
        return bool(
            ClassifierUnit.objects.filter(
                pk=unit.pk, status=ClassifierUnit.Status.RUNNING, lease_token=token
            ).update(finished_at=timezone.now(), **fields)
        )


def _fail(unit: ClassifierUnit, token: str, reason: ClassifierReason | str) -> None:
    _settle(
        unit,
        token,
        status=ClassifierUnit.Status.FAILED,
        reason_code=str(reason),
        crop_valid=str(reason)
        not in (ClassifierReason.INVALID_CROP.value, ClassifierReason.BOX_TOO_SMALL.value),
    )


def _finite(*values: object) -> bool:
    return all(isinstance(v, int | float) and math.isfinite(v) for v in values)


def execute_classifier_units(run_id: int, *, runner: ClassifierRunner | None = None) -> int:
    """Chạy mọi ClassifierUnit đang chờ của run theo batch; idempotent. Trả số unit đã settle."""
    from orchestration.runsync import refresh_run

    run = QCRun.objects.select_related("config_version", "snapshot").get(pk=run_id)
    settled = 0
    while True:
        units, token = _claim_batch(run_id)
        if not units:
            break
        artifact = classifier_artifact(run)
        if artifact is None:
            for unit in units:
                _fail(unit, token, ClassifierReason.NOT_CONFIGURED)
            settled += len(units)
            continue
        provider = crop_provider()
        crops: list[CropItem] = []
        by_id: dict[str, ClassifierUnit] = {}
        crop_hash: dict[str, str] = {}
        for unit in units:
            candidate = CandidateRecord.objects.get(pk=unit.candidate_id)
            try:
                crop = provider.load(candidate)
            except Exception:  # lỗi tải crop (kể cả lỗi của provider) -> crop không hợp lệ
                _fail(unit, token, ClassifierReason.INVALID_CROP)
                settled += 1
                continue
            item_id = str(unit.pk)
            crops.append(CropItem(item_id, crop.data))
            by_id[item_id] = unit
            crop_hash[item_id] = crop.sha256
        if not crops:
            continue
        try:
            batch: BatchResult = (runner or default_runner()).run(
                artifact_key=artifact.artifact_key,
                expected_sha256=artifact.checksum,
                crops=crops,
            )
        except ClassifierRunError as exc:
            for unit in by_id.values():
                _fail(unit, token, exc.reason)
            settled += len(by_id)
            continue
        except Exception:
            logger.exception("classifier runner crashed", extra={"qc_run_id": run_id})
            for unit in by_id.values():
                _fail(unit, token, ClassifierReason.INFERENCE_ERROR)
            settled += len(by_id)
            continue
        for item_id, unit in by_id.items():
            outcome = batch.items.get(item_id)
            if outcome is None or not outcome.ok or outcome.prediction is None:
                _fail(
                    unit, token, outcome.reason if outcome and outcome.reason else "inference_error"
                )
            else:
                _settle_ok(unit, token, outcome.prediction, batch.checkpoint, crop_hash[item_id])
            settled += 1
    refresh_run(run_id)
    return settled


def _settle_ok(
    unit: ClassifierUnit,
    token: str,
    prediction: dict[str, Any],
    checkpoint: dict[str, Any],
    crop_sha256: str,
) -> None:
    top3 = prediction["top3"]
    score, margin = float(prediction["score"]), float(prediction["margin"])
    if not _finite(score, margin):
        _fail(unit, token, ClassifierReason.INFERENCE_ERROR)
        return
    best = top3[0]
    _settle(
        unit,
        token,
        status=ClassifierUnit.Status.COMPLETED,
        reason_code="",
        crop_sha256=crop_sha256,
        crop_valid=True,
        predicted_class_id=int(best["class_id"]),
        predicted_class_name=str(best["class_name"]),
        score=score,
        margin=margin,
        top3=[
            {
                "class_id": int(e["class_id"]),
                "class_name": str(e["class_name"]),
                "score": float(e["score"]),
            }
            for e in top3
        ],
        classifier_unknown=False,
        checkpoint_version=str(checkpoint.get("version", unit.checkpoint_version)),
        checkpoint_status=str(checkpoint.get("status", "")),
        class_map_version=str(checkpoint.get("class_map_version", unit.class_map_version)),
    )


@shared_task(name="orchestration.run_classifier_units", ignore_result=True)
def run_classifier_units_task(run_id: int) -> int:
    return execute_classifier_units(run_id)
