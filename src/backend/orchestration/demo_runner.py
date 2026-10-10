"""DEMO-ONLY synchronous QC runner for M-DEMO01 / D-02."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.contrib.auth.models import User

from orchestration.dispatch import run_work_unit
from orchestration.models import CandidateRecord
from orchestration.runsync import refresh_run
from ranking.score_v0 import FrameInput, RankedFrame, rank_frames
from runs.models import QCRun, WorkUnit
from runs.services import create_qc_run
from snapshots.models import SnapshotFrame

_SCOREABLE_FAMILIES = frozenset({"E1", "E2", "E3"})
logger = logging.getLogger("labelx.orchestration")


@dataclass(frozen=True, slots=True)
class DemoRunSummary:
    """Result printed by the demo management command."""

    run_id: int
    created: bool
    status: str
    executed_work_units: int
    failed_work_units: int
    candidate_count: int
    ranked_frames: tuple[RankedFrame, ...]
    ranking_hash: str


def run_snapshot_synchronously(
    *,
    snapshot_id: int,
    config_version_id: int,
    seed: int,
    created_by: User,
    idempotency_key: str,
) -> DemoRunSummary:
    """Create/reuse a run, execute pending shards inline, then calculate score_v0.

    Work-unit failures are deliberately collected instead of aborting the loop so
    every EngineResult reaches a public Failed/Partial/Not checked/Checked state.
    """
    run, created = create_qc_run(
        snapshot_id=snapshot_id,
        config_version_id=config_version_id,
        seed=seed,
        created_by=created_by,
        idempotency_key=idempotency_key,
        enqueue_after_commit=False,
    )

    executed = 0
    pending_ids = tuple(
        run.work_units.filter(status=WorkUnit.Status.PENDING)
        .order_by("engine", "shard_index", "id")
        .values_list("id", flat=True)
    )
    for work_unit_id in pending_ids:
        executed += 1
        try:
            run_work_unit.apply(args=(work_unit_id,)).get(propagate=True)
        except Exception:  # noqa: BLE001 - continue so every engine reaches a public status
            logger.exception(
                "demo work unit failed",
                extra={"qc_run_id": run.pk, "work_unit_id": work_unit_id},
            )
            continue

    refresh_run(run.pk)
    run.refresh_from_db()
    ranked_frames, ranking_hash = rank_demo_frames(run)
    return DemoRunSummary(
        run_id=run.pk,
        created=created,
        status=run.status,
        executed_work_units=executed,
        failed_work_units=run.work_units.filter(status=WorkUnit.Status.FAILED).count(),
        candidate_count=CandidateRecord.objects.filter(run_id=run.pk).count(),
        ranked_frames=ranked_frames,
        ranking_hash=ranking_hash,
    )


def rank_demo_frames(run: QCRun) -> tuple[tuple[RankedFrame, ...], str]:
    """Calculate score_v0 for every snapshot frame without persisting ranking rows.

    score_v0 is frozen for E1/E2/E3. Structural Schema/Geometry warnings remain
    persisted as CandidateRecord rows for the review UI but are not score terms.
    """
    results = tuple(run.engine_results.order_by("engine"))
    statuses = tuple((result.engine, result.status) for result in results)
    frames = tuple(
        FrameInput(
            cvat_task_id=frame.snapshot_job.cvat_task_id,
            frame_number=frame.frame_index,
            annotation_count=len(frame.shapes),
            engine_statuses=statuses,
        )
        for frame in SnapshotFrame.objects.filter(snapshot_job__snapshot_id=run.snapshot_id)
        .select_related("snapshot_job")
        .order_by("snapshot_job__cvat_task_id", "frame_index", "id")
    )
    candidates = (
        {
            "family": candidate.family,
            "frame": {
                "cvat_task_id": candidate.cvat_task_id,
                "frame_number": candidate.frame_number,
            },
            "anchor": candidate.anchor,
            "evidence": candidate.evidence,
        }
        for candidate in CandidateRecord.objects.filter(
            run_id=run.pk, family__in=_SCOREABLE_FAMILIES
        ).order_by("dedup_key")
    )
    required_engines = tuple(result.engine for result in results if result.required)
    return rank_frames(
        frames,
        candidates,
        seed=run.seed,
        required_engines=required_engines,
    )
