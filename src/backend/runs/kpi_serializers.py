"""Serializer cho reference, KPI evaluation, gate, waiver và báo cáo (MBE-01)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from calibration.serializers import MetricValueSerializer
from runs.kpi import WAIVABLE
from runs.serializers import LedgerEntrySerializer

CONDITIONS = ["coverage", "open_critical_issues", "rework_verified", "residual", "agreement"]


class ReferenceCreateSerializer(serializers.Serializer[Any]):
    snapshot_id = serializers.IntegerField(min_value=1)
    gt_source = serializers.CharField(max_length=255)
    gt_checksum = serializers.RegexField(r"^[0-9a-fA-F]{64}$", help_text="SHA-256 của GT")
    mapping_version = serializers.CharField(max_length=128)
    matching_threshold = serializers.FloatField(min_value=0, max_value=1, required=False)
    minimum_area = serializers.FloatField(min_value=0, required=False)
    algorithm_version = serializers.CharField(max_length=64, required=False)


class ReferenceSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    snapshot_id = serializers.IntegerField()
    gt_checksum = serializers.CharField()
    mapping_version = serializers.CharField()
    matching_threshold = serializers.FloatField()
    minimum_area = serializers.FloatField()
    algorithm_version = serializers.CharField()
    status: Any = serializers.CharField(help_text="draft | locked")
    created_by = serializers.IntegerField()
    locked_by = serializers.IntegerField(allow_null=True)
    locked_at = serializers.DateTimeField(allow_null=True)


class KpiEvaluationCreateSerializer(serializers.Serializer[Any]):
    snapshot_id = serializers.IntegerField(min_value=1)
    run_id = serializers.IntegerField(min_value=1)
    reference_id = serializers.IntegerField(min_value=1)
    score_version = serializers.CharField(max_length=64)
    experiment_id = serializers.IntegerField(required=False, allow_null=True)
    parameters = serializers.DictField()


class KpiEvaluationSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    status: Any = serializers.CharField(
        help_text="queued | running | completed | failed | insufficient_sample"
    )
    snapshot_id = serializers.IntegerField()
    run_id = serializers.IntegerField()
    reference_id = serializers.IntegerField()
    score_version = serializers.CharField()
    experiment_id = serializers.IntegerField(allow_null=True)
    parameters = serializers.DictField()
    metrics = serializers.DictField(child=MetricValueSerializer(), allow_null=True)
    leakage_check = serializers.CharField(help_text="passed | failed | not_checked")
    created_by = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class GateConditionSerializer(serializers.Serializer[Any]):
    name: Any = serializers.CharField(help_text=" | ".join(CONDITIONS))
    status: Any = serializers.CharField(help_text="passed | failed | not_checked | waived")
    observed = serializers.FloatField(allow_null=True)
    threshold = serializers.FloatField()
    waiver_id = serializers.IntegerField(allow_null=True, required=False)
    reason = serializers.CharField(allow_null=True, required=False)


class GateResultSerializer(serializers.Serializer[Any]):
    run_id = serializers.IntegerField()
    source_run_id = serializers.IntegerField()
    source_reason = serializers.CharField()
    status: Any = serializers.CharField(help_text="passed | failed | not_checked")
    conditions = GateConditionSerializer(many=True)


class WaiverCreateSerializer(serializers.Serializer[Any]):
    run_id = serializers.IntegerField(min_value=1)
    condition = serializers.ChoiceField(choices=CONDITIONS, help_text=f"Chỉ {WAIVABLE}")
    reason = serializers.CharField(min_length=1)
    evidence = serializers.CharField(min_length=1)
    expires_at = serializers.DateTimeField()


class WaiverDecisionSerializer(serializers.Serializer[Any]):
    approved = serializers.BooleanField()
    reason = serializers.CharField(min_length=1)


class WaiverSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    run_id = serializers.IntegerField()
    condition = serializers.ChoiceField(choices=CONDITIONS)
    reason = serializers.CharField()
    evidence = serializers.CharField()
    expires_at = serializers.DateTimeField()
    requested_by = serializers.IntegerField()
    approved_by = serializers.IntegerField(allow_null=True)
    status: Any = serializers.CharField(help_text="pending | approved | rejected | expired")


class EffectivenessReportSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    input_snapshot_id = serializers.IntegerField()
    reference_id = serializers.IntegerField()
    source_run_id = serializers.IntegerField()
    source_reason = serializers.CharField()
    score_version = serializers.CharField()
    metrics = serializers.DictField(child=MetricValueSerializer())
    risk_queue = serializers.DictField()
    random_queue = serializers.DictField()
    engine_coverage = LedgerEntrySerializer(many=True)
