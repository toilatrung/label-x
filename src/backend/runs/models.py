"""QC Run, Sharding and Engine Lifecycle domain models (T-024, E-08, archived issue 66)."""

# Historical issue mapping: docs/08-devops/github-issue-migration-2026-10-17.html
# Anchors: issue-66.

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


class VlmConnection(dj_models.Model):
    """Immutable connection version; credentials never enter QC config or API responses."""

    config = dj_models.JSONField(default=dict)
    encrypted_api_key = dj_models.TextField()
    confidence_threshold = dj_models.FloatField(default=0.85)
    created_at = dj_models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vlm_connection"
        constraints = [
            dj_models.CheckConstraint(
                condition=dj_models.Q(confidence_threshold__gte=0)
                & dj_models.Q(confidence_threshold__lte=1),
                name="vlm_connection_confidence_range",
            ),
        ]

    def __str__(self) -> str:
        return f"VLM connection {self.pk}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None and VlmConnection.objects.filter(pk=self.pk).exists():
            raise ValidationError("Kết nối VLM đã lưu không được sửa trực tiếp.")
        super().save(*args, **kwargs)


class VlmConfiguration(dj_models.Model):
    """Singleton pointer, locked when replacing the current connection."""

    connection = dj_models.ForeignKey(VlmConnection, null=True, on_delete=dj_models.PROTECT)

    class Meta:
        db_table = "vlm_configuration"

    def __str__(self) -> str:
        return "VLM configuration"


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


class GpuWorkerConfig(dj_models.Model):
    """Append-only configuration revisions. Credentials live only in server environment."""

    name = dj_models.CharField(max_length=128)
    url = dj_models.URLField(max_length=255)
    credential_ref = dj_models.CharField(max_length=64)
    enabled = dj_models.BooleanField(default=True)
    timeout_seconds = dj_models.PositiveIntegerField(default=120)
    created_at = dj_models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.name} (revision {self.pk})"


class GpuWorkerSelection(dj_models.Model):
    """Singleton pointer; updating it never changes a running run's revision."""

    config = dj_models.ForeignKey(GpuWorkerConfig, on_delete=dj_models.PROTECT, null=True)

    def __str__(self) -> str:
        return f"GPU Worker selection: {self.config_id}"


class RunGpuWorker(dj_models.Model):
    run = dj_models.OneToOneField("QCRun", on_delete=dj_models.CASCADE)
    config = dj_models.ForeignKey(GpuWorkerConfig, on_delete=dj_models.PROTECT, null=True)

    def __str__(self) -> str:
        return f"Run {self.run_id}: GPU Worker revision {self.config_id}"


class ModelKind(dj_models.TextChoices):
    VLM = "vlm", "vlm"
    DETECTOR = "detector", "detector"
    EMBEDDING = "embedding", "embedding"
    OTHER = "other", "other"


class AIModel(dj_models.Model):
    """Model registry theo contract MBE-05 (FR-ENG-01, FR-SEC-05)."""

    name = dj_models.CharField(max_length=128)
    kind = dj_models.CharField(max_length=32, choices=ModelKind.choices, default=ModelKind.OTHER)
    version = dj_models.CharField(max_length=64)
    enabled = dj_models.BooleanField(default=True)
    revision = dj_models.PositiveIntegerField(default=1)
    created_at = dj_models.DateTimeField(auto_now_add=True)
    updated_at = dj_models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ai_model"
        ordering = ["-id"]
        constraints = [
            dj_models.UniqueConstraint(
                fields=["name", "version"], name="ai_model_unique_name_version"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name}:{self.version} ({self.kind}, rev={self.revision})"


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
    metric_reference = dj_models.ForeignKey(
        "Reference",
        null=True,
        blank=True,
        on_delete=dj_models.PROTECT,
        related_name="metric_runs",
    )
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
    # score_v1: policy đóng băng khi tạo run; null chỉ dành cho run legacy score_v0.
    score_policy_snapshot = dj_models.JSONField(null=True, blank=True)
    score_policy_hash = dj_models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001
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

    # Last explicitly selected engine retry; suppresses unrelated automatic stages.
    retry_engine = dj_models.CharField(max_length=64, blank=True, default="")

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
    retry_at = dj_models.DateTimeField(null=True, blank=True)
    deadline_at = dj_models.DateTimeField(null=True, blank=True)
    error_code = dj_models.CharField(max_length=32, blank=True, default="")
    request_attempts = dj_models.PositiveIntegerField(default=0)
    last_error = dj_models.TextField(blank=True, default="")
    started_at = dj_models.DateTimeField(null=True, blank=True)
    finished_at = dj_models.DateTimeField(null=True, blank=True)
    # Lần gần nhất message shard được gửi vào broker; sweeper chỉ gửi lại khi đã quá hạn.
    dispatched_at = dj_models.DateTimeField(null=True, blank=True)
    # Chủ sở hữu lease hiện tại của shard (token do worker nhận shard sinh ra). Chỉ chủ lease mới
    # được chốt COMPLETED/FAILED; delivery trùng hoặc worker cũ sau khi bị thu hồi thì không.
    lease_token = dj_models.CharField(max_length=32, blank=True, default="")

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


class Reference(dj_models.Model):
    """Phiên reference/GT của một snapshot (MBE-01, FR-EVL-01/04).

    Chỉ lưu metadata + checksum của GT đầu vào; nội dung GT không được lưu ở đây.
    """

    class Status(dj_models.TextChoices):
        DRAFT = "draft", "Draft"
        LOCKED = "locked", "Locked"

    snapshot = dj_models.ForeignKey(
        "snapshots.Snapshot", on_delete=dj_models.PROTECT, related_name="references"
    )
    gt_source = dj_models.CharField(max_length=255)
    gt_checksum = dj_models.CharField(max_length=64)
    mapping_version = dj_models.CharField(max_length=128)
    matching_threshold = dj_models.FloatField(default=0.5)
    minimum_area = dj_models.FloatField(default=0.0)
    algorithm_version = dj_models.CharField(max_length=64, blank=True, default="")
    status = dj_models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    created_by = dj_models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=dj_models.PROTECT, related_name="+"
    )
    locked_by = dj_models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=dj_models.PROTECT,
        related_name="+",
    )
    locked_at = dj_models.DateTimeField(null=True, blank=True)
    idempotency_key = dj_models.CharField(max_length=128, null=True, blank=True, unique=True)  # noqa: DJ001
    request_sha256 = dj_models.CharField(max_length=64, blank=True)
    created_at = dj_models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "runs_reference"

    def __str__(self) -> str:
        return f"Reference {self.pk} [{self.status}] (snapshot={self.snapshot_id})"


class GroundTruthUpload(dj_models.Model):
    """Temporary file; retain provenance after successful runs remove its contents."""

    reference = dj_models.OneToOneField(
        Reference, on_delete=dj_models.PROTECT, related_name="upload"
    )
    dataset_id = dj_models.PositiveBigIntegerField(db_index=True)
    filename = dj_models.CharField(max_length=255)
    frame_count = dj_models.PositiveIntegerField()
    box_count = dj_models.PositiveIntegerField()
    is_current = dj_models.BooleanField(default=True)
    deleted_at = dj_models.DateTimeField(null=True, blank=True)
    created_at = dj_models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            dj_models.UniqueConstraint(
                fields=["dataset_id"],
                condition=dj_models.Q(is_current=True),
                name="one_current_ground_truth_per_dataset",
            )
        ]

    def __str__(self) -> str:
        return f"GroundTruthUpload {self.pk} (dataset={self.dataset_id})"


class KpiEvaluation(dj_models.Model):
    """Lượt đánh giá KPI trên reference đã khoá (FR-EVL-13/14); khác orchestration.Evaluation."""

    class Status(dj_models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        INSUFFICIENT_SAMPLE = "insufficient_sample", "Insufficient sample"

    status = dj_models.CharField(max_length=24, choices=Status.choices)
    snapshot = dj_models.ForeignKey(
        "snapshots.Snapshot", on_delete=dj_models.PROTECT, related_name="+"
    )
    run = dj_models.ForeignKey(QCRun, on_delete=dj_models.PROTECT, related_name="kpi_evaluations")
    reference = dj_models.ForeignKey(Reference, on_delete=dj_models.PROTECT, related_name="+")
    score_version = dj_models.CharField(max_length=64)
    experiment_id = dj_models.BigIntegerField(null=True, blank=True)
    parameters = dj_models.JSONField(default=dict)
    metrics = dj_models.JSONField(null=True, blank=True)
    leakage_check = dj_models.CharField(max_length=16, default="not_checked")
    created_by = dj_models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=dj_models.PROTECT, related_name="+"
    )
    idempotency_key = dj_models.CharField(max_length=128, null=True, blank=True, unique=True)  # noqa: DJ001
    request_sha256 = dj_models.CharField(max_length=64, blank=True)
    created_at = dj_models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "runs_kpi_evaluation"

    def __str__(self) -> str:
        return f"KpiEvaluation {self.pk} [{self.status}] (run={self.run_id})"


class Waiver(dj_models.Model):
    """Waiver một điều kiện gate; chỉ hiệu lực sau duyệt và trước hạn (FR-GTE-03)."""

    class Status(dj_models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    run = dj_models.ForeignKey(QCRun, on_delete=dj_models.PROTECT, related_name="waivers")
    condition = dj_models.CharField(max_length=32)
    reason = dj_models.TextField()
    evidence = dj_models.TextField()
    expires_at = dj_models.DateTimeField()
    requested_by = dj_models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=dj_models.PROTECT, related_name="+"
    )
    approved_by = dj_models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=dj_models.PROTECT,
        related_name="+",
    )
    decision_reason = dj_models.TextField(blank=True, default="")
    decided_at = dj_models.DateTimeField(null=True, blank=True)
    status = dj_models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    idempotency_key = dj_models.CharField(max_length=128, null=True, blank=True, unique=True)  # noqa: DJ001
    request_sha256 = dj_models.CharField(max_length=64, blank=True)
    decision_key = dj_models.CharField(max_length=128, blank=True, default="")
    decision_sha256 = dj_models.CharField(max_length=64, blank=True, default="")
    created_at = dj_models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "runs_waiver"

    def __str__(self) -> str:
        return f"Waiver {self.pk} {self.condition} [{self.status}] (run={self.run_id})"
