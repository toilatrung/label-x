"""Candidate, evidence, ledger của orchestrator (FR-AGG-01/04/06).

Khoá theo `run_id` số nguyên (như EngineInput) để không phụ thuộc model QCRun của T-024;
T-024 gắn FK/nối thật khi merge.
"""

from __future__ import annotations

from django.db import models


class ShardCommit(models.Model):
    """Một shard đã commit. Tồn tại = kết quả shard đã ghi, retry cùng khoá là no-op."""

    idempotency_key = models.CharField(max_length=128, unique=True)
    run_id = models.PositiveBigIntegerField(db_index=True)
    snapshot_id = models.PositiveBigIntegerField()
    engine = models.CharField(max_length=64)
    engine_version = models.CharField(max_length=32)
    shard_index = models.PositiveIntegerField()
    output_sha256 = models.CharField(max_length=64)
    attempts = models.PositiveIntegerField(default=1)
    committed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["run_id", "engine", "shard_index"], name="uniq_shard_per_run_engine"
            )
        ]

    def __str__(self) -> str:
        return f"{self.engine} run={self.run_id} shard={self.shard_index}"


class CandidateRecord(models.Model):
    run_id = models.PositiveBigIntegerField(db_index=True)
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
            models.UniqueConstraint(fields=["run_id", "dedup_key"], name="uniq_candidate_dedup")
        ]

    def __str__(self) -> str:
        return f"{self.engine} run={self.run_id} {self.dedup_key[:12]}"


class LedgerUnit(models.Model):
    """Một đơn vị trong mẫu số ledger của engine trong run (FR-AGG-04)."""

    run_id = models.PositiveBigIntegerField(db_index=True)
    engine = models.CharField(max_length=64)
    kind = models.CharField(max_length=16)
    cvat_task_id = models.PositiveBigIntegerField()
    frame_number = models.PositiveIntegerField()
    outcome = models.CharField(max_length=16, default="pending")
    not_checked_reason = models.CharField(max_length=24, blank=True)
    attempts = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["run_id", "engine", "kind", "cvat_task_id", "frame_number"],
                name="uniq_ledger_unit",
            )
        ]

    def __str__(self) -> str:
        return (
            f"{self.engine} run={self.run_id} {self.kind}:{self.cvat_task_id}/{self.frame_number}"
        )
