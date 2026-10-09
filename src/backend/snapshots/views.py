"""Snapshot create/list/detail API with dataset-scoped RBAC."""

from __future__ import annotations

from typing import cast

import httpx
from django.contrib.auth.models import User
from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.pagination import CursorPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import HasRoleAndDatasetScope, append_action_audit
from config.exceptions import ApiError
from snapshots.models import Snapshot
from snapshots.orchestration import (
    SnapshotRequestConflict,
    SnapshotScope,
    SnapshotSourceError,
    create_snapshot_from_cvat,
)
from snapshots.serializers import (
    PaginatedSnapshotListSerializer,
    SnapshotAcceptedSerializer,
    SnapshotCreateSerializer,
    SnapshotErrorResponseSerializer,
    SnapshotSerializer,
)


class SnapshotCursorPagination(CursorPagination):
    page_size = 50
    ordering = "-id"


class SnapshotCollectionView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    action_name = "snapshots.read"
    object_type = "snapshot"
    requires_dataset = True

    def get_permissions(self) -> list[HasRoleAndDatasetScope]:
        self.allowed_roles = (
            (Role.QA_LEAD, Role.SUPER_ADMIN)
            if self.request.method == "POST"
            else (Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN)
        )
        return super().get_permissions()  # type: ignore[return-value]

    @extend_schema(
        operation_id="snapshots_list",
        parameters=[OpenApiParameter("dataset_id", int, required=True)],
        responses={
            200: PaginatedSnapshotListSerializer,
            400: SnapshotErrorResponseSerializer,
            403: SnapshotErrorResponseSerializer,
        },
        tags=["snapshots"],
    )
    def get(self, request: Request) -> Response:
        dataset_id = int(request.query_params["dataset_id"])
        queryset = (
            Snapshot.objects.filter(dataset_id=dataset_id)
            .select_related("created_by", "parent_snapshot")
            .prefetch_related("jobs__frames")
            .order_by("-id")
        )
        paginator = SnapshotCursorPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(SnapshotSerializer(page, many=True).data)

    @extend_schema(
        operation_id="snapshots_create",
        request=SnapshotCreateSerializer,
        responses={
            202: SnapshotAcceptedSerializer,
            400: SnapshotErrorResponseSerializer,
            403: SnapshotErrorResponseSerializer,
            409: SnapshotErrorResponseSerializer,
        },
        tags=["snapshots"],
    )
    def post(self, request: Request) -> Response:
        serializer = SnapshotCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = request.headers.get("Idempotency-Key", "").strip()
        if not key:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "Thiếu header Idempotency-Key.",
            )
        if len(key) > 128:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "Idempotency-Key không được dài quá 128 ký tự.",
            )
        data = serializer.validated_data
        raw_scope = data["scope"]
        try:
            snapshot = create_snapshot_from_cvat(
                dataset_id=data["dataset_id"],
                scope=SnapshotScope(
                    cvat_task_ids=tuple(raw_scope.get("cvat_task_ids", [])),
                    cvat_job_ids=tuple(raw_scope.get("cvat_job_ids", [])),
                ),
                note=data.get("note", ""),
                created_by=cast(User, request.user),
                idempotency_key=key,
            )
        except SnapshotRequestConflict as exc:
            raise ApiError(status.HTTP_409_CONFLICT, "IDEMPOTENCY_KEY_REUSED", str(exc)) from exc
        except (SnapshotSourceError, httpx.HTTPError) as exc:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", str(exc)) from exc

        append_action_audit(
            request=request,
            action="snapshot.create",
            object_type="snapshot",
            object_id=snapshot.pk,
            after={
                "dataset_id": snapshot.dataset_id,
                "status": snapshot.status,
                "revision_hash": snapshot.revision_sha256 or None,
                "drift_jobs": snapshot.drift_jobs,
            },
            revision=snapshot.revision_sha256 or snapshot.request_sha256,
        )
        return Response(
            SnapshotAcceptedSerializer(snapshot).data,
            status=status.HTTP_202_ACCEPTED,
        )


class SnapshotDetailView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN)
    action_name = "snapshots.retrieve"
    object_type = "snapshot"
    requires_dataset = True

    def _queryset(self) -> QuerySet[Snapshot]:
        return Snapshot.objects.select_related("created_by", "parent_snapshot").prefetch_related(
            "jobs__frames"
        )

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            Snapshot.objects.filter(pk=self.kwargs["pk"])
            .values_list("dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="snapshots_retrieve",
        responses={
            200: SnapshotSerializer,
            403: SnapshotErrorResponseSerializer,
            404: SnapshotErrorResponseSerializer,
        },
        tags=["snapshots"],
    )
    def get(self, _request: Request, pk: int) -> Response:
        try:
            snapshot = self._queryset().get(pk=pk)
        except Snapshot.DoesNotExist as exc:
            raise ApiError(
                status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Snapshot không tồn tại."
            ) from exc
        return Response(SnapshotSerializer(snapshot).data)
