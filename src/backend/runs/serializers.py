"""Serializers for QC Run API matching OpenAPI contract (docs/04-api/openapi.yaml)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from orchestration.models import CandidateRecord
from runs.models import ConfigVersion, ModelArtifact, QCRun, RunRankingEntry, WorkUnit


class RunCreateSerializer(serializers.Serializer[Any]):
    """Schema for RunCreate."""

    snapshot_id = serializers.IntegerField(min_value=1)
    config_version_id = serializers.IntegerField(min_value=1)
    seed = serializers.IntegerField()


# DEMO-ONLY: response contract for M-DEMO01; not the M-03 review domain.
class DemoCvatLinkSerializer(serializers.Serializer[dict[str, Any]]):
    task_id = serializers.IntegerField()
    job_id = serializers.IntegerField()
    frame = serializers.IntegerField()
    deep_link = serializers.URLField()


class DemoShapeSerializer(serializers.Serializer[dict[str, Any]]):
    id = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    bbox = serializers.ListField(child=serializers.FloatField(), min_length=4, max_length=4)


class DemoCandidateSerializer(serializers.Serializer[dict[str, Any]]):
    id = serializers.CharField()
    engine = serializers.CharField()
    rule_id = serializers.CharField()
    family = serializers.CharField()
    severity = serializers.CharField()
    shape_ids = serializers.ListField(child=serializers.CharField())
    message = serializers.CharField()
    evidence = serializers.JSONField()


class DemoFrameSerializer(serializers.Serializer[dict[str, Any]]):
    frame_id = serializers.IntegerField()
    rank = serializers.IntegerField(min_value=1)
    score = serializers.FloatField()
    file_name = serializers.CharField()
    width = serializers.IntegerField(min_value=1)
    height = serializers.IntegerField(min_value=1)
    image_url = serializers.CharField()
    cvat = DemoCvatLinkSerializer()
    shapes = DemoShapeSerializer(many=True)
    candidates = DemoCandidateSerializer(many=True)


class DemoEngineSerializer(serializers.Serializer[dict[str, Any]]):
    engine = serializers.CharField()
    status = serializers.ChoiceField(choices=["checked", "failed", "not_checked"])


class DemoFramePageSerializer(serializers.Serializer[dict[str, Any]]):
    run_id = serializers.IntegerField()
    snapshot_id = serializers.IntegerField()
    score_version = serializers.CharField()
    next = serializers.CharField(allow_null=True)
    items = DemoFrameSerializer(many=True)
    engines = DemoEngineSerializer(many=True)


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


class ConfigVersionSerializer(serializers.ModelSerializer[Any]):
    class Meta:
        model = ConfigVersion
        fields = [
            "id",
            "name",
            "status",
            "engines",
            "thresholds",
            "models",
            "created_by",
            "created_at",
            "published_at",
        ]
        read_only_fields = fields


class ConfigVersionCreateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=128)
    engines = serializers.DictField()
    thresholds = serializers.DictField(required=False, default=dict)
    models = serializers.DictField(required=False, default=dict)

    def validate_engines(self, value: dict[str, Any]) -> dict[str, Any]:
        allowed = {"schema", "geometry", "duplicate", "detector", "metric", "vlm"}
        if not value or any(
            name not in allowed
            or not isinstance(config, dict)
            or not isinstance(config.get("enabled"), bool)
            for name, config in value.items()
        ):
            raise serializers.ValidationError(
                "Engine phải có tên hợp lệ và cờ enabled dạng boolean."
            )
        if not any(config["enabled"] for config in value.values()):
            raise serializers.ValidationError("Cần bật ít nhất một engine.")
        return value


class PaginatedConfigVersionSerializer(serializers.Serializer[Any]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = ConfigVersionSerializer(many=True)


class WorkUnitSerializer(serializers.ModelSerializer[Any]):
    class Meta:
        model = WorkUnit
        fields = [
            "id",
            "engine",
            "shard_key",
            "shard_index",
            "status",
            "attempt",
            "last_error",
            "started_at",
            "finished_at",
        ]
        read_only_fields = fields


class PaginatedWorkUnitSerializer(serializers.Serializer[Any]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = WorkUnitSerializer(many=True)


class LedgerEntrySerializer(serializers.Serializer[Any]):
    engine = serializers.CharField()
    status = serializers.CharField()
    required = serializers.BooleanField()  # type: ignore[assignment]
    unit = serializers.CharField()
    total = serializers.IntegerField()
    eligible = serializers.IntegerField()
    excluded = serializers.IntegerField()
    applicability_version = serializers.CharField()
    completed = serializers.IntegerField()
    failed = serializers.IntegerField()
    pending = serializers.IntegerField()
    not_checked = serializers.IntegerField()
    not_checked_reasons = serializers.DictField(child=serializers.IntegerField())
    coverage = serializers.FloatField(allow_null=True)


class CandidateSerializer(serializers.ModelSerializer[Any]):
    """Schema for Candidate matching OpenAPI components.schemas.Candidate."""

    frame = serializers.SerializerMethodField()
    severity = serializers.SerializerMethodField()

    class Meta:
        model = CandidateRecord
        fields = [
            "engine",
            "engine_version",
            "family",
            "severity",
            "frame",
            "anchor",
            "evidence",
        ]
        read_only_fields = fields

    def get_frame(self, obj: CandidateRecord) -> dict[str, int]:
        return {
            "cvat_task_id": obj.cvat_task_id,
            "frame_number": obj.frame_number,
        }

    def get_severity(self, obj: CandidateRecord) -> str | None:
        return getattr(obj, "severity", None)


class PaginatedCandidateListSerializer(serializers.Serializer[Any]):
    """Schema for PaginatedCandidateList."""

    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    raw_count = serializers.IntegerField(allow_null=True)
    dedup_count = serializers.IntegerField()
    results = CandidateSerializer(many=True)


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
