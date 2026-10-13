"""KPI, gate và waiver (MBE-01): chỉ số suy ra từ dữ liệu review đã có trong DB.

Giới hạn (MVP): nội dung GT không được lưu nên KPI-1, KPI-2, KPI-2b và G-1 luôn `not_checked`;
G-2, G-3, G-4 và các điều kiện gate tính từ Issue/ReviewDecision/DecisionCase/Rework thật.
Ngưỡng là cấu hình khởi điểm pilot (requirements G-2 = 0, G-3 >= 90%, G-4 <= 5%).
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from engines.interface import EngineStatus, public_status
from orchestration.services import ledger_counts
from review.finalization_service import evaluate_operational_source
from review.models import DecisionCase, FrameReview, Issue, ReviewDecision, ReworkRequest
from runs.models import QCRun, RunRanking, Waiver

WAIVABLE = ("coverage", "agreement")
OPEN_STATES = (
    Issue.State.CONFIRMED,
    Issue.State.FIX_PENDING,
    Issue.State.RECHECK_PENDING,
    Issue.State.REOPENED,
)
THRESHOLDS: dict[str, float] = {
    "coverage": 1.0,
    "open_critical_issues": 0.0,
    "rework_verified": 1.0,
    "residual": 0.05,
    "agreement": 0.9,
}
_REVIEWED_STATES = (
    FrameReview.State.REVIEWED,
    FrameReview.State.AWAITING_FOLLOWUP,
    FrameReview.State.COMPLETED,
)


def e_min_default() -> int:
    """E_min tạm cho pilot; ghi trong parameters của evaluation để audit."""
    return int(getattr(settings, "KPI_E_MIN", 30))


def origin_of(run: QCRun) -> QCRun:
    return QCRun.objects.get(pk=run.origin_run_id) if run.origin_run_id is not None else run


def _issues(run_ids: list[int]) -> Any:
    return Issue.objects.filter(frame_review__run_id__in=run_ids)


def coverage_value(source: QCRun) -> tuple[float | None, int]:
    completed = eligible = 0
    for result in source.engine_results.filter(required=True):
        ledger = ledger_counts(source.pk, result.engine)
        completed += ledger.completed
        eligible += ledger.eligible
    if eligible == 0:
        return None, 0
    return completed / eligible, eligible


def open_critical_count(run_ids: list[int]) -> tuple[int, int]:
    critical = _issues(run_ids).filter(severity=Issue.Severity.CRITICAL)
    return critical.filter(state__in=OPEN_STATES).count(), critical.count()


def rework_ratio(run_ids: list[int]) -> tuple[float, int]:
    rows = ReworkRequest.objects.filter(issue__frame_review__run_id__in=run_ids)
    total = rows.count()
    if total == 0:
        return 1.0, 0
    return rows.filter(status=ReworkRequest.Status.RESOLVED).count() / total, total


def residual_ratio(origin: QCRun) -> tuple[float | None, int]:
    """G-4: tỉ lệ frame còn lỗi mở trong lát random audit đã review."""
    audit_frames = RunRanking.objects.filter(
        run=origin, source=RunRanking.Source.RANDOM_AUDIT
    ).values_list("entries__snapshot_frame_id", flat=True)
    frames = FrameReview.objects.filter(
        run=origin, snapshot_frame_id__in=list(audit_frames), state__in=_REVIEWED_STATES
    )
    total = frames.count()
    if total == 0:
        return None, 0
    dirty = frames.filter(Q(issues__state__in=OPEN_STATES)).distinct().count()
    return dirty / total, total


def agreement_ratio(run_ids: list[int]) -> tuple[float | None, int]:
    """G-3: quyết định reviewer trùng kết luận adjudicator / số quyết định được chấm."""
    scored = matched = 0
    for decision in ReviewDecision.objects.filter(
        issue__frame_review__run_id__in=run_ids, actor_role="reviewer"
    ).exclude(action__in=[ReviewDecision.Action.ESCALATE, ReviewDecision.Action.REQUEST_FIX]):
        case = (
            DecisionCase.objects.filter(issue_id=decision.issue_id).order_by("-created_at").first()
        )
        if case is None:
            continue
        scored += 1
        if decision.action == case.outcome:  # uncertain không bao giờ trùng
            matched += 1
    if scored == 0:
        return None, 0
    return matched / scored, scored


def _condition(
    name: str, observed: float | None, passed: bool | None, **extra: Any
) -> dict[str, Any]:
    status = (
        "not_checked" if observed is None or passed is None else ("passed" if passed else "failed")
    )
    return {
        "name": name,
        "status": status,
        "observed": observed,
        "threshold": THRESHOLDS[name],
        "waiver_id": None,
        "reason": extra.get("reason"),
    }


def _active_waiver(run_ids: list[int], condition: str) -> Waiver | None:
    return (
        Waiver.objects.filter(
            run_id__in=run_ids,
            condition=condition,
            status=Waiver.Status.APPROVED,
            expires_at__gt=timezone.now(),
        )
        .order_by("-pk")
        .first()
    )


def gate_result(run: QCRun) -> dict[str, Any]:
    origin = origin_of(run)
    source, reason, _attempts, _blockers = evaluate_operational_source(origin)
    run_ids = sorted({origin.pk, source.pk})
    complete = reason == "selected_final"

    cov, _eligible = coverage_value(source)
    cov_ok = None if cov is None else (cov >= 1.0 and source.status == QCRun.Status.COMPLETED)
    open_critical, _ = open_critical_count(run_ids)
    rework, _ = rework_ratio(run_ids)
    residual, _ = residual_ratio(origin)
    agreement, _ = agreement_ratio(run_ids)
    conditions = [
        _condition("coverage", cov, cov_ok, reason=None if complete else reason),
        _condition("open_critical_issues", float(open_critical), open_critical == 0),
        _condition("rework_verified", rework, rework >= 1.0),
        _condition("residual", residual, None if residual is None else residual <= 0.05),
        _condition("agreement", agreement, None if agreement is None else agreement >= 0.9),
    ]
    for item in conditions:
        # Waiver chỉ cứu coverage/agreement và không biến run chưa Completed thành đạt.
        if item["name"] in WAIVABLE and item["status"] != "passed":
            waiver = _active_waiver(run_ids, str(item["name"]))
            if waiver is not None and source.status == QCRun.Status.COMPLETED:
                item["status"] = "waived"
                item["waiver_id"] = waiver.pk
    statuses = {item["status"] for item in conditions}
    if "failed" in statuses or not complete:
        overall = "failed"
    elif "not_checked" in statuses:
        overall = "not_checked"
    else:
        overall = "passed"
    return {
        "run_id": run.pk,
        "source_run_id": source.pk,
        "source_reason": reason,
        "status": overall,
        "conditions": conditions,
    }


def _metric(
    value: float | None, sample: int, denominator: int, method: str, *, status: str | None = None
) -> dict[str, Any]:
    return {
        "status": status or ("computed" if value is not None else "not_checked"),
        "value": value,
        "sample_size": sample,
        "denominator": denominator,
        "method": method,
        "confidence_interval": None,
    }


def compute_metrics(run: QCRun, *, e_min: int) -> tuple[dict[str, Any], int]:
    """Trả (metrics, cỡ mẫu = số frame đã review của run gốc)."""
    origin = origin_of(run)
    source, _reason, _a, _b = evaluate_operational_source(origin)
    run_ids = sorted({origin.pk, source.pk})
    sample = FrameReview.objects.filter(run=origin, state__in=_REVIEWED_STATES).count()
    low = sample < e_min
    no_gt = "gt_payload_not_stored"
    metrics: dict[str, Any] = {
        key: _metric(None, sample, 0, no_gt, status="insufficient_sample" if low else None)
        for key in ("KPI-1", "KPI-2", "KPI-2b", "G-1")
    }
    open_critical, critical_total = open_critical_count(run_ids)
    residual, residual_n = residual_ratio(origin)
    agreement, agreement_n = agreement_ratio(run_ids)
    metrics["G-2"] = _metric(float(open_critical), sample, critical_total, "open_critical_count")
    metrics["G-3"] = _metric(agreement, agreement_n, agreement_n, "reviewer_vs_adjudicator")
    metrics["G-4"] = _metric(residual, residual_n, residual_n, "random_audit_residual")
    if low:
        for key in ("G-2", "G-3", "G-4"):
            metrics[key]["status"] = "insufficient_sample"
            metrics[key]["value"] = None
    return metrics, sample


def ledger_entries(run: QCRun) -> list[dict[str, Any]]:
    """Ledger từng engine của run (dùng cho GET /runs/{id}/ledger/ và báo cáo)."""
    pk = run.pk
    finished = run.status not in (QCRun.Status.QUEUED, QCRun.Status.RUNNING)
    entries: list[dict[str, Any]] = []
    for result in run.engine_results.all():
        counts = ledger_counts(pk, result.engine)
        displayed_status = result.status
        if counts.total:
            displayed_status = public_status(counts, finished=finished).value
        elif finished and displayed_status == EngineStatus.RUNNING:
            displayed_status = EngineStatus.NOT_CHECKED
        entries.append(
            {
                "engine": result.engine,
                "status": displayed_status,
                "required": result.required,
                "unit": result.unit,
                "total": counts.total,
                "eligible": counts.eligible,
                "excluded": counts.excluded,
                "applicability_version": result.applicability_version,
                "completed": counts.completed,
                "failed": counts.failed,
                "pending": counts.pending,
                "not_checked": counts.not_checked,
                "not_checked_reasons": {
                    key.value: value for key, value in counts.not_checked_reasons.items()
                },
                "coverage": counts.coverage,
            }
        )
    return entries
