"""Multipart Ground Truth upload and current dataset metadata (no file download)."""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.models import User
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import HasRoleAndDatasetScope
from config.exceptions import ApiError
from engines.metric import _gt_frames
from runs.ground_truth import create_upload
from runs.kpi_serializers import ReferenceSerializer
from runs.kpi_views import _idempotency_key, _reference_read
from runs.models import GroundTruthUpload
from snapshots.models import Snapshot


class GroundTruthUploadSerializer(serializers.Serializer[Any]):
    snapshot_id = serializers.IntegerField(min_value=1)
    file = serializers.FileField()
    mapping_version = serializers.CharField(max_length=128)
    matching_threshold = serializers.FloatField(min_value=0, max_value=1, default=0.5)
    minimum_area = serializers.FloatField(min_value=0, default=0)


class GroundTruthSerializer(serializers.Serializer[Any]):
    reference = ReferenceSerializer()
    dataset_id = serializers.IntegerField()
    filename = serializers.CharField()
    frame_count = serializers.IntegerField()
    box_count = serializers.IntegerField()
    deleted_at = serializers.DateTimeField(allow_null=True)
    is_current = serializers.BooleanField()


def upload_read(upload: GroundTruthUpload) -> dict[str, Any]:
    return {
        "reference": _reference_read(upload.reference),
        "dataset_id": upload.dataset_id,
        "filename": upload.filename,
        "frame_count": upload.frame_count,
        "box_count": upload.box_count,
        "deleted_at": upload.deleted_at,
        "is_current": upload.is_current,
    }


class GroundTruthView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.QA_LEAD, Role.SUPER_ADMIN)
    requires_dataset = True
    action_name = "ground_truth.upload"
    object_type = "reference"
    parser_classes = [MultiPartParser, FormParser]

    def get_dataset_id(self, request: Request) -> int | None:
        value = (
            request.query_params.get("dataset_id")
            if request.method == "GET"
            else request.data.get("snapshot_id")
        )
        if value is None:
            return None
        try:
            pk = int(value)
        except (ValueError, TypeError):
            return None
        if request.method == "GET":
            return pk if pk > 0 else None
        return Snapshot.objects.filter(pk=pk).values_list("dataset_id", flat=True).first()

    @extend_schema(
        operation_id="ground_truth_current",
        parameters=[OpenApiParameter("dataset_id", int, required=True)],
        responses={200: GroundTruthSerializer},
        tags=["evaluation"],
    )
    def get(self, request: Request) -> Response:
        dataset_id = self.get_dataset_id(request)
        if dataset_id is None:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Thiếu Dataset.")
        upload = (
            GroundTruthUpload.objects.select_related("reference")
            .filter(dataset_id=dataset_id, is_current=True)
            .first()
        )
        return Response(upload_read(upload) if upload else None)

    @extend_schema(
        operation_id="ground_truth_upload",
        request=GroundTruthUploadSerializer,
        parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, True)],
        responses={201: GroundTruthSerializer},
        tags=["evaluation"],
    )
    def post(self, request: Request) -> Response:
        body = GroundTruthUploadSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        snapshot = Snapshot.objects.get(pk=data.pop("snapshot_id"))
        try:
            upload = create_upload(
                snapshot=snapshot,
                actor=cast(User, request.user),
                key=_idempotency_key(request),
                **data,
            )
        except (ValueError, UnicodeError) as exc:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", str(exc)) from exc
        return Response(upload_read(upload), status=status.HTTP_201_CREATED)


class GroundTruthPreviewSerializer(serializers.Serializer[Any]):
    reference_id = serializers.IntegerField()
    frames = serializers.ListField(child=serializers.DictField())


class GroundTruthPreviewView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.QA_LEAD, Role.SUPER_ADMIN)
    requires_dataset = True
    action_name = "ground_truth.preview"
    object_type = "reference"

    def get_dataset_id(self, request: Request) -> int | None:
        return (
            GroundTruthUpload.objects.filter(reference_id=self.kwargs["pk"])
            .values_list("dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="ground_truth_preview",
        responses={200: GroundTruthPreviewSerializer},
        tags=["evaluation"],
    )
    def get(self, request: Request, pk: int) -> Response:
        upload = GroundTruthUpload.objects.select_related("reference").get(reference_id=pk)
        if upload.deleted_at:
            raise ApiError(
                status.HTTP_410_GONE, "GROUND_TRUTH_DELETED", "Ground Truth đã xóa. Hãy upload lại."
            )
        frames = _gt_frames(upload.reference)
        return Response({"reference_id": pk, "frames": list(frames.values())})
