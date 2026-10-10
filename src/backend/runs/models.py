"""QC Run, Sharding and Engine Lifecycle domain models (T-024, E-08, Issue #66)."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models as dj_models


class PublishedConfigImmutableError(ValidationError):
    """Raised when attempting to modify a published ConfigVersion."""


class ConfigVersion(dj_models.Model):
    """Versioned configuration for QC engines and thresholds (FR-ENG-01, schema.html)."""

    class Status(dj_models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    name = dj_models.CharField(max_length=128, default="default")
    status = dj_models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    payload = dj_models.JSONField(default=dict)
    engines = dj_models.JSONField(default=dict)
    thresholds = dj_models.JSONField(default=dict)
    models = dj_models.JSONField(default=dict)
    idempotency_key = dj_models.CharField(max_length=128, unique=True, null=True, blank=True)
    request_sha256 = dj_models.CharField(max_length=64, blank=True, default="")
    created_by = dj_models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=dj_models.PROTECT,
        null=True,
        blank=True,
        related_name="created_config_versions",
    )
    created_at = dj_models.DateTimeField(auto_now_add=True)
    published_by = dj_models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=dj_models.PROTECT,
        null=True,
        blank=True,
        related_name="published_config_versions",
    )
    published_at = dj_models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "config_version"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"ConfigVersion {self.pk} ({self.name}: {self.status})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            existing = ConfigVersion.objects.filter(pk=self.pk).values("status").first()
            if existing and existing["status"] == self.Status.PUBLISHED:
                if self.status != self.Status.PUBLISHED:
                    raise PublishedConfigImmutableError(
                        "Cannot unpublish a published configuration."
                    )
        super().save(*args, **kwargs)


class ModelArtifact(dj_models.Model):
    """Registered AI model artifact with immutable checksum (FR-ENG-05, SRS §9.4)."""

    name = dj_models.CharField(max_length=128)
    version = dj_models.CharField(max_length=64)
    checksum = dj_models.CharField(max_length=64, unique=True)
    class_mapping_version = dj_models.CharField(max_length=64, blank=True, default="")
    class_mapping = dj_models.JSONField(default=dict)
    artifact_key = dj_models.CharField(max_length=512, blank=True, default="")
    created_at = dj_models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "model_artifact"
        ordering = ["name", "version"]
        constraints = [
            dj_models.UniqueConstraint(
                fields=["name", "version"], name="model_artifact_unique_name_version"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name}:{self.version} ({self.checksum[:8]})"


class QCRun(dj_models.Model):
    """Aggregate root for a QC inspection run (FR-ENG-01, FR-AGG-02, state-machines §2)."""

    class Status(dj_models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    snapshot = dj_models.ForeignKey(
        "snapshots.Snapshot",
        on_delete=dj_models.PROTECT,
        related_name="qc_runs",
    )
    config_version = dj_models.ForeignKey(
        ConfigVersion,
        on_delete=dj_models.PROTECT,
        related_name="qc_runs",
    )
    model_artifact = dj_models.ForeignKey(
        ModelArtifact,
        null=True,
        blank=True,
        on_delete=dj_models.PROTECT,
        related_name="qc_runs",
    )
    seed = dj_models.BigIntegerField(default=42)
    engine_versions = dj_models.JSONField(default=dict)
    status = dj_models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    is_final = dj_models.BooleanField(default=False)
    origin_run = dj_models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=dj_models.PROTECT,
        related_name="rework_runs",
    )
    dataset_id = dj_models.PositiveBigIntegerField(db_index=True)
    scope_hash = dj_models.CharField(max_length=64, db_index=True)
    score_version = dj_models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001
    cancel_requested_at = dj_models.DateTimeField(null=True, blank=True)
    next_step_enqueued_at = dj_models.DateTimeField(null=True, blank=True)
    claimed_at = dj_models.DateTimeField(null=True, blank=True)
    created_by = dj_models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=dj_models.PROTECT,
        related_name="created_qc_runs",
    )
    created_at = dj_models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = dj_models.DateTimeField(null=True, blank=True)
    finished_at = dj_models.DateTimeField(null=True, blank=True)

    # HTTP request idempotency
    idempotency_key = dj_models.CharField(max_length=128, null=True, blank=True, db_index=True)  # noqa: DJ001
    request_sha256 = dj_models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = "qc_run"
        ordering = ["-created_at", "-id"]
        indexes = [
            dj_models.Index(fields=["dataset_id", "status"], name="qc_run_dataset_status_idx"),
            dj_models.Index(fields=["snapshot", "status"], name="qc_run_snapshot_status_idx"),
        ]
        constraints = [
            dj_models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=dj_models.Q(idempotency_key__isnull=False),
                name="qc_run_unique_idempotency_key",
            ),
            dj_models.UniqueConstraint(
                fields=["dataset_id", "scope_hash"],
                condition=dj_models.Q(is_final=True, status__in=["queued", "running"]),
                name="qc_run_unique_active_final_scope",
            ),
            dj_models.CheckConstraint(
                condition=~dj_models.Q(id=dj_models.F("origin_run_id")),
                name="qc_run_origin_not_self",
            ),
        ]

    def __str__(self) -> str:
        return f"QCRun {self.pk} [{self.status}] (snapshot={self.snapshot_id})"


class WorkUnit(dj_models.Model):
    """Deterministic work unit / shard allocated to an engine (FR-AGG-02, schema.html)."""

    class Status(dj_models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    run = dj_models.ForeignKey(
        QCRun,
        on_delete=dj_models.CASCADE,
        related_name="work_units",
    )
    engine = dj_models.CharField(max_length=64, db_index=True)
    shard_key = dj_models.CharField(max_length=128)
    shard_index = dj_models.PositiveIntegerField(default=0)
    idempotency_key = dj_models.CharField(max_length=64, db_index=True)
    status = dj_models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    attempt = dj_models.PositiveIntegerField(default=1)
    last_error = dj_models.TextField(blank=True, default="")
    started_at = dj_models.DateTimeField(null=True, blank=True)
    finished_at = dj_models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "work_unit"
        ordering = ["shard_index", "id"]
        constraints = [
            dj_models.UniqueConstraint(
                fields=["run", "idempotency_key"],
                name="work_unit_unique_run_idempotency",
            ),
            dj_models.UniqueConstraint(
                fields=["run", "engine", "shard_key"],
                name="work_unit_unique_run_engine_shard",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"WorkUnit {self.pk} (run={self.run_id}, engine={self.engine}, shard={self.shard_key})"
        )


class EngineResult(dj_models.Model):
    """Engine summary outcome within a QC run (FR-AGG-04, FR-AGG-05, schema.html)."""

    run = dj_models.ForeignKey(
        QCRun,
        on_delete=dj_models.CASCADE,
        related_name="engine_results",
    )
    engine = dj_models.CharField(max_length=64)
    status = dj_models.CharField(max_length=32, default="running")
    reason = dj_models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001
    eligible_units = dj_models.IntegerField(default=0)
    completed_units = dj_models.IntegerField(default=0)
    failed_units = dj_models.IntegerField(default=0)
    not_checked_units = dj_models.IntegerField(default=0)
    required = dj_models.BooleanField(default=True)
    unit = dj_models.CharField(max_length=16, default="frame")
    applicability_version = dj_models.CharField(max_length=64, default="1.0.0")

    class Meta:
        db_table = "engine_result"
        ordering = ["engine"]
        constraints = [
            dj_models.UniqueConstraint(
                fields=["run", "engine"],
                name="engine_result_unique_run_engine",
            ),
        ]

    def __str__(self) -> str:
        return f"EngineResult (run={self.run_id}, engine={self.engine}: {self.status})"


class RunRanking(dj_models.Model):
    """One immutable, source-separated ordering produced for a QC run."""

    class Source(dj_models.TextChoices):
        RISK = "risk", "Risk"
        RANDOM_AUDIT = "random_audit", "Random audit"
        RANDOM_CONTROL = "random_control", "Random control"
        ANNOTATION_COUNT_CONTROL = "annotation_count_control", "Annotation count control"
        MAX_CONFIDENCE_CONTROL = "max_confidence_control", "Max confidence control"

    run = dj_models.ForeignKey(QCRun, on_delete=dj_models.CASCADE, related_name="rankings")
    source = dj_models.CharField(max_length=32, choices=Source.choices)
    seed = dj_models.BigIntegerField()
    score_version = dj_models.CharField(max_length=64)
    content_hash = dj_models.CharField(max_length=64)
    ranking_hash = dj_models.CharField(max_length=64)
    created_at = dj_models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "run_ranking"
        ordering = ["source"]
        constraints = [
            dj_models.UniqueConstraint(
                fields=["run", "source"], name="run_ranking_unique_run_source"
            )
        ]

    def __str__(self) -> str:
        return f"RunRanking (run={self.run_id}, source={self.source})"


class RunRankingEntry(dj_models.Model):
    """Persisted frame position and explanation within one run ordering."""

    ranking = dj_models.ForeignKey(RunRanking, on_delete=dj_models.CASCADE, related_name="entries")
    snapshot_frame = dj_models.ForeignKey(
        "snapshots.SnapshotFrame",
        on_delete=dj_models.PROTECT,
        related_name="ranking_entries",
    )
    rank = dj_models.PositiveIntegerField()
    score = dj_models.DecimalField(max_digits=30, decimal_places=12)
    baseline_score = dj_models.DecimalField(max_digits=30, decimal_places=12)
    missing_evidence = dj_models.BooleanField(default=False)
    issue_counts = dj_models.JSONField(default=dict)
    explanation = dj_models.JSONField(default=dict)
    tie_break_hash = dj_models.CharField(max_length=64)
    source_value = dj_models.DecimalField(max_digits=30, decimal_places=12, null=True, blank=True)

    class Meta:
        db_table = "run_ranking_entry"
        ordering = ["rank"]
        indexes = [dj_models.Index(fields=["ranking", "rank"], name="run_rank_entry_order_idx")]
        constraints = [
            dj_models.UniqueConstraint(
                fields=["ranking", "snapshot_frame"],
                name="run_rank_entry_unique_frame",
            ),
            dj_models.UniqueConstraint(
                fields=["ranking", "rank"], name="run_rank_entry_unique_rank"
            ),
            dj_models.CheckConstraint(
                condition=dj_models.Q(rank__gte=1), name="run_rank_entry_rank_positive"
            ),
        ]

    def __str__(self) -> str:
        return f"RunRankingEntry (ranking={self.ranking_id}, rank={self.rank})"
