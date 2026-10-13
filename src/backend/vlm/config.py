"""Schema cấu hình `ConfigVersion.models.vlm` (M04A-01, CR-116).

Không chứa secret: API key chỉ đọc từ biến môi trường runtime (`api_key_env`), không vào
ConfigVersion, DB, log hay evidence. Model ID phải thuộc allowlist trong source.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from vlm.errors import VlmConfigError

PROVIDER_DASHSCOPE = "dashscope"
DEFAULT_MODEL = "qwen3-vl-plus"
DEFAULT_API_KEY_ENV = "DASHSCOPE_API_KEY"

# Allowlist model ID. Chỉ bản Instruct, không "thinking" (CR-116). Mở rộng cần change request.
ALLOWED_MODELS = frozenset({"qwen3-vl-plus"})

# Allowlist host (chống SSRF/gửi crop tới host lạ). Tên host lấy từ tài liệu Alibaba Model Studio
# qua tìm kiếm; CHƯA xác minh region nào PO được phép dùng -> xem blocker/NOT VERIFIED trong report.
ALLOWED_BASE_URL_HOSTS = frozenset(
    {
        "dashscope.aliyuncs.com",
        "dashscope-intl.aliyuncs.com",
        "dashscope-us.aliyuncs.com",
    }
)

PROMPT_VERSIONS = frozenset({"vlm-prompt-v0"})

MAX_ATTEMPTS_LIMIT = 3  # tối đa 3 attempts/lượt logic (M04A-03)
MAX_TIMEOUT_SECONDS = 120.0
KNOWN_KEYS = frozenset(
    {
        "provider",
        "model",
        "base_url",
        "prompt_version",
        "timeout_seconds",
        "max_attempts",
        "budget",
        "api_key_env",
    }
)


@dataclass(frozen=True)
class VlmBudget:
    """Giới hạn số lần gọi provider thực (mỗi attempt gửi đi đều tính một lần)."""

    max_calls: int


@dataclass(frozen=True)
class VlmConfig:
    provider: str
    model: str
    base_url: str
    prompt_version: str
    timeout_seconds: float
    max_attempts: int
    budget: VlmBudget
    api_key_env: str = DEFAULT_API_KEY_ENV

    def as_public_dict(self) -> dict[str, Any]:
        """Dạng an toàn để ghi evidence: không có secret (chỉ tên biến môi trường)."""
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "prompt_version": self.prompt_version,
            "timeout_seconds": self.timeout_seconds,
            "max_attempts": self.max_attempts,
            "budget": {"max_calls": self.budget.max_calls},
        }


def validate_vlm_config(raw: Mapping[str, Any]) -> list[str]:
    """Trả danh sách lỗi (rỗng nếu hợp lệ). Không ném lỗi để serializer gom được nhiều lỗi."""
    errors: list[str] = []
    if not isinstance(raw, Mapping):
        return ["models.vlm phải là object."]
    unknown = sorted(set(raw) - KNOWN_KEYS)
    if unknown:
        errors.append(f"models.vlm có khoá không hỗ trợ: {', '.join(unknown)}.")
    for key in ("api_key", "apiKey", "secret", "prompt", "system_prompt"):
        if key in raw:
            errors.append(f"models.vlm không được chứa '{key}' (secret/prompt không vào config).")
    if raw.get("provider") != PROVIDER_DASHSCOPE:
        errors.append(f"models.vlm.provider phải là '{PROVIDER_DASHSCOPE}'.")
    model = raw.get("model")
    if model not in ALLOWED_MODELS:
        errors.append(f"models.vlm.model phải thuộc allowlist: {sorted(ALLOWED_MODELS)}.")
    base_url = raw.get("base_url")
    parsed = urlparse(base_url) if isinstance(base_url, str) else None
    if (
        parsed is None
        or parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_BASE_URL_HOSTS
        or parsed.username
        or parsed.password
    ):
        errors.append(
            "models.vlm.base_url phải là https tới host trong allowlist, không có userinfo."
        )
    if raw.get("prompt_version") not in PROMPT_VERSIONS:
        errors.append(f"models.vlm.prompt_version phải thuộc: {sorted(PROMPT_VERSIONS)}.")
    timeout = raw.get("timeout_seconds")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, int | float)
        or not 0 < timeout <= MAX_TIMEOUT_SECONDS
    ):
        errors.append(f"models.vlm.timeout_seconds phải trong (0, {MAX_TIMEOUT_SECONDS:g}].")
    attempts = raw.get("max_attempts")
    if (
        not isinstance(attempts, int)
        or isinstance(attempts, bool)
        or not 1 <= attempts <= MAX_ATTEMPTS_LIMIT
    ):
        errors.append(f"models.vlm.max_attempts phải là số nguyên 1..{MAX_ATTEMPTS_LIMIT}.")
    budget = raw.get("budget")
    max_calls = budget.get("max_calls") if isinstance(budget, Mapping) else None
    if (
        not isinstance(budget, Mapping)
        or set(budget) != {"max_calls"}
        or not isinstance(max_calls, int)
        or isinstance(max_calls, bool)
        or max_calls < 0
    ):
        errors.append("models.vlm.budget phải là {max_calls: số nguyên >= 0}.")
    env_name = raw.get("api_key_env", DEFAULT_API_KEY_ENV)
    if not isinstance(env_name, str) or not env_name.replace("_", "").isalnum() or not env_name:
        errors.append("models.vlm.api_key_env phải là tên biến môi trường hợp lệ.")
    return errors


def parse_vlm_config(raw: Mapping[str, Any]) -> VlmConfig:
    """Dựng VlmConfig đã kiểm; ném VlmConfigError (không kèm giá trị nhạy cảm)."""
    errors = validate_vlm_config(raw)
    if errors:
        raise VlmConfigError(" ".join(errors))
    return VlmConfig(
        provider=raw["provider"],
        model=raw["model"],
        base_url=raw["base_url"],
        prompt_version=raw["prompt_version"],
        timeout_seconds=float(raw["timeout_seconds"]),
        max_attempts=int(raw["max_attempts"]),
        budget=VlmBudget(max_calls=int(raw["budget"]["max_calls"])),
        api_key_env=raw.get("api_key_env", DEFAULT_API_KEY_ENV),
    )
