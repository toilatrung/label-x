"""Serializers cho module GDL."""

from rest_framework import serializers

from guideline.models import GuidelineRule, GuidelineVersion


class ErrorResponseSerializer(serializers.Serializer[dict[str, object]]):
    """Hợp đồng lỗi dùng chung của API LabelX."""

    code = serializers.CharField()
    message = serializers.CharField()
    request_id = serializers.UUIDField()


class GuidelineVersionSerializer(serializers.ModelSerializer[GuidelineVersion]):
    class Meta:
        model = GuidelineVersion
        fields = ["version_tag", "name", "loaded_at"]


class GuidelineVersionListResponseSerializer(serializers.Serializer[dict[str, object]]):
    """Envelope thực tế của API danh sách guideline version."""

    count = serializers.IntegerField(min_value=0)
    results = GuidelineVersionSerializer(many=True)


class GuidelineRuleSerializer(serializers.ModelSerializer[GuidelineRule]):
    guideline_version = serializers.CharField(source="version.version_tag", read_only=True)

    class Meta:
        model = GuidelineRule
        fields = ["rule_id", "section", "content", "guideline_version"]


class GuidelineRuleListResponseSerializer(serializers.Serializer[dict[str, object]]):
    """Envelope thực tế của API danh sách rule."""

    count = serializers.IntegerField(min_value=0)
    results = GuidelineRuleSerializer(many=True)
