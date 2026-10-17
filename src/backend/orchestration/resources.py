"""DB-backed endpoint admission and cooldown. No transaction spans a network request."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from random import SystemRandom

from django.db import transaction
from django.utils import timezone

from orchestration.models import ResourceLease


def retry_delay(seconds: float) -> float:
    """Bounded jitter spreads wakeups without retrying before Retry-After."""
    return min(120, max(1, seconds) * SystemRandom().uniform(1.0, 1.2))


class ResourceWaiting(Exception):
    def __init__(self, seconds: float = 5, code: str = "waiting_resource") -> None:
        self.seconds = max(1, min(seconds, 120))
        self.code = code
        super().__init__(code)


class EndpointLease:
    def __init__(self, endpoint: str, seconds: float) -> None:
        self.key = hashlib.sha256(endpoint.rstrip("/").encode()).hexdigest()
        self.seconds = seconds
        self.owner = uuid.uuid4().hex
        self.acquired = False
        self.delay = 0.0
        self.error_code = ""
        self.uncertain = False

    def __enter__(self) -> EndpointLease:
        ResourceLease.objects.get_or_create(key=self.key)
        with transaction.atomic():
            row = ResourceLease.objects.select_for_update().get(pk=self.key)
            now = timezone.now()
            if row.retry_at and row.retry_at > now:
                raise ResourceWaiting((row.retry_at - now).total_seconds(), row.error_code)
            if row.owner and row.expires_at and row.expires_at > now:
                raise ResourceWaiting(5)
            row.owner = self.owner
            row.expires_at = now + timedelta(seconds=self.seconds)
            row.save(update_fields=["owner", "expires_at"])
        self.acquired = True
        return self

    def failed(self, code: str, *, retry_after: float = 0, uncertain: bool = False) -> None:
        self.error_code = code
        self.delay = max(2, min(retry_after, 120))
        self.uncertain = uncertain

    def __exit__(self, *args: object) -> None:
        if not self.acquired:
            return
        with transaction.atomic():
            row = ResourceLease.objects.select_for_update().get(pk=self.key)
            if row.owner != self.owner:
                return
            now = timezone.now()
            if self.error_code:
                row.failures = min(row.failures + 1, 10)
                delay = max(self.delay, min(2**row.failures, 120))
                row.retry_at = now + timedelta(seconds=delay)
                # A timed-out client cannot establish whether remote inference has ended.
                if self.uncertain and row.expires_at:
                    row.retry_at = max(row.retry_at, row.expires_at)
                row.error_code = self.error_code
            else:
                row.failures = 0
                row.retry_at = None
                row.error_code = ""
            row.owner = ""
            row.expires_at = None
            row.save()
