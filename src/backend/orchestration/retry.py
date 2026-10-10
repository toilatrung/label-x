"""Retry/backoff của shard (TBD-14 qua DEC-012/BLOCKER-014: đề xuất 3 lần, backoff mũ).

Giá trị là đề xuất chờ chốt sau pilot (BLOCKER-025); đổi ở settings `ORCHESTRATION_*`.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base_seconds: float = 2.0
    factor: float = 2.0
    cap_seconds: float = 60.0

    def backoff(self, retry_number: int) -> float:
        """Giây chờ trước lần retry thứ `retry_number` (từ 1); tất định, không jitter."""
        if retry_number < 1:
            raise ValueError("retry_number bắt đầu từ 1")
        return min(self.base_seconds * self.factor ** (retry_number - 1), self.cap_seconds)

    def exhausted(self, retries_done: int) -> bool:
        return retries_done >= self.max_retries


def default_policy() -> RetryPolicy:
    return RetryPolicy(
        max_retries=getattr(settings, "ORCHESTRATION_MAX_RETRIES", 3),
        base_seconds=getattr(settings, "ORCHESTRATION_BACKOFF_BASE_SECONDS", 2.0),
        cap_seconds=getattr(settings, "ORCHESTRATION_BACKOFF_CAP_SECONDS", 60.0),
    )
