from __future__ import annotations

from django.conf import settings
from django.db import models


class Release(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"

    class GateStatus(models.TextChoices):
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed"
        NOT_CHECKED = "not_checked", "Not checked"

    run = models.ForeignKey("runs.QCRun", on_delete=models.PROTECT, related_name="releases")
    snapshot = models.ForeignKey(
        "snapshots.Snapshot", on_delete=models.PROTECT, related_name="releases"
    )
    config_version = models.ForeignKey(
        "runs.ConfigVersion", on_delete=models.PROTECT, related_name="releases"
    )
    version_tag = models.CharField(max_length=128, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    gate_status = models.CharField(
        max_length=16, choices=GateStatus.choices, default=GateStatus.NOT_CHECKED
    )
    gate = models.JSONField(null=True, blank=True)
    approved_waiver_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_releases"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_releases",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_idempotency_key = models.CharField(max_length=128, null=True, blank=True, unique=True)
    approval_note = models.TextField(blank=True)

    class Meta:
        db_table = "release"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(status="pending", approved_by__isnull=True, approved_at__isnull=True)
                    | models.Q(
                        status="approved", approved_by__isnull=False, approved_at__isnull=False
                    )
                ),
                name="release_approval_fields_consistent",
            )
        ]

    def __str__(self) -> str:
        return f"Release {self.version_tag} [{self.status}]"
