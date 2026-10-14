"""Candidate, evidence, ledger của orchestrator (FR-AGG-01/04/06).

FK tới `runs.QCRun` (cột `run_id`, khớp `EngineInput.run_id`).
"""

from __future__ import annotations

from typing import Any

from django.db import models


class ShardCommit(models.Model):
    """Một shard đã commit. Tồn tại = kết quả shard đã ghi, retry cùng khoá là no-op."""

    idempotency_key = models.CharField(max_length=128)
    run = models.ForeignKey(
        "runs.QCRun", on_delete=models.PROTECT, db_column="run_id", related_name="+"
    )
    snapshot_id = models.PositiveBigIntegerField()
    engine = models.CharField(max_length=64)
    engine_version = models.CharField(max_length=32)
    shard_index = models.PositiveIntegerField()
    output_sha256 = models.CharField(max_length=64)
    attempts = models.PositiveIntegerField(default=1)
    committed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Khoá engine không chứa run_id (FR-AGG-02): hai run cùng input phải commit riêng.
            models.UniqueConstraint(
                fields=["run", "idempotency_key"], name="uniq_shard_key_per_run"
            ),
            models.UniqueConstraint(
                fields=["run", "engine", "shard_index"], name="uniq_shard_per_run_engine"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.engine} run={self.run_id} shard={self.shard_index}"


class CandidateRecord(models.Model):
    run = models.ForeignKey(
        "runs.QCRun", on_delete=models.PROTECT, db_column="run_id", related_name="+"
    )
    dedup_key = models.CharField(max_length=64)
    shard = models.ForeignKey(ShardCommit, on_delete=models.PROTECT, related_name="candidates")
    engine = models.CharField(max_length=64)
    engine_version = models.CharField(max_length=32)
    family = models.CharField(max_length=64)
    cvat_task_id = models.PositiveBigIntegerField()
    frame_number = models.PositiveIntegerField()
    anchor = models.JSONField()
    policy_version = models.CharField(max_length=32)
    evidence = models.JSONField()
    evidence_sha256 = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "dedup_key"], name="uniq_candidate_dedup")
        ]

    def __str__(self) -> str:
        return f"{self.engine} run={self.run_id} {self.dedup_key[:12]}"


class LedgerUnit(models.Model):
    """Một đơn vị trong mẫu số ledger của engine trong run (FR-AGG-04)."""

    run = models.ForeignKey(
        "runs.QCRun", on_delete=models.PROTECT, db_column="run_id", related_name="+"
    )
    engine = models.CharField(max_length=64)
    kind = models.CharField(max_length=16)
    cvat_task_id = models.PositiveBigIntegerField()
    frame_number = models.PositiveIntegerField()
    outcome = models.CharField(max_length=16, default="pending")
    not_checked_reason = models.CharField(max_length=24, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    details = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["run", "engine", "kind", "cvat_task_id", "frame_number"],
                name="uniq_ledger_unit",
            )
        ]

    def __str__(self) -> str:
        return (
            f"{self.engine} run={self.run_id} {self.kind}:{self.cvat_task_id}/{self.frame_number}"
        )


class VlmBudget(models.Model):
    """Ngân sách lần gọi provider của một run (M04A-03). Có dòng = stage VLM của run đã khởi động.

    Chỉ tăng `used_calls` bằng UPDATE có điều kiện `used_calls < max_calls` (nguyên tử); CHECK ở
    DB chặn vượt ngân sách kể cả khi code sai.
    """

    run = models.OneToOneField(
        "runs.QCRun", on_delete=models.PROTECT, db_column="run_id", related_name="+"
    )
    max_calls = models.PositiveIntegerField()
    used_calls = models.PositiveIntegerField(default=0)
    skipped_reason = models.CharField(max_length=32, blank=True, default="")
    started_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(used_calls__lte=models.F("max_calls")),
                name="vlm_budget_used_within_max",
            )
        ]

    def __str__(self) -> str:
        return f"VlmBudget run={self.run_id} {self.used_calls}/{self.max_calls}"


class VlmUnit(models.Model):
    """Một lượt VLM logic cho một candidate (đơn vị VLM = candidate, không phải frame).

    Khoá idempotency gồm evaluation generation, candidate, crop identity, snapshot revision,
    policy, model và prompt version: tạo lại cùng khoá là no-op, không nhân unit/evidence/budget.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    run = models.ForeignKey(
        "runs.QCRun", on_delete=models.PROTECT, db_column="run_id", related_name="+"
    )
    candidate = models.ForeignKey(CandidateRecord, on_delete=models.PROTECT, related_name="+")
    idempotency_key = models.CharField(max_length=64)
    evaluation_generation = models.PositiveIntegerField(default=1)
    policy_version = models.CharField(max_length=32)
    model = models.CharField(max_length=64)
    prompt_version = models.CharField(max_length=32)
    crop_identity = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    reason_code = models.CharField(max_length=24, blank=True, default="")
    result = models.JSONField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    lease_token = models.CharField(max_length=32, blank=True, default="")
    dispatched_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["run", "idempotency_key"], name="uniq_vlm_unit_key_per_run"
            ),
            models.UniqueConstraint(
                fields=["run", "candidate", "evaluation_generation"],
                name="uniq_vlm_unit_candidate_generation",
            ),
        ]

    def __str__(self) -> str:
        return f"VlmUnit run={self.run_id} candidate={self.candidate_id} [{self.status}]"


class VlmAttempt(models.Model):
    """Attempt gửi provider đã được tính budget. Unique (unit, attempt_no): giao lại cùng attempt
    không tính budget lần hai."""

    unit = models.ForeignKey(VlmUnit, on_delete=models.CASCADE, related_name="attempt_rows")
    attempt_no = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["unit", "attempt_no"], name="uniq_vlm_attempt_no")
        ]

    def __str__(self) -> str:
        return f"VlmAttempt unit={self.unit_id} #{self.attempt_no}"


class VlmEvidenceImmutableError(RuntimeError):
    """VlmEvidence là append-only: không sửa, không xoá."""


class VlmEvidence(models.Model):
    """Evidence VLM append-only, đúng một dòng cho mỗi VlmUnit (M04A-04).

    Là đề xuất/bằng chứng, không phải quyết định: không có quan hệ tới ReviewDecision hay
    Adjudication. Lưu model/prompt/policy/revision, crop hash và ánh xạ crop về ảnh gốc, request
    ID đã redacted. Không chứa API key, prompt hay bytes ảnh. DB trigger chặn UPDATE/DELETE.
    """

    class Status(models.TextChoices):
        CHECKED = "checked", "Checked"
        UNCERTAIN = "uncertain", "Uncertain"
        FAILED = "failed", "Failed"

    unit = models.OneToOneField(VlmUnit, on_delete=models.PROTECT, related_name="evidence")
    run = models.ForeignKey(
        "runs.QCRun", on_delete=models.PROTECT, db_column="run_id", related_name="+"
    )
    candidate = models.ForeignKey(CandidateRecord, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=16, choices=Status.choices)
    label_class_id = models.CharField(max_length=64, blank=True, default="")
    class_name = models.CharField(max_length=128, blank=True, default="")
    # Lời giải thích của model, KHÔNG phải bằng chứng đã xác minh.
    rationale = models.TextField(blank=True, default="")
    reason_code = models.CharField(max_length=24, blank=True, default="")
    attempts = models.PositiveSmallIntegerField(default=0)
    provider = models.CharField(max_length=32)
    # Host của cổng/provider (không secret) và model ID mà cổng BÁO VỀ: kết quả có thể đi qua bên
    # trung gian nên cần provenance thực tế, không chỉ model đã yêu cầu.
    provider_host = models.CharField(max_length=128, blank=True, default="")
    response_model = models.CharField(max_length=64, blank=True, default="")
    model = models.CharField(max_length=64)
    prompt_version = models.CharField(max_length=32)
    policy_version = models.CharField(max_length=32)
    snapshot_revision = models.CharField(max_length=64)
    crop_sha256 = models.CharField(max_length=64, blank=True, default="")
    crop_origin = models.JSONField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True, default="")
    config = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"VlmEvidence unit={self.unit_id} [{self.status}]"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise VlmEvidenceImmutableError("VlmEvidence là append-only, không được cập nhật.")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise VlmEvidenceImmutableError("VlmEvidence là append-only, không được xoá.")


class Evaluation(models.Model):
    """Một lượt đánh giá logic của candidate (M04C-02): quyết định định tuyến + (nếu cần) VlmUnit.

    Mỗi (candidate, generation) đúng một dòng; `source="auto"` là lượt đầu do stage tạo, `manual`
    là re-evaluate do reviewer/QA yêu cầu với Idempotency-Key mới. Policy được LƯU THEO evaluation
    (`policy` kèm sha256) để đọc lại đúng ngưỡng đã dùng; ngưỡng chỉ là routing tạm, không phải
    calibration. Bản ghi bất biến sau khi tạo: không ghi đè evidence hay quyết định cũ; trạng thái
    chạy luôn suy ra từ `vlm_unit`. `note` là ghi chú tự do của người dùng, chỉ để audit và KHÔNG
    bao giờ đi vào prompt VLM. Không có quan hệ tới ReviewDecision/Adjudication.
    """

    class Source(models.TextChoices):
        AUTO = "auto", "Auto"
        MANUAL = "manual", "Manual"

    run = models.ForeignKey(
        "runs.QCRun", on_delete=models.PROTECT, db_column="run_id", related_name="+"
    )
    candidate = models.ForeignKey(CandidateRecord, on_delete=models.PROTECT, related_name="+")
    generation = models.PositiveIntegerField()
    source = models.CharField(max_length=8, choices=Source.choices)
    idempotency_key = models.CharField(max_length=128, blank=True, default="")
    request_sha256 = models.CharField(max_length=64, blank=True, default="")
    requested_by = models.ForeignKey(
        "auth.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    note = models.CharField(max_length=500, blank=True, default="")
    expected_revision = models.CharField(max_length=128, blank=True, default="")
    snapshot_revision = models.CharField(max_length=128)
    primary_reason = models.CharField(max_length=24)
    reasons = models.JSONField(default=list)
    call_qwen = models.BooleanField()
    human_review_required = models.BooleanField()
    policy = models.JSONField()
    checkpoint_status = models.CharField(max_length=16, blank=True, default="")
    vlm_unit = models.OneToOneField(
        VlmUnit, null=True, blank=True, on_delete=models.PROTECT, related_name="evaluation"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "generation"], name="uniq_evaluation_candidate_generation"
            ),
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_evaluation_idempotency_key",
            ),
        ]

    def __str__(self) -> str:
        return f"Evaluation candidate={self.candidate_id} gen={self.generation} [{self.source}]"
