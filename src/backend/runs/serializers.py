"""Serializers for QC Run API matching OpenAPI contract (docs/04-api/openapi.yaml)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from runs.models import ConfigVersion, EngineResult, ModelArtifact, QCRun


class RunCreateSerializer(serializers.Serializer):
    """Schema for RunCreate."""

    snapshot_id = serializers.IntegerField(min_value=1)
    config_version_id = serializers.IntegerField(min_value=1)
    seed = serializers.IntegerField()


class ModelArtifactSerializer(serializers.ModelSerializer):
    """Schema for ModelArtifact."""

    class Meta:
        model = ModelArtifact
        fields = ["name", "version", "checksum"]


class EngineRunStatusSerializer(serializers.Serializer):
    """Schema for EngineRunStatus."""

    engine = serializers.CharField()
    status = serializers.CharField()
    reason = serializers.CharField(allow_null=True, required=False)
    failed_units = serializers.IntegerField(default=0)


class RunSerializer(serializers.ModelSerializer):
    """Schema for Run matching OpenAPI components.schemas.Run."""

    model_artifact = ModelArtifactSerializer(read_only=True)
    engines = serializers.SerializerMethodField()
    origin_run_id = serializers.IntegerField(source="origin_run.id", allow_null=True, read_only=True)

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
            results.append({
                "engine": er.engine,
                "status": er.status,
                "reason": er.reason,
                "failed_units": er.failed_units,
            })
        return results


class PaginatedRunListSerializer(serializers.Serializer):
    """Schema for PaginatedRunList."""

    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = RunSerializer(many=True)