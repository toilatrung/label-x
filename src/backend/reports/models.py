from __future__ import annotations

from django.db import models


class ReportExport(models.Model):
    class Format(models.TextChoices):
        PDF = "pdf", "PDF"
        CSV = "csv", "CSV"
        JSON = "json", "JSON"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    run = models.ForeignKey("runs.QCRun", on_delete=models.PROTECT, related_name="report_exports")
    format = models.CharField(max_length=8, choices=Format.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    storage_key = models.CharField(max_length=512, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    error = models.CharField(max_length=255, null=True, blank=True)  # noqa: DJ001
    idempotency_key = models.CharField(max_length=128, null=True, blank=True, unique=True)
    request_sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "report_export"
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["run", "format"], name="report_export_run_format")
        ]

    def __str__(self) -> str:
        return f"ReportExport {self.pk} ({self.run_id}/{self.format}: {self.status})"


class EffectivenessReport(models.Model):
    """Persisted KPI report; unlike RunReport it is evaluated against a reference."""

    input_snapshot = models.ForeignKey(
        "snapshots.Snapshot", on_delete=models.PROTECT, related_name="effectiveness_reports"
    )
    reference_id = models.PositiveBigIntegerField()
    source_run = models.ForeignKey(
        "runs.QCRun", on_delete=models.PROTECT, related_name="effectiveness_reports"
    )
    source_reason = models.CharField(max_length=255)
    score_version = models.CharField(max_length=64)
    metrics = models.JSONField(default=dict)
    risk_queue = models.JSONField(default=dict)
    random_queue = models.JSONField(default=dict)
    engine_coverage = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "effectiveness_report"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"EffectivenessReport {self.pk} (run={self.source_run_id})"
