"""Immutable audit records (FR-SEC-05, NFR-08)."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models


class AuditImmutableError(RuntimeError):
    """Raised when application code tries to mutate an audit record."""


class AuditEvent(models.Model):
    """One append-only record for a security-sensitive operation."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    action = models.CharField(max_length=100)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=255)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    revision = models.CharField(max_length=255)
    reason = models.TextField(blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["object_type", "object_id"], name="audit_object_idx"),
            models.Index(fields=["occurred_at"], name="audit_occurred_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=~models.Q(action=""), name="audit_action_not_empty"),
            models.CheckConstraint(
                condition=~models.Q(object_type=""), name="audit_object_type_not_empty"
            ),
            models.CheckConstraint(
                condition=~models.Q(object_id=""), name="audit_object_id_not_empty"
            ),
            models.CheckConstraint(
                condition=~models.Q(revision=""), name="audit_revision_not_empty"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.object_type}:{self.object_id} @ {self.revision}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise AuditImmutableError("Audit events are append-only and cannot be updated.")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise AuditImmutableError("Audit events are append-only and cannot be deleted.")
