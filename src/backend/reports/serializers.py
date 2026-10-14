from __future__ import annotations

from typing import Any

from rest_framework import serializers

from calibration.serializers import MetricValueSerializer
from reports.models import ReportExport
from runs.serializers import LedgerEntrySerializer


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


class RunMetricsSerializer(serializers.Serializer[Any]):
    run_id = serializers.IntegerField()
    status = serializers.ChoiceField(
        choices=["queued", "running", "completed", "partial", "failed", "cancelled"]
    )
    frames_total = serializers.IntegerField()
    frames_reviewed = serializers.IntegerField()
    issues_total = serializers.IntegerField()
    issues_by_family = serializers.DictField(child=serializers.IntegerField())
    issues_by_state = serializers.DictField(child=serializers.IntegerField())
    reviewed_ratio = serializers.FloatField(allow_null=True, required=False)


class GateConditionSerializer(serializers.Serializer[Any]):
    name = serializers.ChoiceField(
        choices=["coverage", "open_critical_issues", "rework_verified", "residual", "agreement"]
    )
    status = serializers.ChoiceField(choices=["passed", "failed", "not_checked", "waived"])
    observed = serializers.FloatField(allow_null=True)
    threshold = serializers.FloatField()
    waiver_id = serializers.IntegerField(allow_null=True, required=False)
    reason = serializers.CharField(allow_null=True, required=False)


class GateResultSerializer(serializers.Serializer[Any]):
    run_id = serializers.IntegerField()
    source_run_id = serializers.IntegerField()
    source_reason = serializers.CharField()
    status = serializers.ChoiceField(choices=["passed", "failed", "not_checked"])
    conditions = GateConditionSerializer(many=True)


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
