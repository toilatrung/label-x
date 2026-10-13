"""Read-only D05 payloads: verification lineage, selected final sources, operational source."""

from __future__ import annotations

from orchestration.services import ledger_counts
from review.finalization_service import (
    evaluate_operational_source,
    final_source_status,
)
from review.models import FinalRunVerification, ReworkVerification
from runs.models import QCRun


def run_kind(run: QCRun) -> str:
    if run.is_final:
        return "final"
    return "recheck" if run.origin_run_id is not None else "origin"


def _lineage_rows(run: QCRun) -> list[ReworkVerification]:
    if run.is_final:
        return [
            link.verification
            for link in FinalRunVerification.objects.filter(final_run=run)
            .select_related("verification")
            .order_by("verification_id")
        ]
    return list(ReworkVerification.objects.filter(recheck_run=run).order_by("pk"))


def verification_lineage(run: QCRun) -> list[dict[str, object]]:
    return [
        {
            "verification_id": verification.pk,
            "rework_id": verification.rework_id,
            "recheck_run_id": verification.recheck_run_id,
            "outcome": verification.outcome,
            "revision": verification.revision,
            "verified_at": verification.created_at.isoformat(),
        }
        for verification in _lineage_rows(run)
    ]


def selected_final_sources(run: QCRun) -> list[dict[str, object]]:
    """Latest passed verified revision per CVAT job, only for a valid selected final run."""

    if not run.is_final or run.origin_run_id is None:
        return []
    origin = QCRun.objects.get(pk=run.origin_run_id)
    if not final_source_status(origin, run)[0]:
        return []
    latest: dict[int, ReworkVerification] = {}
    for verification in (
        verification
        for verification in _lineage_rows(run)
        if verification.outcome == ReworkVerification.Outcome.PASS
    ):
        job_id = verification.rework.issue.frame_review.snapshot_frame.snapshot_job.cvat_job_id
        previous = latest.get(job_id)
        if previous is None or verification.rework_id > previous.rework_id:
            latest[job_id] = verification
    return [
        {
            "cvat_job_id": job_id,
            "rework_id": verification.rework_id,
            "verification_id": verification.pk,
            "source_run_id": verification.recheck_run_id,
            "source_revision": verification.revision,
        }
        for job_id, verification in sorted(latest.items(), key=lambda item: (item[0], item[1].pk))
    ]


def _coverage(run: QCRun) -> dict[str, object]:
    engines = []
    complete = run.status == QCRun.Status.COMPLETED
    for result in run.engine_results.filter(required=True).order_by("engine"):
        ledger = ledger_counts(run.pk, result.engine)
        engines.append(
            {
                "engine": result.engine,
                "status": result.status,
                "eligible": ledger.eligible,
                "completed": ledger.completed,
                "failed": ledger.failed,
                "pending": ledger.pending,
                "not_checked": ledger.not_checked,
            }
        )
        complete = complete and ledger.eligible > 0 and ledger.completed == ledger.eligible
    return {"complete": bool(engines) and complete, "required_engines": engines}


def operational_source(run: QCRun) -> dict[str, object]:
    """Which run consumers should trust for the run's origin scope, and why."""

    origin = QCRun.objects.get(pk=run.origin_run_id) if run.origin_run_id is not None else run
    source, reason, attempts, blockers = evaluate_operational_source(origin)
    # Every reason that applies (DEC-019 P07), unique and sorted so the list is stable. The
    # source decision itself is unchanged: with a valid final nothing blocks the scope, and
    # with none the reasons of all attempts are merged (computed once, in the same read).
    blocked_reasons = (
        []
        if reason == "selected_final"
        else [reason]
        if not attempts
        else sorted({blocker for found in blockers.values() for blocker in found})
    )
    return {
        "origin_run_id": origin.pk,
        "run_id": source.pk,
        "run_kind": run_kind(source),
        "status": source.status,
        "scope_complete": reason == "selected_final",
        "blocked_reasons": blocked_reasons,
        "reason": reason,
        "coverage": _coverage(source),
        "final_attempts": attempts,
    }


def run_lineage_fields(run: QCRun) -> dict[str, object]:
    """Fields for GET /api/runs/{id}/ (A integrates this into RunSerializer)."""

    return {
        "verification_lineage": verification_lineage(run),
        "selected_final_sources": selected_final_sources(run),
        "operational_source": operational_source(run),
    }
