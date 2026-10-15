"""Read model của Evaluation (M04C-02/03): suy ra trạng thái từ VlmUnit, không lưu trùng."""

from __future__ import annotations

from typing import Any

from orchestration.models import Evaluation, VlmUnit
from runs.vlm_read import build_vlm_view

_UNIT_TO_STATUS: dict[str, str] = {
    VlmUnit.Status.PENDING: "pending",
    VlmUnit.Status.RUNNING: "running",
    VlmUnit.Status.COMPLETED: "completed",
    VlmUnit.Status.FAILED: "failed",
    VlmUnit.Status.CANCELLED: "cancelled",
    VlmUnit.Status.SKIPPED: "completed",
}


def evaluation_status(evaluation: Evaluation) -> str:
    """pending|running|completed|failed|cancelled; không cần Qwen ⇒ completed ngay."""
    unit = evaluation.vlm_unit
    if unit is None:
        return "completed"
    return _UNIT_TO_STATUS.get(str(unit.status), str(unit.status))


def evaluation_reason_code(evaluation: Evaluation) -> str | None:
    """reason_code theo payload FE v0: lý do định tuyến; Qwen lỗi thì mã lỗi của Qwen."""
    unit = evaluation.vlm_unit
    if (
        unit is not None
        and unit.status in (VlmUnit.Status.FAILED, VlmUnit.Status.SKIPPED)
        and unit.reason_code
    ):
        return str(unit.reason_code)
    return evaluation.primary_reason


def evaluation_review_required(evaluation: Evaluation) -> bool:
    """AI không đủ khả năng đề xuất đáng tin: crop lỗi, hết budget, Qwen lỗi hoặc uncertain."""
    if evaluation.human_review_required:
        return True
    unit = evaluation.vlm_unit
    if unit is None:
        return False
    if unit.status in (VlmUnit.Status.FAILED, VlmUnit.Status.SKIPPED):
        return True
    uncertain = (unit.result or {}).get("status") == "uncertain"
    return bool(unit.status == VlmUnit.Status.COMPLETED and uncertain)


def latest_evaluations(candidate_ids: list[int]) -> dict[int, Evaluation]:
    """Evaluation mới nhất (generation lớn nhất) của từng candidate; candidate chưa có thì vắng."""
    latest: dict[int, Evaluation] = {}
    rows = (
        Evaluation.objects.filter(candidate_id__in=candidate_ids)
        .select_related("vlm_unit__evidence")
        .order_by("candidate_id", "generation")
    )
    for evaluation in rows:
        latest[evaluation.candidate_id] = evaluation  # generation tăng dần: bản cuối thắng
    return latest


def evaluation_summary(evaluation: Evaluation | None) -> dict[str, Any] | None:
    """Tóm tắt cho danh sách candidate (BLOCKER-034 B-4): đủ để tìm lại và hỏi kết quả."""
    if evaluation is None:
        return None
    return {
        "id": evaluation.pk,
        "generation": evaluation.generation,
        "status": evaluation_status(evaluation),
    }


def evaluation_read(evaluation: Evaluation) -> dict[str, Any]:
    unit = evaluation.vlm_unit
    vlm = build_vlm_view(unit, "not_triggered") if unit is not None else None
    if vlm is not None:
        vlm["evaluation_id"] = str(evaluation.pk)
    return {
        "id": evaluation.pk,
        "candidate_id": evaluation.candidate_id,
        "run_id": evaluation.run_id,
        "generation": evaluation.generation,
        "source": evaluation.source,
        "status": evaluation_status(evaluation),
        "reason_code": evaluation_reason_code(evaluation),
        "reasons": list(evaluation.reasons),
        "review_required": evaluation_review_required(evaluation),
        "call_qwen": evaluation.call_qwen,
        "policy": evaluation.policy,
        "checkpoint_status": evaluation.checkpoint_status or None,
        "snapshot_revision": evaluation.snapshot_revision,
        "requested_by_user_id": evaluation.requested_by_id,
        "note": evaluation.note or None,
        "vlm": vlm,
        "created_at": evaluation.created_at,
        "poll_url": f"/api/candidate-evaluations/{evaluation.pk}/",
    }
