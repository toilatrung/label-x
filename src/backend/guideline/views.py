"""Views cho module GDL — Tra cứu guideline.

Hợp đồng lỗi (09-interfaces.tex §apierrors):
  - 404: rule_id không tồn tại → {code, message, request_id}
  - 403: chưa đăng nhập (IsAuthenticated từ DEFAULT_PERMISSION_CLASSES)

Không dùng RAG hay embedding (FR-GDL-04, Must).
"""

from __future__ import annotations

import uuid

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from guideline.models import GuidelineRule, GuidelineVersion, RuleMapping
from guideline.serializers import (
    ErrorResponseSerializer,
    GuidelineRuleListResponseSerializer,
    GuidelineRuleSerializer,
    GuidelineVersionListResponseSerializer,
    GuidelineVersionSerializer,
)


def _error_response(
    request: Request,
    code: str,
    message: str,
    http_status: int,
) -> Response:
    """Trả phản hồi lỗi theo hợp đồng dự án: {code, message, request_id}."""
    return Response(
        {
            "code": code,
            "message": message,
            "request_id": str(uuid.uuid4()),
        },
        status=http_status,
    )


class GuidelineAPIView(APIView):
    """Base view cho API guideline chỉ đọc.

    T-003 chỉ có tài nguyên guideline toàn cục, chưa gắn dataset. Vì vậy view
    yêu cầu người dùng LabelX đã đăng nhập; RBAC/scope chi tiết được tích hợp
    bởi E-02 khi mô hình quyền của hệ thống tồn tại.
    """

    permission_classes = [IsAuthenticated]

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, (NotAuthenticated, PermissionDenied)):
            return _error_response(
                self.request,
                "forbidden",
                "Bạn không có quyền truy cập tài nguyên này.",
                status.HTTP_403_FORBIDDEN,
            )
        return super().handle_exception(exc)


class GuidelineVersionListView(GuidelineAPIView):
    """GET /api/guidelines/ — Danh sách phiên bản guideline đã nạp."""

    @extend_schema(
        operation_id="guideline_version_list",
        summary="Danh sách guideline version",
        description=(
            "Trả danh sách các phiên bản guideline đã nạp vào hệ thống. "
            "Yêu cầu đăng nhập (FR-GDL-04, FR-SEC-01)."
        ),
        responses={
            200: GuidelineVersionListResponseSerializer,
            403: ErrorResponseSerializer,
        },
        tags=["guidelines"],
    )
    def get(self, request: Request) -> Response:
        versions = GuidelineVersion.objects.all()
        serializer = GuidelineVersionSerializer(versions, many=True)
        return Response({"count": len(serializer.data), "results": serializer.data})


class GuidelineRuleListView(GuidelineAPIView):
    """GET /api/guidelines/rules/ — Danh sách rule, lọc theo mapping."""

    @extend_schema(
        operation_id="guideline_rule_list",
        summary="Tra rule theo nhóm lỗi/lớp",
        description=(
            "Trả danh sách rule theo ánh xạ (error_group, class_name, paired_class). "
            "Có thể kết hợp nhiều filter. Không truyền filter → trả tất cả rule. "
            "Không dùng RAG (FR-GDL-04)."
        ),
        parameters=[
            OpenApiParameter("error_group", str, description="Nhóm lỗi: E1, E2, E3"),
            OpenApiParameter("class_name", str, description="Tên lớp: car, truck, …"),
            OpenApiParameter("paired_class", str, description="Lớp cặp: truck"),
            OpenApiParameter("version", str, description="version_tag, mặc định latest"),
        ],
        responses={
            200: GuidelineRuleListResponseSerializer,
            403: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        },
        tags=["guidelines"],
    )
    def get(self, request: Request) -> Response:
        version_tag: str | None = request.query_params.get("version")
        if version_tag:
            version_qs = GuidelineVersion.objects.filter(version_tag=version_tag)
            if not version_qs.exists():
                return _error_response(
                    request,
                    "not_found",
                    f"Guideline version '{version_tag}' không tồn tại.",
                    status.HTTP_404_NOT_FOUND,
                )
            version = version_qs.first()
        else:
            version = GuidelineVersion.objects.first()  # latest (ordered by -loaded_at)

        if version is None:
            return Response({"count": 0, "results": []})

        error_group: str | None = request.query_params.get("error_group")
        class_name: str | None = request.query_params.get("class_name")
        paired_class: str | None = request.query_params.get("paired_class")

        has_filter = any([error_group, class_name, paired_class])

        if has_filter:
            mapping_qs = RuleMapping.objects.filter(version=version)
            if error_group is not None:
                mapping_qs = mapping_qs.filter(error_group=error_group)
            if class_name is not None:
                mapping_qs = mapping_qs.filter(class_name=class_name)
            if paired_class is not None:
                mapping_qs = mapping_qs.filter(paired_class=paired_class)
            rule_ids = mapping_qs.values_list("rule_id", flat=True).distinct()
            rules = GuidelineRule.objects.filter(version=version, id__in=rule_ids)
        else:
            rules = GuidelineRule.objects.filter(version=version)

        serializer = GuidelineRuleSerializer(rules, many=True)
        return Response({"count": len(serializer.data), "results": serializer.data})


class GuidelineRuleDetailView(GuidelineAPIView):
    """GET /api/guidelines/rules/{rule_id}/ — Rule theo rule_id."""

    @extend_schema(
        operation_id="guideline_rule_retrieve",
        summary="Tra rule theo rule ID",
        description=(
            "Trả thông tin một rule theo rule_id. "
            "Dùng query param version để chọn phiên bản; mặc định là phiên bản mới nhất. "
            "Trả 404 nếu rule_id không tồn tại (09-interfaces.tex §apierrors)."
        ),
        parameters=[
            OpenApiParameter("version", str, description="version_tag, mặc định latest"),
        ],
        responses={
            200: GuidelineRuleSerializer,
            403: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        },
        tags=["guidelines"],
    )
    def get(self, request: Request, rule_id: str) -> Response:
        version_tag: str | None = request.query_params.get("version")
        if version_tag:
            version_qs = GuidelineVersion.objects.filter(version_tag=version_tag)
            if not version_qs.exists():
                return _error_response(
                    request,
                    "not_found",
                    f"Guideline version '{version_tag}' không tồn tại.",
                    status.HTTP_404_NOT_FOUND,
                )
            version = version_qs.first()
        else:
            version = GuidelineVersion.objects.first()

        if version is None:
            return _error_response(
                request,
                "not_found",
                f"Rule '{rule_id}' không tồn tại.",
                status.HTTP_404_NOT_FOUND,
            )

        try:
            rule = GuidelineRule.objects.get(version=version, rule_id=rule_id)
        except GuidelineRule.DoesNotExist:
            return _error_response(
                request,
                "not_found",
                f"Rule '{rule_id}' không tồn tại.",
                status.HTTP_404_NOT_FOUND,
            )

        serializer = GuidelineRuleSerializer(rule)
        return Response(serializer.data)
