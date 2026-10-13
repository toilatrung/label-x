"""MBE-06 response schemas; numbers are operational counts, not quality gates."""

from typing import Any

from rest_framework import serializers

from engines.interface import EngineStatus
from review.api_serializers import ENGINE_NAMES
from review.models import Issue
from runs.models import QCRun


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
    status = serializers.ChoiceField(choices=[s.value for s in EngineStatus])
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


class PaginatedTaskQualityListSerializer(serializers.Serializer[Any]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = TaskQualitySerializer(many=True)


class CandidateCategorySerializer(serializers.Serializer[Any]):
    family = serializers.ChoiceField(choices=Issue.Family.choices)
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
