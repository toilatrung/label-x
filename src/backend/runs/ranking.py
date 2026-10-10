"""Persistence boundary between pure ranking policies and QC runs (T-031)."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256

from django.db import transaction

from ranking import SCORE_V0, FrameInput, control_rankings, explain_score, random_audit_slice
from ranking.sampling import RankingSource, StoredOrdering
from ranking.score_v0 import RankedFrame, rank_frames
from runs.models import QCRun, RunRanking, RunRankingEntry
from snapshots.models import SnapshotFrame

SCORABLE_FAMILIES = frozenset({"E1", "E2", "E3"})
DEFAULT_AUDIT_PERCENT = Decimal("10")


class RankingPersistenceError(RuntimeError):
    """Raised when persisted ranking content would be changed in place."""


def persist_run_rankings(
    *,
    run_id: int,
    candidates: Iterable[Mapping[str, object]],
    audit_percent: Decimal,
) -> tuple[RunRanking, ...]:
    """Score and persist risk, audit and control sources exactly once per run.

    An identical retry is idempotent. A retry whose normalized input or ordering
    hashes differ fails closed instead of mutating an already published ranking.
    """
    candidate_values = _unique_candidates(candidates)
    unsupported_families = {
        candidate.get("family")
        for candidate in candidate_values
        if candidate.get("family") not in SCORABLE_FAMILIES | {"structural"}
    }
    if unsupported_families:
        raise RankingPersistenceError(
            f"ranking does not support candidate families: {sorted(map(str, unsupported_families))}"
        )
    with transaction.atomic():
        run = (
            QCRun.objects.select_for_update()
            .select_related("snapshot", "config_version")
            .filter(pk=run_id)
            .first()
        )
        if run is None:
            raise QCRun.DoesNotExist(f"Run {run_id} does not exist")

        snapshot_frames = tuple(
            SnapshotFrame.objects.filter(snapshot_job__snapshot_id=run.snapshot_id)
            .select_related("snapshot_job")
            .order_by("snapshot_job__cvat_task_id", "frame_index", "id")
        )
        engine_statuses = tuple(
            run.engine_results.order_by("engine").values_list("engine", "status")
        )
        required_engines = tuple(
            run.engine_results.filter(required=True)
            .order_by("engine")
            .values_list("engine", flat=True)
        )
        frames, frame_records, frame_provenance = _normalize_snapshot_frames(
            snapshot_frames, engine_statuses
        )
        scorable_candidates = tuple(
            candidate
            for candidate in candidate_values
            if candidate.get("family") in SCORABLE_FAMILIES
        )
        warnings_by_frame = _warnings_by_frame(candidate_values)

        risk_frames, risk_hash = rank_frames(
            frames,
            scorable_candidates,
            seed=run.seed,
            required_engines=required_engines,
        )
        audit = random_audit_slice(frames, percent=audit_percent, seed=run.seed)
        controls = control_rankings(frames, candidate_values, seed=run.seed)
        content_hash = _content_hash(run, frames, candidate_values, audit_percent)
        ordering_hashes = {
            RunRanking.Source.RISK: risk_hash,
            RunRanking.Source.RANDOM_AUDIT: audit.content_hash,
            **{_model_source(control.source): control.content_hash for control in controls},
        }

        existing = tuple(run.rankings.prefetch_related("entries").order_by("source"))
        if existing:
            existing_hashes = {
                item.source: (item.content_hash, item.ranking_hash) for item in existing
            }
            expected_hashes = {
                source: (content_hash, ranking_hash)
                for source, ranking_hash in ordering_hashes.items()
            }
            if existing_hashes == expected_hashes:
                return existing
            raise RankingPersistenceError(
                "run rankings already exist with different normalized content"
            )

        risk_by_key = {frame.frame_key: frame for frame in risk_frames}
        created = [
            _create_ranking(
                run=run,
                source=RunRanking.Source.RISK,
                content_hash=content_hash,
                ranking_hash=risk_hash,
                frame_records=frame_records,
                risk_by_key=risk_by_key,
                frame_provenance=frame_provenance,
                warnings_by_frame=warnings_by_frame,
                risk_frames=risk_frames,
            ),
            _create_ranking(
                run=run,
                source=RunRanking.Source.RANDOM_AUDIT,
                content_hash=content_hash,
                ranking_hash=audit.content_hash,
                frame_records=frame_records,
                risk_by_key=risk_by_key,
                frame_provenance=frame_provenance,
                warnings_by_frame=warnings_by_frame,
                ordering=audit,
            ),
        ]
        created.extend(
            _create_ranking(
                run=run,
                source=_model_source(control.source),
                content_hash=content_hash,
                ranking_hash=control.content_hash,
                frame_records=frame_records,
                risk_by_key=risk_by_key,
                frame_provenance=frame_provenance,
                warnings_by_frame=warnings_by_frame,
                ordering=control,
            )
            for control in controls
        )
        if run.score_version != SCORE_V0:
            QCRun.objects.filter(pk=run.pk).update(score_version=SCORE_V0)
        return tuple(sorted(created, key=lambda item: item.source))


def _create_ranking(
    *,
    run: QCRun,
    source: str,
    content_hash: str,
    ranking_hash: str,
    frame_records: Mapping[str, SnapshotFrame],
    risk_by_key: Mapping[str, RankedFrame],
    frame_provenance: Mapping[str, tuple[Mapping[str, object], ...]],
    warnings_by_frame: Mapping[str, tuple[Mapping[str, object], ...]],
    risk_frames: tuple[RankedFrame, ...] | None = None,
    ordering: StoredOrdering | None = None,
) -> RunRanking:
    ranking = RunRanking.objects.create(
        run=run,
        source=source,
        seed=run.seed,
        score_version=SCORE_V0,
        content_hash=content_hash,
        ranking_hash=ranking_hash,
    )
    if risk_frames is not None:
        entries = [
            _entry(
                ranking,
                frame_records[frame.frame_key],
                frame,
                provenance=frame_provenance[frame.frame_key],
                warnings=warnings_by_frame.get(frame.frame_key, ()),
                rank=frame.rank,
                tie_break_hash=frame.tie_break_hash,
                source_value=frame.score,
            )
            for frame in risk_frames
        ]
    elif ordering is not None:
        entries = [
            _entry(
                ranking,
                frame_records[item.frame_key],
                risk_by_key[item.frame_key],
                provenance=frame_provenance[item.frame_key],
                warnings=warnings_by_frame.get(item.frame_key, ()),
                rank=item.rank,
                tie_break_hash=item.tie_break_hash,
                source_value=item.value,
            )
            for item in ordering.entries
        ]
    else:  # pragma: no cover - internal programming guard
        raise AssertionError("risk_frames or ordering is required")
    RunRankingEntry.objects.bulk_create(entries)
    return ranking


def _entry(
    ranking: RunRanking,
    snapshot_frame: SnapshotFrame,
    risk: RankedFrame,
    *,
    provenance: tuple[Mapping[str, object], ...],
    warnings: tuple[Mapping[str, object], ...],
    rank: int,
    tie_break_hash: str,
    source_value: Decimal | None,
) -> RunRankingEntry:
    explanation = explain_score(risk)
    explanation["snapshot_frame_provenance"] = list(provenance)
    explanation["structural_warnings"] = list(warnings)
    return RunRankingEntry(
        ranking=ranking,
        snapshot_frame=snapshot_frame,
        rank=rank,
        score=risk.score,
        baseline_score=risk.baseline_score,
        missing_evidence=risk.missing_evidence,
        issue_counts=dict(risk.anchor_counts),
        explanation=explanation,
        tie_break_hash=tie_break_hash,
        source_value=source_value,
    )


def _model_source(source: RankingSource) -> str:
    return RunRanking.Source(source.value)


def _content_hash(
    run: QCRun,
    frames: tuple[FrameInput, ...],
    candidates: tuple[Mapping[str, object], ...],
    audit_percent: Decimal,
) -> str:
    canonical_candidates = sorted(
        json.dumps(candidate, sort_keys=True, separators=(",", ":"), default=str)
        for candidate in candidates
    )
    payload = {
        "snapshot_revision": run.snapshot.revision_sha256,
        "config_version_id": run.config_version_id,
        "config": run.config_version.payload,
        "engine_versions": run.engine_versions,
        "score_version": SCORE_V0,
        "seed": run.seed,
        "audit_percent": str(audit_percent),
        "frames": [asdict(frame) for frame in frames],
        "candidates": canonical_candidates,
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def persist_terminal_run_rankings(run_id: int) -> tuple[RunRanking, ...]:
    """Persist orchestrator output after a run reaches a terminal state."""
    from orchestration.models import CandidateRecord

    run = QCRun.objects.select_related("config_version").get(pk=run_id)
    candidates = (
        {
            "engine": candidate.engine,
            "engine_version": candidate.engine_version,
            "family": candidate.family,
            "frame": {
                "cvat_task_id": candidate.cvat_task_id,
                "frame_number": candidate.frame_number,
            },
            "anchor": candidate.anchor,
            "evidence": candidate.evidence,
        }
        for candidate in CandidateRecord.objects.filter(run_id=run_id).order_by("dedup_key", "id")
    )
    return persist_run_rankings(
        run_id=run_id,
        candidates=candidates,
        audit_percent=_audit_percent(run),
    )


def _audit_percent(run: QCRun) -> Decimal:
    payload = run.config_version.payload or {}
    sampling = payload.get("sampling", {})
    raw = sampling.get("random_audit_percent") if isinstance(sampling, Mapping) else None
    if raw is None:
        raw = payload.get("audit_percent", DEFAULT_AUDIT_PERCENT)
    try:
        value = Decimal(str(raw))
    except Exception as exc:
        raise RankingPersistenceError("audit percent must be numeric") from exc
    if not value.is_finite() or not Decimal(0) <= value <= Decimal(100):
        raise RankingPersistenceError("audit percent must be between 0 and 100")
    return value


def _unique_candidates(
    candidates: Iterable[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    """Drop exact cross-job/retry duplicates and impose a canonical input order."""
    by_payload: dict[str, Mapping[str, object]] = {}
    for candidate in candidates:
        canonical = json.dumps(candidate, sort_keys=True, separators=(",", ":"), default=str)
        by_payload.setdefault(canonical, candidate)
    return tuple(by_payload[key] for key in sorted(by_payload))


def _normalize_snapshot_frames(
    snapshot_frames: tuple[SnapshotFrame, ...],
    engine_statuses: tuple[tuple[str, str], ...],
) -> tuple[
    tuple[FrameInput, ...],
    dict[str, SnapshotFrame],
    dict[str, tuple[Mapping[str, object], ...]],
]:
    """Collapse legal CVAT job overlap to one task/frame while retaining provenance."""
    grouped: dict[str, list[SnapshotFrame]] = defaultdict(list)
    for frame in snapshot_frames:
        grouped[f"{frame.snapshot_job.cvat_task_id}:{frame.frame_index}"].append(frame)

    frames: list[FrameInput] = []
    records: dict[str, SnapshotFrame] = {}
    provenance: dict[str, tuple[Mapping[str, object], ...]] = {}
    for frame_key in sorted(grouped, key=_frame_key_sort):
        rows = sorted(grouped[frame_key], key=lambda row: (row.snapshot_job.cvat_job_id, row.pk))
        records[frame_key] = rows[0]
        unique_shapes = {_shape_identity(shape) for row in rows for shape in row.shapes}
        task_id, frame_number = (int(value) for value in frame_key.split(":"))
        frames.append(FrameInput(task_id, frame_number, len(unique_shapes), engine_statuses))
        provenance[frame_key] = tuple(
            {
                "snapshot_frame_id": row.pk,
                "cvat_job_id": row.snapshot_job.cvat_job_id,
                "job_sha256": row.snapshot_job.sha256,
                "media_sha256": row.media_sha256,
            }
            for row in rows
        )
    return tuple(frames), records, provenance


def _warnings_by_frame(
    candidates: tuple[Mapping[str, object], ...],
) -> dict[str, tuple[Mapping[str, object], ...]]:
    warnings: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for candidate in candidates:
        if candidate.get("family") != "structural":
            continue
        frame = candidate.get("frame")
        if not isinstance(frame, Mapping):
            continue
        task_id, frame_number = frame.get("cvat_task_id"), frame.get("frame_number")
        if isinstance(task_id, int) and isinstance(frame_number, int):
            warnings[f"{task_id}:{frame_number}"].append(candidate)
    return {key: tuple(value) for key, value in warnings.items()}


def _frame_key_sort(frame_key: str) -> tuple[int, int]:
    task_id, frame_number = frame_key.split(":")
    return int(task_id), int(frame_number)


def _shape_identity(shape: object) -> str:
    """Prefer immutable CVAT source identity; fall back to canonical content."""
    if isinstance(shape, Mapping):
        source = shape.get("source")
        if isinstance(source, Mapping) and "kind" in source and "id" in source:
            return f"source:{source['kind']}:{source['id']}"
    return "content:" + json.dumps(shape, sort_keys=True, separators=(",", ":"), default=str)
