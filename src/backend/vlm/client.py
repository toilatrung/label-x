"""Client VLM tương thích OpenAI cho Qwen và Gemini.

- API key lấy từ kết nối mã hóa hoặc biến môi trường `config.api_key_env`; không log.
- Qwen không nhận `response_format`/tham số suy luận. Gemini dùng reasoning_effort theo
  tài liệu Google; cả hai được backend validate JSON ở `parse_response`.
- Mọi lỗi httpx/HTTP được đổi thành VlmProviderError; thông điệp chỉ chứa mã trạng thái và mã
  lỗi đã làm sạch, không chứa nội dung phản hồi, header hay ảnh.
- Bảng map mã HTTP → loại lỗi là giả định dựa trên quy ước OpenAI, CHƯA kiểm với provider thật.
"""

from __future__ import annotations

import base64
import logging
import os
import re
from typing import Any

import httpx

from engines.worker_adapter.client import retry_after_seconds
from vlm.config import ALLOWED_API_KEY_ENVS, GEMINI_MODELS, binding_error
from vlm.contract import VlmRequest, build_prompt
from vlm.errors import VlmProviderError, VlmProviderFailure

logger = logging.getLogger("labelx.vlm")

_SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]")
REQUEST_ID_SUFFIX_CHARS = 8
MAX_MODEL_ID_CHARS = 64
MAX_OUTPUT_TOKENS = 256
GEMINI_MAX_OUTPUT_TOKENS = 4096  # Bao gồm thinking tokens trước JSON kết quả.
_QUOTA_HINTS = ("quota", "insufficient", "arrear", "balance", "billing")


def redact_request_id(value: object) -> str | None:
    """Chỉ giữ hậu tố an toàn để đối soát mà không lộ toàn bộ ID của provider."""
    if not isinstance(value, str) or not value:
        return None
    cleaned = _SAFE_ID.sub("", value)
    return f"…{cleaned[-REQUEST_ID_SUFFIX_CHARS:]}" if cleaned else None


def redact_model_id(value: object) -> str | None:
    """Model ID do provider/cổng báo về: giữ ký tự an toàn, cắt ngắn (ghi provenance)."""
    if not isinstance(value, str) or not value:
        return None
    return re.sub(r"[^A-Za-z0-9_.:/-]", "", value)[:MAX_MODEL_ID_CHARS] or None


def _error_code(response: httpx.Response) -> str:
    """Mã lỗi từ body (nếu có) đã làm sạch; không bao giờ trả nội dung tự do."""
    try:
        body = response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        raw = error.get("code")
        if not isinstance(raw, str) or not raw:
            raw = error.get("status") or error.get("type")
        if isinstance(raw, str):
            return _SAFE_ID.sub("", raw)[:64].lower()
    return ""


def classify_http_error(response: httpx.Response) -> VlmProviderError:
    status = response.status_code
    code = _error_code(response)
    if status in (401, 403):
        failure = VlmProviderFailure.AUTH
    elif status == 402 or (status == 429 and any(h in code for h in _QUOTA_HINTS)):
        failure = VlmProviderFailure.QUOTA
    elif status == 429:
        failure = VlmProviderFailure.RATE_LIMITED
    elif status in (408, 504):
        failure = VlmProviderFailure.TIMEOUT
    elif status >= 500:
        failure = VlmProviderFailure.SERVER_ERROR
    else:
        failure = VlmProviderFailure.BAD_REQUEST
    delay = retry_after_seconds(response)
    return VlmProviderError(
        failure, f"provider HTTP {status}" + (f" ({code})" if code else ""), retry_after=delay
    )


def _content_text(payload: Any) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ValueError("thiếu choices[0].message.content") from None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [p.get("text", "") for p in content if isinstance(p, dict)]
        return "".join(p for p in parts if isinstance(p, str))
    raise ValueError("content sai kiểu")


class DashScopeClient:
    """Qwen/Gemini qua chat completions; giữ tên cũ để tương thích các worker.

    Một lần `complete` = một attempt thực gửi provider (tính budget ở tầng trên).
    """

    def __init__(self, *, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    @staticmethod
    def _api_key(request: VlmRequest) -> str:
        cfg = request.config
        if cfg.api_key_env not in ALLOWED_API_KEY_ENVS:
            # Phòng thủ thêm: không bao giờ đọc biến môi trường ngoài allowlist.
            raise VlmProviderError(VlmProviderFailure.AUTH, "api_key_env không được phép")
        mismatch = binding_error(cfg.provider, cfg.host, cfg.api_key_env, cfg.model)
        if mismatch is not None:
            # Key của nhà cung cấp này không được gửi tới host của nhà khác; nêu đúng nguyên nhân.
            raise VlmProviderError(VlmProviderFailure.AUTH, mismatch)
        if cfg.connection_id is not None:
            from vlm.connection import connection_api_key

            return connection_api_key(cfg)
        api_key = os.environ.get(cfg.api_key_env, "")
        if not api_key:
            # Thiếu credential: lỗi xác thực cố định, không retry và không gọi mạng.
            raise VlmProviderError(VlmProviderFailure.AUTH, "thiếu API key trong môi trường")
        return api_key

    def preflight(self, request: VlmRequest) -> None:
        self._api_key(request)

    def complete(self, request: VlmRequest) -> tuple[str, str | None, str | None]:
        cfg = request.config
        api_key = self._api_key(request)
        prompt = build_prompt(cfg.prompt_version, request.taxonomy, request.context)
        data_url = (
            f"data:{request.crop.mime_type};base64,"
            f"{base64.b64encode(request.crop.data).decode('ascii')}"
        )
        body: dict[str, Any] = {
            "model": cfg.model,
            "temperature": 0,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }
        if cfg.model in GEMINI_MODELS:
            # Gemini 3/2.5 Pro cần chỗ cho reasoning, nếu dùng 256 tokens của Qwen thì
            # có thể hết budget trước khi có JSON. Google khuyến nghị giữ temperature mặc định.
            body.pop("temperature")
            body["max_tokens"] = GEMINI_MAX_OUTPUT_TOKENS
            body["reasoning_effort"] = "none" if cfg.model == "gemini-2.5-flash" else "low"
        url = cfg.base_url.rstrip("/") + "/chat/completions"
        try:
            with httpx.Client(
                timeout=cfg.timeout_seconds, transport=self._transport, follow_redirects=False
            ) as http:
                logger.info(
                    "vlm provider request starting",
                    extra={
                        "provider": cfg.provider,
                        "model": cfg.model,
                        "qc_run_id": request.context.run_id,
                        "vlm_unit_id": request.context.unit_id,
                    },
                )
                response = http.post(url, json=body, headers={"Authorization": f"Bearer {api_key}"})
        except httpx.TimeoutException:
            raise VlmProviderError(VlmProviderFailure.TIMEOUT) from None
        except httpx.HTTPError:
            raise VlmProviderError(VlmProviderFailure.NETWORK) from None
        logger.info(
            "vlm provider response received",
            extra={
                "provider": cfg.provider,
                "http_status": response.status_code,
                "qc_run_id": request.context.run_id,
                "vlm_unit_id": request.context.unit_id,
            },
        )
        if response.status_code != 200:
            raise classify_http_error(response)
        try:
            payload = response.json()
            text = _content_text(payload)
        except ValueError:
            # 200 nhưng không phải JSON OpenAI hợp lệ: coi là lỗi server tạm thời.
            raise VlmProviderError(
                VlmProviderFailure.SERVER_ERROR, "phản hồi sai định dạng"
            ) from None
        request_id = response.headers.get("x-request-id") or (
            payload.get("id") if isinstance(payload, dict) else None
        )
        reported = payload.get("model") if isinstance(payload, dict) else None
        return text, redact_request_id(request_id), redact_model_id(reported)
