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
    if unit is not None and unit.status == VlmUnit.Status.FAILED and unit.reason_code:
        return str(unit.reason_code)
    return evaluation.primary_reason


def evaluation_review_required(evaluation: Evaluation) -> bool:
    """AI không đủ khả năng đề xuất đáng tin: crop lỗi, hết budget, Qwen lỗi hoặc uncertain."""
    if evaluation.human_review_required:
        return True
    unit = evaluation.vlm_unit
    if unit is None:
        return False
    if unit.status == VlmUnit.Status.FAILED:
        return True
    uncertain = (unit.result or {}).get("status") == "uncertain"
    return bool(unit.status == VlmUnit.Status.COMPLETED and uncertain)


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
        "poll_url": f"/api/evaluations/{evaluation.pk}/",
    }
