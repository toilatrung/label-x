"""Persistent immutable snapshot aggregate (FR-SNP-03, FR-SNP-05, FR-SNP-06)."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models


class LockedSnapshotError(RuntimeError):
    """Raised before application code attempts to mutate a locked snapshot."""


class Snapshot(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        EXPORTING = "exporting", "Exporting"
        LOCKED = "locked", "Locked"
        FAILED = "failed", "Failed"

    dataset_id = models.PositiveBigIntegerField(db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    failure_reason = models.CharField(max_length=64, blank=True)
    parent_snapshot = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="child_snapshots",
    )
    taxonomy_version = models.CharField(max_length=128)
    guideline_version = models.CharField(max_length=128)
    schema_version = models.CharField(max_length=64)
    revision_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    normalized_json = models.JSONField(default=dict)
    provenance = models.JSONField(default=dict)
    skipped_shape_counts = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_snapshots",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    locked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["dataset_id", "status"], name="snapshot_dataset_status_idx")
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~models.Q(status="locked")
                    | (models.Q(locked_at__isnull=False) & ~models.Q(revision_sha256=""))
                ),
                name="snapshot_locked_has_hash_and_time",
            ),
            models.CheckConstraint(
                condition=~models.Q(id=models.F("parent_snapshot_id")),
                name="snapshot_parent_not_self",
            ),
        ]

    def __str__(self) -> str:
        return f"Snapshot {self.pk} ({self.status})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if (
            self.pk is not None
            and type(self).objects.filter(pk=self.pk, status=self.Status.LOCKED).exists()
        ):
            raise LockedSnapshotError("Locked snapshots cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if self.status == self.Status.LOCKED or (
            self.pk is not None
            and type(self).objects.filter(pk=self.pk, status=self.Status.LOCKED).exists()
        ):
            raise LockedSnapshotError("Locked snapshots cannot be deleted.")
        return super().delete(*args, **kwargs)


class SnapshotJob(models.Model):
    snapshot = models.ForeignKey(Snapshot, on_delete=models.CASCADE, related_name="jobs")
    cvat_job_id = models.PositiveBigIntegerField()
    cvat_task_id = models.PositiveBigIntegerField()
    assignee_cvat_user_id = models.PositiveBigIntegerField(null=True, blank=True)
    assignee_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="snapshot_job_assignments",
    )
    source_updated_at = models.CharField(max_length=64)
    sha256 = models.CharField(max_length=64)
    normalized_json = models.JSONField()
    rectangle_count = models.PositiveIntegerField(default=0)
    skipped_shape_counts = models.JSONField(default=dict)

    class Meta:
        ordering = ["cvat_job_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "cvat_job_id"],
                name="snapshot_job_unique_cvat_job",
            )
        ]

    def __str__(self) -> str:
        return f"Snapshot {self.snapshot_id} / CVAT job {self.cvat_job_id}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._assert_snapshot_mutable()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        self._assert_snapshot_mutable()
        return super().delete(*args, **kwargs)

    def _assert_snapshot_mutable(self) -> None:
        if (
            self.snapshot_id
            and Snapshot.objects.filter(pk=self.snapshot_id, status=Snapshot.Status.LOCKED).exists()
        ):
            raise LockedSnapshotError("Jobs of a locked snapshot cannot be mutated.")


class SnapshotFrame(models.Model):
    snapshot_job = models.ForeignKey(
        SnapshotJob,
        on_delete=models.CASCADE,
        related_name="frames",
    )
    frame_index = models.PositiveIntegerField()
    source_frame_id = models.PositiveBigIntegerField(null=True, blank=True)
    file_name = models.CharField(max_length=512)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    media_storage_key = models.CharField(max_length=1024)
    media_sha256 = models.CharField(max_length=64)
    media_size_bytes = models.PositiveBigIntegerField()
    media_mime_type = models.CharField(max_length=128)
    shapes = models.JSONField(default=list)
    rectangle_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["frame_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot_job", "frame_index"],
                name="snapshot_frame_unique_index",
            )
        ]

    def __str__(self) -> str:
        return f"Snapshot job {self.snapshot_job_id} / frame {self.frame_index}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._assert_snapshot_mutable()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        self._assert_snapshot_mutable()
        return super().delete(*args, **kwargs)

    def _assert_snapshot_mutable(self) -> None:
        if (
            self.snapshot_job_id
            and SnapshotJob.objects.filter(
                pk=self.snapshot_job_id,
                snapshot__status=Snapshot.Status.LOCKED,
            ).exists()
        ):
            raise LockedSnapshotError("Frames of a locked snapshot cannot be mutated.")
