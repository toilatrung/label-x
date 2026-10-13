"""Client DashScope (endpoint tương thích OpenAI) cho Qwen3-VL (M04A-02, CR-116).

- API key đọc từ biến môi trường tên `config.api_key_env` tại thời điểm gọi; không lưu, không log.
- Không gửi `response_format`/tham số suy luận: hỗ trợ JSON schema và chế độ suy luận của
  qwen3-vl-plus CHƯA xác minh từ tài liệu Alibaba, nên backend validate JSON ở `parse_response`.
- Mọi lỗi httpx/HTTP được đổi thành VlmProviderError; thông điệp chỉ chứa mã trạng thái và mã
  lỗi đã làm sạch, không chứa nội dung phản hồi, header hay ảnh.
- Bảng map mã HTTP → loại lỗi là giả định dựa trên quy ước OpenAI, CHƯA kiểm với provider thật.
"""

from __future__ import annotations

import base64
import os
import re
from typing import Any

import httpx

from vlm.config import ALLOWED_API_KEY_ENVS, binding_error
from vlm.contract import VlmRequest, build_prompt
from vlm.errors import VlmProviderError, VlmProviderFailure

_SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]")
MAX_REQUEST_ID_CHARS = 64
MAX_OUTPUT_TOKENS = 256
_QUOTA_HINTS = ("quota", "insufficient", "arrear", "balance", "billing")


def redact_request_id(value: object) -> str | None:
    """Giữ ký tự an toàn và cắt ngắn; ID provider chỉ dùng để đối soát, không phải secret."""
    if not isinstance(value, str) or not value:
        return None
    return _SAFE_ID.sub("", value)[:MAX_REQUEST_ID_CHARS] or None


def redact_model_id(value: object) -> str | None:
    """Model ID do provider/cổng báo về: giữ ký tự an toàn, cắt ngắn (ghi provenance)."""
    if not isinstance(value, str) or not value:
        return None
    return re.sub(r"[^A-Za-z0-9_.:/-]", "", value)[:MAX_REQUEST_ID_CHARS] or None


def _error_code(response: httpx.Response) -> str:
    """Mã lỗi từ body (nếu có) đã làm sạch; không bao giờ trả nội dung tự do."""
    try:
        body = response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        raw = error.get("code") or error.get("type")
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
    return VlmProviderError(failure, f"provider HTTP {status}" + (f" ({code})" if code else ""))


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
    """Một lần `complete` = một attempt thực gửi provider (tính budget ở tầng trên)."""

    def __init__(self, *, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    @staticmethod
    def _api_key(request: VlmRequest) -> str:
        cfg = request.config
        if cfg.api_key_env not in ALLOWED_API_KEY_ENVS:
            # Phòng thủ thêm: không bao giờ đọc biến môi trường ngoài allowlist.
            raise VlmProviderError(VlmProviderFailure.AUTH, "api_key_env không được phép")
        mismatch = binding_error(cfg.provider, cfg.host, cfg.api_key_env)
        if mismatch is not None:
            # Key của nhà cung cấp này không được gửi tới host của nhà khác; nêu đúng nguyên nhân.
            raise VlmProviderError(VlmProviderFailure.AUTH, mismatch)
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
        body = {
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
        url = cfg.base_url.rstrip("/") + "/chat/completions"
        try:
            with httpx.Client(
                timeout=cfg.timeout_seconds, transport=self._transport, follow_redirects=False
            ) as http:
                response = http.post(url, json=body, headers={"Authorization": f"Bearer {api_key}"})
        except httpx.TimeoutException:
            raise VlmProviderError(VlmProviderFailure.TIMEOUT) from None
        except httpx.HTTPError:
            raise VlmProviderError(VlmProviderFailure.NETWORK) from None
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
