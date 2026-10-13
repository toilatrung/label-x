"""Celery task chạy một đơn vị VLM (M04A-02).

Payload chỉ chứa dữ liệu JSON: crop base64 (crop nhỏ ≤ 2 MiB), taxonomy, candidate context và
`models.vlm` (không secret). Task không tự retry qua Celery: retry/backoff nằm trong
`run_vlm_unit` để mỗi attempt thực đều được tính budget.

CHỈ DÙNG CHO SMOKE/TEST, KHÔNG phải đường production: budget là CounterBudget trong bộ nhớ nên
giao lại message sẽ tính lại budget và không có idempotency theo DB. Đường thật là
`orchestration.run_vlm_unit` (orchestration/vlm_stage.py: budget nguyên tử, VlmUnit idempotent,
evidence append-only). Payload mang crop base64 (≤ 2 MiB) qua broker, chỉ chấp nhận được cho
smoke; đường thật đọc crop từ storage trong worker.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any

from celery import shared_task

from vlm.client import DashScopeClient, redact_request_id
from vlm.config import parse_vlm_config
from vlm.contract import (
    CandidateContext,
    CropInput,
    TaxonomyLabel,
    VlmClient,
    VlmRequest,
    VlmResult,
)
from vlm.errors import VlmConfigError, VlmReasonCode
from vlm.runner import BudgetGate, CounterBudget, run_vlm_unit


def result_to_dict(result: VlmResult) -> dict[str, Any]:
    """Dạng JSON công khai của kết quả: không crop, không prompt, không secret."""
    return {
        "status": result.status.value,
        "label": result.label,
        "rationale": result.rationale,
        "reason_code": result.reason_code.value if result.reason_code else None,
        "attempts": result.attempts,
        # Phòng thủ tại biên public/persistence: cả client thay thế trong test hay provider mới
        # cũng không thể đưa request ID đầy đủ vào task result hoặc VlmEvidence.
        "request_id": redact_request_id(result.request_id),
        "model": result.model,
        "response_model": result.response_model,
        "provider": result.provider,
        "provider_host": result.provider_host,
        "prompt_version": result.prompt_version,
        "crop_sha256": result.crop_sha256,
    }


def _bad_payload() -> dict[str, Any]:
    return {
        "status": "failed",
        "label": None,
        "rationale": None,
        "reason_code": VlmReasonCode.INVALID_CROP.value,
        "attempts": 0,
        "request_id": None,
        "model": None,
        "response_model": None,
        "provider": None,
        "provider_host": None,
        "prompt_version": None,
        "crop_sha256": None,
    }


def evaluate_payload(
    payload: dict[str, Any],
    *,
    client: VlmClient | None = None,
    budget: BudgetGate | None = None,
) -> dict[str, Any]:
    """Dựng request từ payload và chạy; payload hỏng → failed có reason_code, không ném lỗi."""
    try:
        config = parse_vlm_config(payload["config"])
        crop = CropInput(base64.b64decode(payload["crop_b64"], validate=True), payload["mime_type"])
        taxonomy = tuple(TaxonomyLabel(t["class_id"], t["class_name"]) for t in payload["taxonomy"])
        ctx = payload["context"]
        context = CandidateContext(
            candidate_id=str(ctx["candidate_id"]),
            snapshot_revision=str(ctx["snapshot_revision"]),
            current_label=ctx.get("current_label"),
        )
    except VlmConfigError:
        out = _bad_payload()
        out["reason_code"] = VlmReasonCode.PROVIDER_ERROR.value
        return out
    except (KeyError, TypeError, ValueError, binascii.Error):
        return _bad_payload()
    request = VlmRequest(crop=crop, taxonomy=taxonomy, context=context, config=config)
    gate = budget if budget is not None else CounterBudget(config.budget.max_calls)
    return result_to_dict(run_vlm_unit(request, client or DashScopeClient(), gate))


@shared_task(name="vlm.smoke_unit", acks_late=True, reject_on_worker_lost=True)
def smoke_vlm_unit_task(payload: dict[str, Any]) -> dict[str, Any]:
    return evaluate_payload(payload)
