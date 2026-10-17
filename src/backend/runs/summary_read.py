"""Read-only grouped aggregates. Do not confuse candidates with confirmed issues."""

from collections import Counter
from typing import Any

from django.db.models import CharField, Count, Max, Min, Q, QuerySet, Value
from django.db.models.functions import Cast, Concat, TruncDay, TruncWeek

from audit.models import AuditEvent
from engines.interface import EngineUnitOutcome, LedgerCounts, NotCheckedReason
from orchestration.models import CandidateRecord, LedgerUnit
from review.models import FrameReview, Issue, ReviewDecision
from runs.kpi import OPEN_STATES
from runs.models import QCRun, WorkUnit
from snapshots.models import SnapshotFrame

REVIEWED_STATES = (
    FrameReview.State.REVIEWED,
    FrameReview.State.AWAITING_FOLLOWUP,
    FrameReview.State.COMPLETED,
)
CLOSED_ISSUE_STATES = (Issue.State.REJECTED, Issue.State.RESOLVED)
# "Lỗi đã xác nhận": từ confirmed trở đi, cùng cách đếm với thẻ tổng của Quality Summary.
CONFIRMED_ISSUE_STATES = (
    Issue.State.CONFIRMED,
    Issue.State.FIX_PENDING,
    Issue.State.RECHECK_PENDING,
    Issue.State.RESOLVED,
    Issue.State.REOPENED,
)


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


def task_quality_extras(run: QCRun, task_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Coverage, candidate, lỗi đã xác nhận và gate theo Task (BLOCKER-034 B-3, DEC-023).

    coverage = unit completed / eligible của các engine bắt buộc, chỉ tính unit của Task (cùng
    mẫu số với gate của run). Engine VLM không có ledger theo Task nên không tính. gate_status chỉ
    để hiển thị, không thay Quality Gate của run: blocked khi còn Issue critical chưa đóng, partial
    khi coverage < 100%, passed khi không; null khi Task chưa có unit eligible.
    """
    required = [
        engine
        for engine in run.engine_results.filter(required=True).values_list("engine", flat=True)
        if engine != "vlm"
    ]
    outcomes: dict[int, list[tuple[EngineUnitOutcome, NotCheckedReason | None]]] = {}
    for task_id, outcome, reason in LedgerUnit.objects.filter(
        run_id=run.pk, engine__in=required, cvat_task_id__in=task_ids
    ).values_list("cvat_task_id", "outcome", "not_checked_reason"):
        outcomes.setdefault(task_id, []).append(
            (EngineUnitOutcome(outcome), NotCheckedReason(reason) if reason else None)
        )
    candidates = dict(
        CandidateRecord.objects.filter(run_id=run.pk, cvat_task_id__in=task_ids)
        .values("cvat_task_id")
        .annotate(n=Count("id"))
        .values_list("cvat_task_id", "n")
    )
    task_field = "frame_review__snapshot_frame__snapshot_job__cvat_task_id"
    issues = Issue.objects.filter(frame_review__run=run, **{f"{task_field}__in": task_ids})
    confirmed = dict(
        issues.filter(state__in=CONFIRMED_ISSUE_STATES)
        .values(task_field)
        .annotate(n=Count("id", distinct=True))
        .values_list(task_field, "n")
    )
    critical = dict(
        issues.filter(severity=Issue.Severity.CRITICAL, state__in=OPEN_STATES)
        .values(task_field)
        .annotate(n=Count("id", distinct=True))
        .values_list(task_field, "n")
    )
    rows: dict[int, dict[str, Any]] = {}
    for task_id in task_ids:
        counts = LedgerCounts.from_outcomes(outcomes.get(task_id, []))
        coverage = ratio(counts.completed, counts.eligible)
        if critical.get(task_id, 0):
            gate = "blocked"
        elif coverage is None:
            gate = None
        else:
            gate = "passed" if coverage >= 1.0 else "partial"
        rows[task_id] = {
            "coverage": coverage,
            "candidates": candidates.get(task_id, 0),
            "confirmed_issues": confirmed.get(task_id, 0),
            "gate_status": gate,
        }
    return rows
