"""Mã lý do ổn định của classifier (không lộ exception thô, đường dẫn hay stderr qua API)."""

from __future__ import annotations

from enum import StrEnum


class ClassifierReason(StrEnum):
    INVALID_CROP = "invalid_crop"
    BOX_TOO_SMALL = "box_too_small"
    CHECKPOINT_UNAVAILABLE = "checkpoint_unavailable"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    NOT_CONFIGURED = "not_configured"
    TIMEOUT = "timeout"
    INFERENCE_ERROR = "inference_error"


class ClassifierRunError(Exception):
    """Cả batch không chạy được (khác với một crop hỏng); mang mã lý do ổn định."""

    def __init__(self, reason: ClassifierReason) -> None:
        super().__init__(reason.value)
        self.reason = reason
