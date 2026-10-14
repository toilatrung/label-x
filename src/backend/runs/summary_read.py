"""Read-only grouped aggregates. Do not confuse candidates with confirmed issues."""

from collections import Counter
from typing import Any

from django.db.models import CharField, Count, Max, Min, Q, QuerySet, Value
from django.db.models.functions import Cast, Concat, TruncDay, TruncWeek

from audit.models import AuditEvent
from orchestration.models import CandidateRecord, LedgerUnit
from review.models import FrameReview, Issue, ReviewDecision
from runs.models import QCRun, WorkUnit
from snapshots.models import SnapshotFrame

REVIEWED_STATES = (
    FrameReview.State.REVIEWED,
    FrameReview.State.AWAITING_FOLLOWUP,
    FrameReview.State.COMPLETED,
)
CLOSED_ISSUE_STATES = (Issue.State.REJECTED, Issue.State.RESOLVED)


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def logical_frame_count(task_field: str, frame_field: str) -> Count:
    # Jobs may overlap: the same task/frame is still one logical frame.
    return Count(
        Concat(Cast(task_field, CharField()), Value(":"), Cast(frame_field, CharField())),
        distinct=True,
        filter=Q(**{f"{task_field}__isnull": False, f"{frame_field}__isnull": False}),
    )


def frames_for_run(run: QCRun) -> QuerySet[SnapshotFrame]:
    return SnapshotFrame.objects.filter(snapshot_job__snapshot_id=run.snapshot_id)


def reviewed_for_run(run: QCRun) -> QuerySet[FrameReview]:
    return FrameReview.objects.filter(
        run=run,
        state__in=REVIEWED_STATES,
        snapshot_frame__snapshot_job__snapshot_id=run.snapshot_id,
    )


def run_metrics(run: QCRun) -> dict[str, Any]:
    total = frames_for_run(run).aggregate(
        n=logical_frame_count("snapshot_job__cvat_task_id", "frame_index")
    )["n"]
    reviewed = reviewed_for_run(run).aggregate(
        n=logical_frame_count(
            "snapshot_frame__snapshot_job__cvat_task_id", "snapshot_frame__frame_index"
        )
    )["n"]
    families: Counter[str] = Counter()
    states: Counter[str] = Counter()
    for row in (
        Issue.objects.filter(frame_review__run=run)
        .values("family", "state")
        .annotate(n=Count("id"))
    ):
        families[row["family"]] += row["n"]
        states[row["state"]] += row["n"]
    return {
        "run_id": run.pk,
        "status": run.status,
        "frames_total": total,
        "frames_reviewed": reviewed,
        "issues_total": sum(families.values()),
        "issues_by_family": dict(families),
        "issues_by_state": dict(states),
        "reviewed_ratio": ratio(reviewed, total),
    }


def engine_stats(run: QCRun) -> dict[str, Any]:
    ledger = {
        r["engine"]: r
        for r in LedgerUnit.objects.filter(run=run)
        .values("engine")
        .annotate(total=Count("id"), failed=Count("id", filter=Q(outcome="failed")))
    }
    candidates = {
        r["engine"]: r["n"]
        for r in CandidateRecord.objects.filter(run=run).values("engine").annotate(n=Count("id"))
    }
    times = {
        r["engine"]: r
        for r in WorkUnit.objects.filter(run=run)
        .values("engine")
        .annotate(
            first=Min("started_at"),
            last=Max("finished_at"),
            total=Count("id"),
            finished=Count("finished_at"),
        )
    }
    rows = []
    for result in run.engine_results.all():
        counts = ledger.get(result.engine)
        timing = times.get(result.engine)
        duration = None
        if (
            timing
            and timing["first"] is not None
            and timing["last"] is not None
            and timing["finished"] == timing["total"]
        ):
            duration = max(0, int((timing["last"] - timing["first"]).total_seconds() * 1000))
        rows.append(
            {
                "engine": result.engine,
                "status": result.status,
                "units_total": counts["total"]
                if counts
                else result.eligible_units + result.not_checked_units,
                "units_failed": counts["failed"] if counts else result.failed_units,
                "candidates": candidates.get(result.engine, 0),
                "duration_ms": duration,
            }
        )
    return {"run_id": run.pk, "engines": rows}


def candidate_categories(run: QCRun) -> dict[str, Any]:
    counts = list(
        CandidateRecord.objects.filter(run=run)
        .values("family")
        .annotate(n=Count("id"))
        .order_by("family")
    )
    total = sum(row["n"] for row in counts)
    return {
        "run_id": run.pk,
        "total": total,
        "categories": [
            {"family": row["family"], "count": row["n"], "share": ratio(row["n"], total)}
            for row in counts
        ],
    }


def review_volume(run: QCRun, query: dict[str, Any]) -> dict[str, Any]:
    """Completed-frame audit events, not number of decisions mistaken for completion."""
    frame_ids = (
        FrameReview.objects.filter(run=run)
        .annotate(text_id=Cast("id", CharField()))
        .values("text_id")
    )
    events = AuditEvent.objects.filter(
        action="frame.complete", object_type="frame", object_id__in=frame_ids
    )
    decisions = ReviewDecision.objects.filter(issue__frame_review__run=run)
    for key, lookup in (("date_from", "gte"), ("date_to", "lte")):
        if key in query:
            events = events.filter(**{f"occurred_at__date__{lookup}": query[key]})
            decisions = decisions.filter(**{f"recorded_at__date__{lookup}": query[key]})
    trunc = TruncWeek if query["granularity"] == "week" else TruncDay
    completed = {
        row["period"].date(): row["n"]
        for row in events.order_by()
        .annotate(period=trunc("occurred_at"))
        .values("period")
        .annotate(n=Count("object_id", distinct=True))
    }
    decided = {
        row["period"].date(): row["n"]
        for row in decisions.order_by()
        .annotate(period=trunc("recorded_at"))
        .values("period")
        .annotate(n=Count("id"))
    }
    return {
        "run_id": run.pk,
        "granularity": query["granularity"],
        "points": [
            {
                "period_start": date,
                "frames_reviewed": completed.get(date, 0),
                "decisions": decided.get(date, 0),
            }
            for date in sorted(completed.keys() | decided.keys())
        ],
    }
