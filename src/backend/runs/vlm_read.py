"""Read model VLM của candidate (M04A-04): phân biệt disabled/no_model/not_triggered/failed.

`state` là trạng thái tổng hợp duy nhất mà FE cần; `engine_status`, `conclusion`, `reason_code`
bám payload FE v0. Kết quả VLM chỉ là đề xuất (conclusion) và lời giải thích của model không phải
bằng chứng đã xác minh; không có quyết định review nào được tạo ở đây.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from orchestration.models import VlmEvidence, VlmUnit
from runs.models import EngineResult, QCRun

NOT_CHECKED_STATES = frozenset({"disabled", "no_model", "not_applicable", "not_triggered"})


def run_vlm_engine_state(run_id: int) -> str:
    """Trạng thái engine vlm của run khi candidate chưa có VlmUnit."""
    result = EngineResult.objects.filter(run_id=run_id, engine="vlm").first()
    if result is None:
        return "disabled"  # config của run không có engine vlm
    if result.status == "not_checked" and result.reason in NOT_CHECKED_STATES:
        return str(result.reason)
    if result.status == "running":
        run_status = QCRun.objects.filter(pk=run_id).values_list("status", flat=True).first()
        return "pending" if run_status in ("queued", "running") else "not_triggered"
    return "not_triggered"


def load_candidate_units(candidate_ids: Iterable[int]) -> dict[int, VlmUnit]:
    """VlmUnit mới nhất (generation lớn nhất) của mỗi candidate, kèm evidence."""
    units: dict[int, VlmUnit] = {}
    rows = (
        VlmUnit.objects.filter(candidate_id__in=list(candidate_ids))
        .select_related("evidence")
        .order_by("candidate_id", "evaluation_generation", "id")
    )
    for unit in rows:
        units[unit.candidate_id] = unit  # generation tăng dần: bản cuối thắng
    return units


def _engine_status(state: str) -> str:
    if state in ("checked", "uncertain"):
        return "checked"
    if state == "failed":
        return "failed"
    if state in ("pending", "running"):
        return "running"
    return "not_checked"


def build_vlm_view(unit: VlmUnit | None, engine_state: str) -> dict[str, Any]:
    state = engine_state
    evidence: VlmEvidence | None = None
    if unit is not None:
        evidence = (
            getattr(unit, "evidence", None) if unit.status in ("completed", "failed") else None
        )
        if unit.status == VlmUnit.Status.COMPLETED:
            state = (evidence.status if evidence else None) or (unit.result or {}).get(
                "status", "checked"
            )
        elif unit.status == VlmUnit.Status.FAILED:
            state = "failed"
        elif unit.status == VlmUnit.Status.CANCELLED:
            state = "cancelled"
        else:
            state = str(unit.status)  # pending | running
    conclusion = {"checked": "confirmed", "uncertain": "uncertain"}.get(state)
    return {
        "state": state,
        "engine_status": _engine_status(state),
        "source": "qwen",
        "conclusion": conclusion,
        "class_id": (evidence.label_class_id or None) if evidence else None,
        "class_name": (evidence.class_name or None) if evidence else None,
        "reason_code": (unit.reason_code or None) if unit is not None else None,
        "evidence_id": evidence.pk if evidence else None,
        "evaluation_id": None,  # tài nguyên evaluation do M04C-02 định nghĩa
        "model_version": (evidence.model if evidence else (unit.model if unit else None)),
        "provider": (evidence.provider or None) if evidence else None,
        "provider_host": (evidence.provider_host or None) if evidence else None,
        "response_model": (evidence.response_model or None) if evidence else None,
        "prompt_version": (
            evidence.prompt_version if evidence else (unit.prompt_version if unit else None)
        ),
        "policy_version": (
            evidence.policy_version if evidence else (unit.policy_version if unit else None)
        ),
        "snapshot_revision": (evidence.snapshot_revision or None) if evidence else None,
        "attempts": (evidence.attempts if evidence else (unit.attempts if unit else 0)),
        "request_id": (evidence.request_id or None) if evidence else None,
        "crop_sha256": (evidence.crop_sha256 or None) if evidence else None,
        "crop": evidence.crop_origin if evidence else None,
        "rationale": (evidence.rationale or None) if evidence else None,
        "created_at": evidence.created_at if evidence else None,
    }
