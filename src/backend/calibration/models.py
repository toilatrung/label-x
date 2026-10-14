"""Models for Calibration and Audit Sampling (MBE-04, E-17, E-18, E-20)."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditSampleStream(models.TextChoices):
    RANDOM = "random", "Random"
    RISK = "risk", "Risk"


class AuditSample(models.Model):
    """Mẫu kiểm định (audit sample) lấy từ dữ liệu run/issue có sẵn."""

    run = models.ForeignKey("runs.QCRun", on_delete=models.PROTECT, related_name="audit_samples")
    stream = models.CharField(max_length=16, choices=AuditSampleStream.choices)
    seed = models.BigIntegerField(help_text="Seed ngẫu nhiên dùng để tái lập kết quả")
    size = models.PositiveIntegerField(help_text="Cỡ mẫu yêu cầu")
    frame_count = models.PositiveIntegerField(default=0, help_text="Số frame thực tế lấy được")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    idempotency_key = models.CharField(max_length=128, blank=True, default="", db_index=True)
    request_sha256 = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "audit_sample"
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "stream", "seed", "size"],
                name="uniq_audit_sample_run_stream_seed_size",
            ),
        ]

    def __str__(self) -> str:
        return f"AuditSample {self.pk} (run={self.run_id}, stream={self.stream}, size={self.size})"


class AuditSampleFrame(models.Model):
    """Một frame thuộc mẫu kiểm định."""

    audit_sample = models.ForeignKey(
        AuditSample, on_delete=models.CASCADE, related_name="sample_frames"
    )
    snapshot_frame = models.ForeignKey(
        "snapshots.SnapshotFrame", on_delete=models.PROTECT, related_name="+"
    )
    rank = models.PositiveIntegerField(null=True, blank=True)
    review_state = models.CharField(max_length=32)

    class Meta:
        db_table = "audit_sample_frame"
        ordering = ["rank", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["audit_sample", "snapshot_frame"],
                name="uniq_audit_sample_frame",
            ),
        ]

    def __str__(self) -> str:
        return f"AuditSampleFrame {self.pk} (sample={self.audit_sample_id})"


class BenchmarkSource(models.TextChoices):
    MANUAL = "manual", "Manual"
    CVAT_IMPORT = "cvat_import", "CVAT Import"


class BenchmarkStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"


class Benchmark(models.Model):
    """Tập tham chiếu hiệu chỉnh (benchmark)."""

    name = models.CharField(max_length=255)
    dataset_id = models.PositiveIntegerField(db_index=True)
    snapshot = models.ForeignKey(
        "snapshots.Snapshot", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    source = models.CharField(
        max_length=32, choices=BenchmarkSource.choices, default=BenchmarkSource.MANUAL
    )
    cvat_task_id = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=32, choices=BenchmarkStatus.choices, default=BenchmarkStatus.READY
    )
    frame_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    idempotency_key = models.CharField(max_length=128, blank=True, default="", db_index=True)
    request_sha256 = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "benchmark"
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["dataset_id", "cvat_task_id"],
                condition=models.Q(cvat_task_id__isnull=False),
                name="uniq_benchmark_dataset_cvat_task",
            ),
        ]

    def __str__(self) -> str:
        return f"Benchmark {self.pk} ({self.name}, status={self.status})"


class BenchmarkFrame(models.Model):
    """Frame thuộc benchmark."""

    benchmark = models.ForeignKey(
        Benchmark, on_delete=models.CASCADE, related_name="benchmark_frames"
    )
    snapshot_frame = models.ForeignKey(
        "snapshots.SnapshotFrame", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    frame_id = models.PositiveIntegerField()

    class Meta:
        db_table = "benchmark_frame"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["benchmark", "frame_id"],
                name="uniq_benchmark_frame",
            ),
        ]

    def __str__(self) -> str:
        return f"BenchmarkFrame {self.pk} (benchmark={self.benchmark_id}, frame={self.frame_id})"


class TargetKind(models.TextChoices):
    REVIEWER = "reviewer", "Reviewer"
    MODEL = "model", "Model"


class AssignmentStatus(models.TextChoices):
    ASSIGNED = "assigned", "Assigned"
    COMPLETED = "completed", "Completed"


class CalibrationAssignment(models.Model):
    """Ghi nhận giao mẫu hiệu chỉnh cho reviewer hoặc model (chỉ ghi nhận và liệt kê trong MVP)."""

    target_kind = models.CharField(max_length=16, choices=TargetKind.choices)
    target_id = models.PositiveIntegerField(help_text="user_id (reviewer) hoặc model_id (model)")
    audit_sample = models.ForeignKey(
        AuditSample, on_delete=models.PROTECT, related_name="calibration_assignments"
    )
    status = models.CharField(
        max_length=16, choices=AssignmentStatus.choices, default=AssignmentStatus.ASSIGNED
    )
    note = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    idempotency_key = models.CharField(max_length=128, blank=True, default="", db_index=True)
    request_sha256 = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "calibration_assignment"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"CalibrationAssignment {self.pk} (target={self.target_kind}:{self.target_id})"
