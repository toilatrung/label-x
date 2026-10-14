"""Serializers cho module GDL."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from guideline.models import GuidelineRule, GuidelineVersion, RuleMapping


class ErrorResponseSerializer(serializers.Serializer[dict[str, Any]]):
    """Hợp đồng lỗi dùng chung của API LabelX."""

    code = serializers.CharField()
    message = serializers.CharField()
    request_id = serializers.CharField()
    details = serializers.DictField(required=False, default=dict)


class GuidelineVersionSerializer(serializers.ModelSerializer[GuidelineVersion]):
    class Meta:
        model = GuidelineVersion
        fields = ["version_tag", "name", "loaded_at"]


class GuidelineRuleSerializer(serializers.ModelSerializer[GuidelineRule]):
    guideline_version = serializers.CharField(source="version.version_tag", read_only=True)

    class Meta:
        model = GuidelineRule
        fields = ["rule_id", "section", "content", "guideline_version"]


class PaginatedGuidelineRuleListSerializer(serializers.Serializer[dict[str, Any]]):
    """Envelope phân trang cursor theo hợp đồng OpenAPI."""

    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = GuidelineRuleSerializer(many=True)


class RuleMappingSerializer(serializers.ModelSerializer[RuleMapping]):
    rule_id = serializers.CharField(source="rule.rule_id", read_only=True)
    guideline_version = serializers.CharField(source="version.version_tag", read_only=True)

    class Meta:
        model = RuleMapping
        fields = [
            "error_group",
            "class_name",
            "paired_class",
            "rule_id",
            "guideline_version",
        ]


class PaginatedRuleMappingListSerializer(serializers.Serializer[dict[str, Any]]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = RuleMappingSerializer(many=True)


@extend_schema_serializer(component_name="GuidelineVersionEntry")
class GuidelineVersionEntrySerializer(serializers.Serializer[dict[str, Any]]):
    version = serializers.CharField()
    is_current = serializers.BooleanField()
    rule_count = serializers.IntegerField()
    effective_from = serializers.DateTimeField(allow_null=True, required=False)
    effective_to = serializers.DateTimeField(allow_null=True, required=False)


@extend_schema_serializer(component_name="PaginatedGuidelineVersionEntryList")
class PaginatedGuidelineVersionEntryListSerializer(serializers.Serializer[dict[str, Any]]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = GuidelineVersionEntrySerializer(many=True)
