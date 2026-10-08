"""Serializers cho module GDL."""

from __future__ import annotations

from typing import Any

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
            "error_group", "class_name", "paired_class", "rule_id", "guideline_version",
        ]


class PaginatedRuleMappingListSerializer(serializers.Serializer[dict[str, Any]]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = RuleMappingSerializer(many=True)
