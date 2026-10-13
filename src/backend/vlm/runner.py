"""Chạy một đơn vị VLM: kiểm crop → (budget → gọi → parse)×tối đa max_attempts (M04A-02).

Mỗi lần gọi provider thực là một attempt và tính budget đúng một lần, kể cả retry. Budget nguyên
tử theo DB và idempotency theo evaluation thuộc M04A-03; ở đây budget là cổng có thể thay thế.
Mọi lỗi được đổi thành VlmResult có reason_code; không ném exception thô ra ngoài.
Kết quả chỉ là đề xuất/evidence, không phải quyết định.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Protocol

from vlm.contract import (
    VlmClient,
    VlmRequest,
    VlmResult,
    VlmStatus,
    parse_response,
    validate_crop,
)
from vlm.errors import (
    VlmError,
    VlmInvalidCropError,
    VlmParseError,
    VlmProviderError,
    VlmReasonCode,
)

logger = logging.getLogger("labelx.vlm")
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_CAP_SECONDS = 20.0


class BudgetGate(Protocol):
    def try_consume(self) -> bool:
        """Giữ chỗ một lần gọi provider; False nếu hết budget."""
        ...


class CounterBudget:
    """Budget trong bộ nhớ cho một lượt logic (test/smoke); bản DB nguyên tử ở M04A-03."""

    def __init__(self, max_calls: int) -> None:
        self.remaining = max_calls
        self.used = 0

    def try_consume(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        self.used += 1
        return True


def backoff_seconds(retry_number: int) -> float:
    return float(min(BACKOFF_BASE_SECONDS * 2 ** (retry_number - 1), BACKOFF_CAP_SECONDS))


def _failed(
    request: VlmRequest,
    reason: VlmReasonCode,
    attempts: int,
    request_id: str | None = None,
) -> VlmResult:
    return VlmResult(
        status=VlmStatus.FAILED,
        reason_code=reason,
        attempts=attempts,
        request_id=request_id,
        model=request.config.model,
        prompt_version=request.config.prompt_version,
        crop_sha256=request.crop.sha256,
    )


def run_vlm_unit(
    request: VlmRequest,
    client: VlmClient,
    budget: BudgetGate,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> VlmResult:
    try:
        validate_crop(request.crop)
    except VlmInvalidCropError as exc:
        return _failed(request, exc.reason_code, 0)
    attempts = 0
    last_reason = VlmReasonCode.PROVIDER_ERROR
    request_id: str | None = None
    while attempts < request.config.max_attempts:
        if not budget.try_consume():
            # Không gọi provider khi hết budget; chuyển người review (reason rõ).
            return _failed(request, VlmReasonCode.BUDGET_EXHAUSTED, attempts, request_id)
        attempts += 1
        try:
            text, request_id = client.complete(request)
            verdict = parse_response(text, request.taxonomy)
        except VlmParseError as exc:
            # Phản hồi sai schema là kết quả của model, không retry để khỏi đốt budget.
            return _failed(request, exc.reason_code, attempts, request_id)
        except VlmProviderError as exc:
            last_reason = exc.reason_code
            logger.warning("vlm provider failure", extra={"failure": exc.failure.value})
            if not exc.retryable or attempts >= request.config.max_attempts:
                return _failed(request, last_reason, attempts, request_id)
            sleep(backoff_seconds(attempts))
            continue
        except VlmError as exc:
            return _failed(request, exc.reason_code, attempts, request_id)
        except Exception:
            # Chặn exception thô (lỗi lập trình/thư viện); chi tiết chỉ ở log, không ra API.
            logger.exception("vlm unexpected failure")
            return _failed(request, VlmReasonCode.PROVIDER_ERROR, attempts, request_id)
        return VlmResult(
            status=verdict.status,
            label=verdict.label,
            rationale=verdict.rationale,
            attempts=attempts,
            request_id=request_id,
            model=request.config.model,
            prompt_version=request.config.prompt_version,
            crop_sha256=request.crop.sha256,
        )
    return _failed(request, last_reason, attempts, request_id)
