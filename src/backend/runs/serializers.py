"""Serializers for QC Run API matching OpenAPI contract (docs/04-api/openapi.yaml)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from runs.models import ModelArtifact, QCRun, RunRankingEntry


class RunCreateSerializer(serializers.Serializer[Any]):
    """Schema for RunCreate."""

    snapshot_id = serializers.IntegerField(min_value=1)
    config_version_id = serializers.IntegerField(min_value=1)
    seed = serializers.IntegerField()


class ModelArtifactSerializer(serializers.ModelSerializer[Any]):
    """Schema for ModelArtifact."""

    class Meta:
        model = ModelArtifact
        fields = ["name", "version", "checksum"]


class EngineRunStatusSerializer(serializers.Serializer[Any]):
    """Schema for EngineRunStatus."""

    engine = serializers.CharField()
    status = serializers.CharField()
    reason = serializers.CharField(allow_null=True, required=False)
    failed_units = serializers.IntegerField(default=0)


class RunSerializer(serializers.ModelSerializer[Any]):
    """Schema for Run matching OpenAPI components.schemas.Run."""

    model_artifact = ModelArtifactSerializer(read_only=True)
    engines = serializers.SerializerMethodField()
    origin_run_id = serializers.IntegerField(
        source="origin_run.id", allow_null=True, read_only=True
    )

    class Meta:
        model = QCRun
        fields = [
            "id",
            "snapshot_id",
            "config_version_id",
            "seed",
            "status",
            "is_final",
            "origin_run_id",
            "score_version",
            "model_artifact",
            "engines",
            "created_by",
            "created_at",
            "finished_at",
        ]
        read_only_fields = fields

    def get_engines(self, obj: QCRun) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for er in obj.engine_results.all():
            results.append(
                {
                    "engine": er.engine,
                    "status": er.status,
                    "reason": er.reason,
                    "failed_units": er.failed_units,
                }
            )
        return results


class PaginatedRunListSerializer(serializers.Serializer[Any]):
    """Schema for PaginatedRunList."""

    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = RunSerializer(many=True)


class RankedFrameSerializer(serializers.ModelSerializer[Any]):
    """Stored ranking row matching and extending the public RankedFrame schema."""

    frame_id = serializers.IntegerField(source="snapshot_frame_id", read_only=True)
    frame_key = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    baseline_score = serializers.SerializerMethodField()
    queue = serializers.SerializerMethodField()
    source: Any = serializers.CharField(source="ranking.source", read_only=True)
    score_version = serializers.CharField(source="ranking.score_version", read_only=True)
    review_state = serializers.SerializerMethodField()
    lease_holder_user_id = serializers.SerializerMethodField()

    class Meta:
        model = RunRankingEntry
        fields = [
            "frame_id",
            "frame_key",
            "rank",
            "score",
            "baseline_score",
            "score_version",
            "queue",
            "source",
            "review_state",
            "missing_evidence",
            "issue_counts",
            "explanation",
            "lease_holder_user_id",
        ]
        read_only_fields = fields

    def get_frame_key(self, obj: RunRankingEntry) -> dict[str, int]:
        return {
            "cvat_task_id": obj.snapshot_frame.snapshot_job.cvat_task_id,
            "frame_number": obj.snapshot_frame.frame_index,
        }

    def get_score(self, obj: RunRankingEntry) -> float:
        return float(obj.score)

    def get_baseline_score(self, obj: RunRankingEntry) -> float:
        return float(obj.baseline_score)

    def get_queue(self, obj: RunRankingEntry) -> str:
        return "random" if obj.ranking.source == "random_audit" else "risk"

    def get_review_state(self, _obj: RunRankingEntry) -> str:
        return "unreviewed"

    def get_lease_holder_user_id(self, _obj: RunRankingEntry) -> int | None:
        return None


class PaginatedRankedFrameListSerializer(serializers.Serializer[Any]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    source: Any = serializers.CharField()
    content_hash = serializers.CharField()
    ranking_hash = serializers.CharField()
    results = RankedFrameSerializer(many=True)
