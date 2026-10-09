"""API serializers for immutable snapshots."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from rest_framework import serializers

from cvat_adapter.client import build_job_url
from snapshots.models import Snapshot, SnapshotFrame, SnapshotJob


class SnapshotErrorResponseSerializer(serializers.Serializer[dict[str, Any]]):
    code = serializers.CharField()
    message = serializers.CharField()
    request_id = serializers.CharField()
    details = serializers.DictField(required=False, default=dict)


class SnapshotScopeSerializer(serializers.Serializer[dict[str, Any]]):
    cvat_task_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list
    )
    cvat_job_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        for field in ("cvat_task_ids", "cvat_job_ids"):
            values = attrs.get(field, [])
            if len(values) != len(set(values)):
                raise serializers.ValidationError({field: "Không được chứa ID trùng lặp."})
        return attrs


class SnapshotCreateSerializer(serializers.Serializer[dict[str, Any]]):
    dataset_id = serializers.IntegerField(min_value=1)
    scope = SnapshotScopeSerializer()
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class SnapshotFrameSerializer(serializers.ModelSerializer[SnapshotFrame]):
    cvat_url = serializers.SerializerMethodField()

    class Meta:
        model = SnapshotFrame
        fields = ["frame_index", "file_name", "width", "height", "cvat_url"]

    def get_cvat_url(self, frame: SnapshotFrame) -> str:
        job = frame.snapshot_job
        return build_job_url(
            settings.CVAT_BASE_URL,
            job.cvat_task_id,
            job.cvat_job_id,
            frame_index=frame.frame_index,
        )


class SnapshotJobSerializer(serializers.ModelSerializer[SnapshotJob]):
    job_hash = serializers.CharField(source="sha256")
    assignee_user_id = serializers.IntegerField(allow_null=True)
    cvat_url = serializers.SerializerMethodField()
    frames = SnapshotFrameSerializer(many=True, read_only=True)

    class Meta:
        model = SnapshotJob
        fields = [
            "cvat_job_id",
            "cvat_task_id",
            "job_hash",
            "assignee_user_id",
            "cvat_url",
            "frames",
        ]

    def get_cvat_url(self, job: SnapshotJob) -> str:
        return build_job_url(settings.CVAT_BASE_URL, job.cvat_task_id, job.cvat_job_id)


class SnapshotSerializer(serializers.ModelSerializer[Snapshot]):
    revision_hash = serializers.SerializerMethodField()
    parent_snapshot_id = serializers.IntegerField(allow_null=True)
    jobs = SnapshotJobSerializer(many=True, read_only=True)
    created_by = serializers.IntegerField(source="created_by_id")
    failure_reason = serializers.SerializerMethodField()
    out_of_scope_shapes = serializers.SerializerMethodField()

    class Meta:
        model = Snapshot
        fields = [
            "id",
            "dataset_id",
            "status",
            "failure_reason",
            "revision_hash",
            "parent_snapshot_id",
            "jobs",
            "taxonomy_version",
            "guideline_version",
            "out_of_scope_shapes",
            "drift_jobs",
            "created_by",
            "created_at",
            "locked_at",
        ]

    def get_revision_hash(self, snapshot: Snapshot) -> str | None:
        return snapshot.revision_sha256 or None

    def get_failure_reason(self, snapshot: Snapshot) -> str | None:
        return snapshot.failure_reason or None

    def get_out_of_scope_shapes(self, snapshot: Snapshot) -> int:
        return sum(int(value) for value in snapshot.skipped_shape_counts.values())


class SnapshotAcceptedSerializer(serializers.ModelSerializer[Snapshot]):
    class Meta:
        model = Snapshot
        fields = ["id", "status", "drift_jobs"]


class PaginatedSnapshotListSerializer(serializers.Serializer[dict[str, Any]]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = SnapshotSerializer(many=True)
