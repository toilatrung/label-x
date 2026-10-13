"""Serializers for Calibration and Audit Sampling (MBE-04)."""

from __future__ import annotations

from rest_framework import serializers

from calibration.models import (
    AuditSample,
    AuditSampleFrame,
    AuditSampleStream,
    Benchmark,
    CalibrationAssignment,
    TargetKind,
)


class FrameKeySerializer(serializers.Serializer[object]):
    task_id = serializers.IntegerField()
    frame_index = serializers.IntegerField()


class AuditSampleFrameSerializer(serializers.ModelSerializer[AuditSampleFrame]):
    frame_id = serializers.IntegerField(source="snapshot_frame.pk")
    frame_key = serializers.SerializerMethodField()
    rank = serializers.IntegerField(allow_null=True)
    review_state = serializers.CharField()

    class Meta:
        model = AuditSampleFrame
        fields = ["frame_id", "frame_key", "rank", "review_state"]

    def get_frame_key(self, obj: AuditSampleFrame) -> dict[str, int]:
        frame = obj.snapshot_frame
        task_id = frame.snapshot_job.cvat_task_id if frame.snapshot_job else 0
        return {"task_id": task_id, "frame_index": frame.frame_index}


class AuditSampleSerializer(serializers.ModelSerializer[AuditSample]):
    run_id = serializers.IntegerField(source="run.pk")
    created_by = serializers.IntegerField(source="created_by.pk")

    class Meta:
        model = AuditSample
        fields = [
            "id",
            "run_id",
            "stream",
            "seed",
            "size",
            "frame_count",
            "created_by",
            "created_at",
        ]


class AuditSampleDetailSerializer(AuditSampleSerializer):
    frames = AuditSampleFrameSerializer(source="sample_frames", many=True, read_only=True)

    class Meta(AuditSampleSerializer.Meta):
        fields = AuditSampleSerializer.Meta.fields + ["frames"]


class AuditSampleCreateSerializer(serializers.Serializer[object]):
    run_id = serializers.IntegerField(required=True)
    stream = serializers.ChoiceField(choices=AuditSampleStream.choices, required=True)
    size = serializers.IntegerField(min_value=1, required=True)
    seed = serializers.IntegerField(required=False, allow_null=True)


class BenchmarkSerializer(serializers.ModelSerializer[Benchmark]):
    snapshot_id = serializers.IntegerField(source="snapshot.pk", allow_null=True)
    created_by = serializers.IntegerField(source="created_by.pk")

    class Meta:
        model = Benchmark
        fields = [
            "id",
            "name",
            "dataset_id",
            "snapshot_id",
            "source",
            "cvat_task_id",
            "status",
            "frame_count",
            "created_by",
            "created_at",
        ]


class BenchmarkCreateSerializer(serializers.Serializer[object]):
    name = serializers.CharField(min_length=1, max_length=255, required=True)
    dataset_id = serializers.IntegerField(required=True)
    snapshot_id = serializers.IntegerField(required=True)
    frame_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, required=True)


class BenchmarkImportCvatSerializer(serializers.Serializer[object]):
    name = serializers.CharField(min_length=1, max_length=255, required=True)
    dataset_id = serializers.IntegerField(required=True)
    cvat_task_id = serializers.IntegerField(required=True)


class MetricValueSerializer(serializers.Serializer[object]):
    status = serializers.ChoiceField(
        choices=["computed", "not_checked", "insufficient_sample"], required=True
    )
    value = serializers.FloatField(allow_null=True, required=False)
    sample_size = serializers.IntegerField(min_value=0, required=True)
    denominator = serializers.IntegerField(min_value=0, required=True)
    method = serializers.CharField(required=True)
    confidence_interval = serializers.ListField(
        child=serializers.FloatField(), required=False, allow_null=True
    )


class PerformanceEntrySerializer(serializers.Serializer[object]):
    evaluation_id = serializers.IntegerField()
    run_id = serializers.IntegerField()
    snapshot_id = serializers.IntegerField()
    score_version = serializers.CharField()
    created_at = serializers.DateTimeField()
    metrics = serializers.DictField(child=MetricValueSerializer())


class CalibrationReviewerSerializer(serializers.Serializer[object]):
    user_id = serializers.IntegerField()
    display_name = serializers.CharField()
    reviewed_frames = serializers.IntegerField()
    assignments = serializers.IntegerField()
    agreement_rate = serializers.FloatField(allow_null=True)
    last_calibrated_at = serializers.DateTimeField(allow_null=True)


class CalibrationModelSerializer(serializers.Serializer[object]):
    model_id = serializers.IntegerField()
    name = serializers.CharField()
    version = serializers.CharField()
    kind = serializers.ChoiceField(choices=["vlm", "detector", "embedding", "other"])
    assignments = serializers.IntegerField()
    agreement_rate = serializers.FloatField(allow_null=True)
    last_calibrated_at = serializers.DateTimeField(allow_null=True)


class CalibrationAssignmentSerializer(serializers.ModelSerializer[CalibrationAssignment]):
    audit_sample_id = serializers.IntegerField(source="audit_sample.pk")
    created_by = serializers.IntegerField(source="created_by.pk")

    class Meta:
        model = CalibrationAssignment
        fields = [
            "id",
            "target_kind",
            "target_id",
            "audit_sample_id",
            "status",
            "note",
            "created_by",
            "created_at",
        ]


class CalibrationAssignmentCreateSerializer(serializers.Serializer[object]):
    target_kind = serializers.ChoiceField(choices=TargetKind.choices, required=True)
    target_id = serializers.IntegerField(required=True)
    audit_sample_id = serializers.IntegerField(required=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")
