"""Schema cấu hình `ConfigVersion.models.vlm` (M04A-01, CR-116).

Không chứa secret: API key chỉ đọc từ biến môi trường runtime (`api_key_env`), không vào
ConfigVersion, DB, log hay evidence. Model ID phải thuộc allowlist trong source.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from vlm.errors import VlmConfigError

PROVIDER_DASHSCOPE = "dashscope"
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"
# Provider hợp lệ. `openai_compatible` = cổng tương thích OpenAI (kể cả bên thứ ba): crop ảnh đi
# qua bên trung gian nên cần PO xác nhận chính sách dữ liệu trước smoke thật.
ALLOWED_PROVIDERS = frozenset({PROVIDER_OPENAI_COMPATIBLE, PROVIDER_DASHSCOPE})
DEFAULT_MODEL = "qwen3-vl-plus"
DEFAULT_API_KEY_ENV = "VLM_API_KEY"
# Chỉ đọc biến môi trường trong allowlist: tên tuỳ ý sẽ làm lộ secret khác (DJANGO_SECRET_KEY...)
# sang host provider qua header Authorization.
ALLOWED_API_KEY_ENVS = frozenset({DEFAULT_API_KEY_ENV, "DASHSCOPE_API_KEY"})

# Allowlist model ID. Chỉ bản Instruct, không "thinking" (CR-116). Mở rộng cần change request.
# Cổng OpenAI-compatible có thể dùng định danh khác (qwen-vl-plus, qwen-vl-max, qwen3-vl-...): CHƯA
# biết ID nào hợp lệ; chỉ thêm vào tập này sau khi lấy GET /v1/models bằng key thật. Không đoán.
ALLOWED_MODELS = frozenset({"qwen3-vl-plus"})

# Allowlist host -> đường dẫn base_url duy nhất được phép (chống SSRF/gửi crop tới host lạ).
# DashScope: tên host lấy từ tài liệu Alibaba qua tìm kiếm, CHƯA xác minh region PO được dùng.
# api.shopaikey.com: cổng OpenAI-compatible bên thứ ba do PO chỉ định (qua phiên điều phối),
# KHÔNG phải DashScope trực tiếp; chưa xác minh chính sách dữ liệu hay danh sách model của cổng.
ALLOWED_BASE_URLS: dict[str, frozenset[str]] = {
    "dashscope.aliyuncs.com": frozenset({"/compatible-mode/v1"}),
    "dashscope-intl.aliyuncs.com": frozenset({"/compatible-mode/v1"}),
    "dashscope-us.aliyuncs.com": frozenset({"/compatible-mode/v1"}),
    "api.shopaikey.com": frozenset({"/v1"}),
}
ALLOWED_BASE_URL_HOSTS = frozenset(ALLOWED_BASE_URLS)

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

    @property
    def host(self) -> str:
        """Host của base_url (không secret) để ghi provenance."""
        return urlparse(self.base_url).hostname or ""

    def as_public_dict(self) -> dict[str, Any]:
        """Dạng an toàn để ghi evidence: không có secret (chỉ tên biến môi trường)."""
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "host": self.host,
            "prompt_version": self.prompt_version,
            "timeout_seconds": self.timeout_seconds,
            "max_attempts": self.max_attempts,
            "budget": {"max_calls": self.budget.max_calls},
        }


_PATH_OK = re.compile(r"^/[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$")
MIN_TIMEOUT_SECONDS = 1.0
MAX_BUDGET_CALLS = 10_000


def _base_url_errors(base_url: Any) -> list[str]:
    """base_url: https, host allowlist, KHÔNG port/userinfo/query/fragment/ký tự lạ."""
    message = (
        "models.vlm.base_url phải là https tới host trong allowlist, chỉ gồm host và đường dẫn "
        "(không port, userinfo, query, fragment, khoảng trắng hay ký tự điều khiển)."
    )
    if not isinstance(base_url, str) or not base_url.isascii() or not base_url.isprintable():
        return [message]
    if any(c in base_url for c in " \t\r\n%?#;\\@"):
        return [message]
    try:
        parsed = urlparse(base_url)
        port = parsed.port
    except ValueError:
        return [message]
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_BASE_URLS
        or parsed.netloc != parsed.hostname  # chặn userinfo và mọi port tường minh
        or port is not None
        or parsed.query
        or parsed.fragment
        or parsed.params
        or not _PATH_OK.match(parsed.path.rstrip("/"))
        or ".." in parsed.path.split("/")
        or parsed.path.rstrip("/") not in ALLOWED_BASE_URLS[parsed.hostname or ""]
    ):
        return [message]
    return []


def validate_vlm_config(raw: Mapping[str, Any]) -> list[str]:
    """Trả danh sách lỗi (rỗng nếu hợp lệ). Không ném lỗi để serializer gom được nhiều lỗi.

    Mọi giá trị đều kiểm kiểu TRƯỚC khi so sánh/`in` (giá trị list/dict không được gây TypeError).
    """
    errors: list[str] = []
    if not isinstance(raw, Mapping):
        return ["models.vlm phải là object."]
    unknown = sorted(str(k) for k in set(raw) - KNOWN_KEYS)
    if unknown:
        errors.append(f"models.vlm có khoá không hỗ trợ: {', '.join(unknown)}.")
    for key in ("api_key", "apiKey", "secret", "prompt", "system_prompt"):
        if key in raw:
            errors.append(f"models.vlm không được chứa '{key}' (secret/prompt không vào config).")
    provider = raw.get("provider")
    if not isinstance(provider, str) or provider not in ALLOWED_PROVIDERS:
        errors.append(f"models.vlm.provider phải thuộc: {sorted(ALLOWED_PROVIDERS)}.")
    model = raw.get("model")
    if not isinstance(model, str) or model not in ALLOWED_MODELS:
        errors.append(f"models.vlm.model phải thuộc allowlist: {sorted(ALLOWED_MODELS)}.")
    errors += _base_url_errors(raw.get("base_url"))
    prompt_version = raw.get("prompt_version")
    if not isinstance(prompt_version, str) or prompt_version not in PROMPT_VERSIONS:
        errors.append(f"models.vlm.prompt_version phải thuộc: {sorted(PROMPT_VERSIONS)}.")
    timeout = raw.get("timeout_seconds")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, int | float)
        or not math.isfinite(timeout)
        or not MIN_TIMEOUT_SECONDS <= timeout <= MAX_TIMEOUT_SECONDS
    ):
        errors.append(
            f"models.vlm.timeout_seconds phải trong [{MIN_TIMEOUT_SECONDS:g}, "
            f"{MAX_TIMEOUT_SECONDS:g}]."
        )
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
        or not 0 <= max_calls <= MAX_BUDGET_CALLS
    ):
        errors.append(f"models.vlm.budget phải là {{max_calls: số nguyên 0..{MAX_BUDGET_CALLS}}}.")
    env_name = raw.get("api_key_env", DEFAULT_API_KEY_ENV)
    if not isinstance(env_name, str) or env_name not in ALLOWED_API_KEY_ENVS:
        errors.append(
            f"models.vlm.api_key_env phải thuộc allowlist: {sorted(ALLOWED_API_KEY_ENVS)}."
        )
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
