"""MBE-06 response schemas; numbers are operational counts, not quality gates."""

from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from review.api_serializers import ENGINE_NAMES, ENGINE_STATUSES, FAMILIES
from runs.models import QCRun


@extend_schema_field({"$ref": "#/components/schemas/EngineStatusStatusEnum"})
class EngineStatusField(serializers.ChoiceField):
    """Reuse the existing EngineStatus component, preserving M-03 enum names.

    Introducing another inline status enum renames the existing M-03 component
    and makes spectacular --fail-on-warn fail. Do not change global settings here.
    """


class RunMetricsSerializer(serializers.Serializer[Any]):
    run_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=QCRun.Status.choices)
    frames_total = serializers.IntegerField()
    frames_reviewed = serializers.IntegerField()
    issues_total = serializers.IntegerField()
    issues_by_family = serializers.DictField(child=serializers.IntegerField())
    issues_by_state = serializers.DictField(child=serializers.IntegerField())
    reviewed_ratio = serializers.FloatField(allow_null=True)


class RunEngineStatSerializer(serializers.Serializer[Any]):
    engine = serializers.ChoiceField(choices=ENGINE_NAMES)
    status = EngineStatusField(choices=ENGINE_STATUSES)
    units_total = serializers.IntegerField()
    units_failed = serializers.IntegerField()
    candidates = serializers.IntegerField()
    duration_ms = serializers.IntegerField(allow_null=True)


class RunEngineStatsSerializer(serializers.Serializer[Any]):
    run_id = serializers.IntegerField()
    engines = RunEngineStatSerializer(many=True)


class ReviewVolumePointSerializer(serializers.Serializer[Any]):
    period_start = serializers.DateField()
    frames_reviewed = serializers.IntegerField()
    decisions = serializers.IntegerField()


class ReviewVolumeSerializer(serializers.Serializer[Any]):
    run_id = serializers.IntegerField()
    granularity = serializers.ChoiceField(choices=["day", "week"])
    points = ReviewVolumePointSerializer(many=True)


class ReviewVolumeQuerySerializer(serializers.Serializer[Any]):
    granularity = serializers.ChoiceField(choices=["day", "week"], default="day")
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if "date_from" in attrs and "date_to" in attrs and attrs["date_from"] > attrs["date_to"]:
            raise serializers.ValidationError("date_from không được lớn hơn date_to.")
        return attrs


class TaskQualitySerializer(serializers.Serializer[Any]):
    cvat_task_id = serializers.IntegerField()
    name = serializers.CharField()
    frames = serializers.IntegerField()
    issues = serializers.IntegerField()
    issue_rate = serializers.FloatField(allow_null=True)
    reviewed_ratio = serializers.FloatField(allow_null=True)
    coverage = serializers.FloatField(allow_null=True)
    candidates = serializers.IntegerField()
    confirmed_issues = serializers.IntegerField()
    gate_status = serializers.ChoiceField(choices=["passed", "partial", "blocked"], allow_null=True)


class PaginatedTaskQualityListSerializer(serializers.Serializer[Any]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = TaskQualitySerializer(many=True)


class CandidateCategorySerializer(serializers.Serializer[Any]):
    family = serializers.ChoiceField(choices=FAMILIES)
    count = serializers.IntegerField()
    share = serializers.FloatField(allow_null=True)


class CandidateCategoriesSerializer(serializers.Serializer[Any]):
    run_id = serializers.IntegerField()
    total = serializers.IntegerField()
    categories = CandidateCategorySerializer(many=True)


class DatasetSummarySerializer(serializers.Serializer[Any]):
    dataset_id = serializers.IntegerField()
    name = serializers.CharField()
    snapshot_count = serializers.IntegerField()
    latest_snapshot_id = serializers.IntegerField(allow_null=True)
    latest_run_id = serializers.IntegerField(allow_null=True)
    open_issue_count = serializers.IntegerField()
    reviewed_ratio = serializers.FloatField(allow_null=True)


class PaginatedDatasetSummaryListSerializer(serializers.Serializer[Any]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = DatasetSummarySerializer(many=True)


class DatasetRevisionSerializer(serializers.Serializer[Any]):
    revision = serializers.CharField()
    snapshot_id = serializers.IntegerField()
    frame_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class PaginatedDatasetRevisionListSerializer(serializers.Serializer[Any]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = DatasetRevisionSerializer(many=True)
