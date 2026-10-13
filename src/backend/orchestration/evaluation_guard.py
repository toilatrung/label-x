"""Guard idempotency + revision cho evaluation/re-evaluate (M04C-02, CR-115).

Hàm thuần, không DB và không đoán schema evidence: view/service của #289 gọi vào đây
trước khi ghi. Quy tắc:
- revision cũ → 409 (StaleRevisionError), không ghi gì;
- cùng Idempotency-Key + cùng payload + cùng người → replay (trả evaluation cũ);
- cùng key khác payload hoặc khác người → 409 (EvaluationKeyReusedError);
- manual recheck với key mới luôn tạo evaluation mới, dù revision/model không đổi.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

MAX_KEY_LENGTH = 128
MAX_REASON_LENGTH = 500


class EvaluationGuardError(Exception):
    """Lỗi domain của guard; view ánh xạ sang ApiError."""


class StaleRevisionError(EvaluationGuardError):
    """expected_revision không còn là revision hiện tại của snapshot."""


class EvaluationKeyReusedError(EvaluationGuardError):
    """Idempotency-Key đã dùng cho payload hoặc người khác."""


class InvalidIdempotencyKeyError(EvaluationGuardError):
    """Idempotency-Key trống hoặc quá dài."""


class IdempotencyOutcome(StrEnum):
    CREATE = "create"
    REPLAY = "replay"


@dataclass(frozen=True)
class EvaluationRequest:
    """Payload FE được phép gửi: chỉ reason + revision; không prompt/model/ảnh/key API."""

    candidate_id: int
    reason: str
    expected_revision: str

    def digest(self) -> str:
        body = {
            "candidate_id": self.candidate_id,
            "reason": self.reason,
            "expected_revision": self.expected_revision,
        }
        return hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def validate_idempotency_key(key: str | None) -> str:
    cleaned = (key or "").strip()
    if not cleaned or len(cleaned) > MAX_KEY_LENGTH:
        raise InvalidIdempotencyKeyError(f"Idempotency-Key phải có 1–{MAX_KEY_LENGTH} ký tự.")
    return cleaned


def check_revision(*, expected_revision: str, current_revision: str) -> None:
    if expected_revision != current_revision:
        raise StaleRevisionError("Revision đã thay đổi; tải lại candidate rồi gửi lại.")


def resolve_idempotency(
    *,
    existing_digest: str | None,
    existing_actor_id: int | None,
    request_digest: str,
    actor_id: int,
) -> IdempotencyOutcome:
    """`existing_*` là None khi key chưa có evaluation."""
    if existing_digest is None:
        return IdempotencyOutcome.CREATE
    if existing_digest != request_digest or existing_actor_id != actor_id:
        raise EvaluationKeyReusedError("Idempotency-Key đã được dùng với yêu cầu khác.")
    return IdempotencyOutcome.REPLAY
