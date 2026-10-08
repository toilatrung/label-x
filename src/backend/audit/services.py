"""Transaction-bound service for appending sanitized audit events."""

from __future__ import annotations

from collections.abc import Mapping

from django.contrib.auth.models import User
from django.db import connection

from audit.models import AuditEvent
from config.logging import redact_text, redact_value


class AuditTransactionRequired(RuntimeError):
    """Raised when an audit record is not part of the operation transaction."""


def _required(value: object, field: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field} must not be empty.")
    return normalized


def _sanitize_snapshot(value: Mapping[str, object] | None) -> dict[str, object] | None:
    if value is None:
        return None
    sanitized = redact_value(dict(value))
    if not isinstance(sanitized, dict):  # pragma: no cover - dict input always remains a dict
        raise TypeError("Audit snapshots must be JSON objects.")
    return sanitized


def append_audit_event(
    *,
    actor: User,
    action: str,
    object_type: str,
    object_id: object,
    before: Mapping[str, object] | None,
    after: Mapping[str, object] | None,
    revision: object,
    reason: str = "",
) -> AuditEvent:
    """Append one sanitized event inside the caller's database transaction.

    The service deliberately does not open its own transaction. The business
    operation must own the surrounding ``transaction.atomic`` block so both
    writes commit or roll back together.
    """

    if not connection.in_atomic_block:
        raise AuditTransactionRequired(
            "append_audit_event() must run inside the operation's transaction.atomic block."
        )

    return AuditEvent.objects.create(
        actor=actor,
        action=_required(action, "action"),
        object_type=_required(object_type, "object_type"),
        object_id=_required(object_id, "object_id"),
        before=_sanitize_snapshot(before),
        after=_sanitize_snapshot(after),
        revision=_required(revision, "revision"),
        reason=redact_text(reason.strip()),
    )
