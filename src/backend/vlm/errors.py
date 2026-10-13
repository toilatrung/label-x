"""Exception mapping của VLM adapter (M04A-01, CR-116).

Adapter chỉ ném các lỗi dưới đây; exception thô của thư viện HTTP không được vượt qua
ranh giới adapter. `reason_code` trùng tập reason_code của payload FE v0.
"""

from __future__ import annotations

from enum import StrEnum


class VlmReasonCode(StrEnum):
    """Tập con reason_code của payload FE v0 mà tầng VLM có thể sinh ra."""

    INVALID_CROP = "invalid_crop"
    PROVIDER_ERROR = "provider_error"
    PARSE_FAILURE = "parse_failure"
    BUDGET_EXHAUSTED = "budget_exhausted"
    DETECTOR_NO_MATCH = "detector_no_match"


class VlmProviderFailure(StrEnum):
    """Chi tiết lỗi provider (nội bộ/evidence), không phải enum công khai."""

    TIMEOUT = "timeout"
    QUOTA = "quota"
    RATE_LIMITED = "rate_limited"
    AUTH = "auth"
    BAD_REQUEST = "bad_request"
    SERVER_ERROR = "server_error"
    NETWORK = "network"


class VlmError(Exception):
    """Gốc của mọi lỗi VLM; thông điệp không chứa secret, prompt hay nội dung ảnh."""

    reason_code: VlmReasonCode = VlmReasonCode.PROVIDER_ERROR
    retryable: bool = False

    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.message = message


class VlmConfigError(VlmError):
    """Cấu hình `models.vlm` không hợp lệ (model ngoài allowlist, base_url lạ, ...)."""

    reason_code = VlmReasonCode.PROVIDER_ERROR


class VlmInvalidCropError(VlmError):
    """Crop sai MIME/kích thước/rỗng; không gọi provider."""

    reason_code = VlmReasonCode.INVALID_CROP


class VlmBudgetExhaustedError(VlmError):
    """Hết budget; không gọi provider."""

    reason_code = VlmReasonCode.BUDGET_EXHAUSTED


class VlmProviderError(VlmError):
    """Provider lỗi (timeout, quota, 5xx, mạng). `failure` cho biết loại để quyết định retry."""

    reason_code = VlmReasonCode.PROVIDER_ERROR

    def __init__(self, failure: VlmProviderFailure, message: str = "") -> None:
        super().__init__(message or failure.value)
        self.failure = failure
        self.retryable = failure in RETRYABLE_FAILURES


class VlmParseError(VlmError):
    """Phản hồi không phải JSON đúng schema nội bộ hoặc nhãn ngoài taxonomy."""

    reason_code = VlmReasonCode.PARSE_FAILURE


# Quota/auth/bad_request không retry: thử lại chỉ đốt budget mà không đổi kết quả.
RETRYABLE_FAILURES = frozenset(
    {
        VlmProviderFailure.TIMEOUT,
        VlmProviderFailure.RATE_LIMITED,
        VlmProviderFailure.SERVER_ERROR,
        VlmProviderFailure.NETWORK,
    }
)
