from __future__ import annotations

from typing import Any

from rest_framework import serializers

from reports.models import ReportExport
from runs.kpi_serializers import GateResultSerializer
from runs.serializers import LedgerEntrySerializer
from runs.summary_serializers import RunMetricsSerializer


class ReportExportCreateSerializer(serializers.Serializer[Any]):
    format = serializers.ChoiceField(choices=ReportExport.Format.choices)


class ReportExportSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    run_id = serializers.IntegerField()
    format = serializers.ChoiceField(choices=ReportExport.Format.choices)
    status = serializers.ChoiceField(choices=ReportExport.Status.choices)
    download_url = serializers.URLField(allow_null=True, required=False)
    error = serializers.CharField(allow_null=True, required=False)
    created_at = serializers.DateTimeField()
    finished_at = serializers.DateTimeField(allow_null=True, required=False)

    def _download_url(self, obj: ReportExport) -> str | None:
        if obj.status != ReportExport.Status.COMPLETED or not obj.storage_key:
            return None
        from storage.client import ObjectStorage

        storage = ObjectStorage.from_django_settings("reports")
        return storage.presigned_get_url(
            obj.storage_key, is_allowed=lambda key: key == obj.storage_key
        )

    def to_representation(self, instance: ReportExport) -> dict[str, Any]:
        data = super().to_representation(instance)
        data["download_url"] = self._download_url(instance)
        return data


class RunReportSerializer(serializers.Serializer[Any]):
    run_id = serializers.IntegerField()
    snapshot_id = serializers.IntegerField()
    source_run_id = serializers.IntegerField()
    source_reason = serializers.CharField()
    score_version = serializers.CharField(allow_null=True, required=False)
    generated_at = serializers.DateTimeField()
    metrics = RunMetricsSerializer()
    gate = GateResultSerializer(allow_null=True, required=False)
    engine_coverage = LedgerEntrySerializer(many=True)
    release_id = serializers.IntegerField(allow_null=True, required=False)
    exports = ReportExportSerializer(many=True)


class MetricValueSerializer(serializers.Serializer[Any]):
    status = serializers.ChoiceField(choices=["computed", "not_checked", "insufficient_sample"])
    value = serializers.FloatField(allow_null=True)
    sample_size = serializers.IntegerField(min_value=0)
    denominator = serializers.IntegerField(min_value=0)
    method = serializers.CharField()
    confidence_interval = serializers.ListField(
        child=serializers.FloatField(), allow_null=True, required=False, min_length=2, max_length=2
    )


class EffectivenessReportSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    input_snapshot_id = serializers.IntegerField()
    reference_id = serializers.IntegerField()
    source_run_id = serializers.IntegerField()
    source_reason = serializers.CharField()
    score_version = serializers.CharField(required=False)
    metrics = serializers.DictField(child=MetricValueSerializer())
    risk_queue = serializers.DictField()
    random_queue = serializers.DictField()
    engine_coverage = LedgerEntrySerializer(many=True)
