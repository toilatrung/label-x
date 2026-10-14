from __future__ import annotations

from typing import cast

from django.contrib.auth.models import User
from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.pagination import CursorPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import HasRoleAndDatasetScope
from config.exceptions import ApiError
from config.serializers import ErrorSerializer
from releases.models import Release
from releases.serializers import (
    PaginatedReleaseListSerializer,
    ReleaseApproveSerializer,
    ReleaseManifestSerializer,
    ReleaseSerializer,
)
from releases.services import approve_release, build_manifest

_READ_ROLES: tuple[Role, ...] = (
    Role.QA_LEAD,
    Role.QC_ADMIN,
    Role.SUPER_ADMIN,
    Role.PRODUCT_OWNER,
    Role.DATA_MODEL_OWNER,
)


class ReleaseCursorPagination(CursorPagination):
    page_size = 50
    ordering = "-id"


class ReleaseListView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = _READ_ROLES
    action_name = "releases.list"
    object_type = "release"
    requires_dataset = False

    def _scoped_queryset(self, request: Request) -> QuerySet[Release]:
        from accounts.permissions import get_user_scoped_datasets

        scoped_ids = get_user_scoped_datasets(
            cast(User, request.user), allowed_roles=self.allowed_roles
        )
        if scoped_ids is None:
            return Release.objects.all()
        return Release.objects.filter(run__dataset_id__in=scoped_ids)

    @extend_schema(
        operation_id="releases_list",
        parameters=[
            OpenApiParameter("status", str, required=False, enum=["pending", "approved"]),
            OpenApiParameter("cursor", str, required=False),
        ],
        responses={200: PaginatedReleaseListSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
        tags=["releases"],
    )
    def get(self, request: Request) -> Response:
        queryset = self._scoped_queryset(request).select_related(
            "run", "snapshot", "config_version", "created_by", "approved_by"
        )
        selected_status = request.query_params.get("status")
        if selected_status is not None:
            if selected_status not in Release.Status.values:
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Status không hợp lệ."
                )
            queryset = queryset.filter(status=selected_status)
        paginator = ReleaseCursorPagination()
        page = paginator.paginate_queryset(queryset.order_by("-id"), request, view=self)
        return paginator.get_paginated_response(ReleaseSerializer(page, many=True).data)


class ReleaseScopedView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = _READ_ROLES
    object_type = "release"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            Release.objects.filter(pk=self.kwargs["pk"])
            .values_list("run__dataset_id", flat=True)
            .first()
        )


class ReleaseManifestView(ReleaseScopedView):
    action_name = "releases.manifest"

    @extend_schema(
        operation_id="releases_manifest",
        responses={200: ReleaseManifestSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        tags=["releases"],
    )
    def get(self, _request: Request, pk: int) -> Response:
        release = (
            Release.objects.select_related("run__model_artifact", "snapshot", "config_version")
            .filter(pk=pk)
            .first()
        )
        if release is None:
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Release không tồn tại.")
        return Response(ReleaseManifestSerializer(build_manifest(release)).data)


class ReleaseApproveView(ReleaseScopedView):
    allowed_roles: tuple[Role, ...] = (Role.PRODUCT_OWNER, Role.SUPER_ADMIN)
    action_name = "releases.approve"

    @extend_schema(
        operation_id="releases_approve",
        parameters=[OpenApiParameter("Idempotency-Key", str, location="header", required=False)],
        request=ReleaseApproveSerializer,
        responses={
            200: ReleaseSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
            422: ErrorSerializer,
        },
        tags=["releases"],
    )
    def post(self, request: Request, pk: int) -> Response:
        serializer = ReleaseApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = request.headers.get("Idempotency-Key", "").strip()
        if not key or len(key) > 128:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "Idempotency-Key bắt buộc và không được dài quá 128 ký tự.",
            )
        release = approve_release(
            release_id=pk,
            request=request,
            idempotency_key=key,
            note=serializer.validated_data.get("note", ""),
        )
        return Response(ReleaseSerializer(release).data)
