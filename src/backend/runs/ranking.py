"""Persistence boundary between pure ranking policies and QC runs (T-031)."""

from __future__ import annotations

import json
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
    candidate_values = tuple(candidates)
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
        frames = tuple(
            FrameInput(
                frame.snapshot_job.cvat_task_id,
                frame.frame_index,
                frame.rectangle_count,
                engine_statuses,
            )
            for frame in snapshot_frames
        )
        frame_records = {
            f"{frame.snapshot_job.cvat_task_id}:{frame.frame_index}": frame
            for frame in snapshot_frames
        }
        if len(frame_records) != len(snapshot_frames):
            raise RankingPersistenceError("snapshot contains duplicate frame keys")

        risk_frames, risk_hash = rank_frames(
            frames,
            candidate_values,
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
                risk_frames=risk_frames,
            ),
            _create_ranking(
                run=run,
                source=RunRanking.Source.RANDOM_AUDIT,
                content_hash=content_hash,
                ranking_hash=audit.content_hash,
                frame_records=frame_records,
                risk_by_key=risk_by_key,
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
    rank: int,
    tie_break_hash: str,
    source_value: Decimal | None,
) -> RunRankingEntry:
    return RunRankingEntry(
        ranking=ranking,
        snapshot_frame=snapshot_frame,
        rank=rank,
        score=risk.score,
        baseline_score=risk.baseline_score,
        missing_evidence=risk.missing_evidence,
        issue_counts=dict(risk.anchor_counts),
        explanation=explain_score(risk),
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
