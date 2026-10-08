"""Views cho module GDL — Tra cứu guideline.

Theo CR-101 và OpenAPI contract (docs/04-api/openapi.yaml):
- Tra rule tĩnh theo rule_id và theo context mapping (family, class_name, paired_class).
- Không dùng RAG hay embedding (FR-GDL-04, Must).
- Quyền theo vai trò: reviewer, qa_lead, qc_admin, super_admin.
- Cursor pagination page size 50.
"""

from __future__ import annotations

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import CursorPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from guideline.models import (
    GuidelineRule,
    GuidelineVersion,
    RuleMapping,
    get_latest_guideline_version,
)
from guideline.permissions import HasGuidelineRole
from guideline.serializers import (
    ErrorResponseSerializer,
    GuidelineRuleSerializer,
    PaginatedGuidelineRuleListSerializer,
)

# IssueFamily trong docs/04-api/openapi.yaml; giữ thứ tự enum của contract.
ISSUE_FAMILIES = ["E1", "E2", "E3", "structural"]
VALID_FAMILIES = set(ISSUE_FAMILIES)


class GuidelineCursorPagination(CursorPagination):
    page_size = 50
    ordering = "id"


class GuidelineAPIView(APIView):
    """Base view cho API guideline chỉ đọc.

    Yêu cầu quyền theo vai trò (HasGuidelineRole): reviewer, qa_lead, qc_admin, super_admin.
    Lỗi được xử lý thống nhất qua exception handler dùng chung của LabelX.
    """

    permission_classes = [HasGuidelineRole]


class GuidelineRuleListView(GuidelineAPIView):
    """GET /api/guidelines/rules/ — Danh sách rule, lọc theo mapping."""

    @extend_schema(
        operation_id="guidelines_rules_list",
        summary="Tra rule theo nhóm lỗi, lớp, cặp lớp",
        description=(
            "Không dùng retrieval ngữ nghĩa (FR-GDL-04). Mặc định guideline version mới nhất."
        ),
        parameters=[
            OpenApiParameter(
                "version",
                str,
                description="Guideline version tag; bỏ trống là bản mới nhất.",
            ),
            OpenApiParameter(
                "family",
                str,
                enum=ISSUE_FAMILIES,
                description="Nhóm lỗi (IssueFamily): E1, E2, E3, structural",
            ),
            OpenApiParameter("class_name", str, description="Tên lớp"),
            OpenApiParameter("paired_class", str, description="Lớp cặp"),
            OpenApiParameter("cursor", str, description="Con trỏ phân trang"),
        ],
        responses={
            200: PaginatedGuidelineRuleListSerializer,
            400: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        },
        tags=["guidelines"],
    )
    def get(self, request: Request) -> Response:
        version: GuidelineVersion | None = None
        version_tag = request.query_params.get("version", "").strip()
        if version_tag:
            try:
                version = GuidelineVersion.objects.get(version_tag=version_tag)
            except GuidelineVersion.DoesNotExist as exc:
                raise NotFound(f"Guideline version '{version_tag}' không tồn tại.") from exc
        else:
            version = get_latest_guideline_version()

        if version is None:
            return Response({"next": None, "previous": None, "results": []})

        family = request.query_params.get("family", "").strip()
        if family and family not in VALID_FAMILIES:
            allowed = ", ".join(sorted(VALID_FAMILIES))
            raise ValidationError(
                {"family": [f"Giá trị '{family}' không hợp lệ. Phải là một trong: {allowed}."]}
            )

        class_name = request.query_params.get("class_name", "").strip()
        paired_class = request.query_params.get("paired_class", "").strip()

        has_filter = any((family, class_name, paired_class))
        if has_filter:
            mapping_qs = RuleMapping.objects.filter(version=version)
            if family:
                mapping_qs = mapping_qs.filter(Q(error_group=family) | Q(error_group=""))
            if class_name:
                mapping_qs = mapping_qs.filter(Q(class_name=class_name) | Q(class_name=""))
            if paired_class:
                mapping_qs = mapping_qs.filter(Q(paired_class=paired_class) | Q(paired_class=""))

            rule_ids = mapping_qs.values_list("rule_id", flat=True).distinct()
            rules = GuidelineRule.objects.filter(version=version, id__in=rule_ids)
        else:
            rules = GuidelineRule.objects.filter(version=version)

        rules = rules.order_by("id")
        paginator = GuidelineCursorPagination()
        page = paginator.paginate_queryset(rules, request, view=self)
        serializer = GuidelineRuleSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class GuidelineRuleDetailView(GuidelineAPIView):
    """GET /api/guidelines/rules/{rule_id}/ — Rule theo rule_id."""

    @extend_schema(
        operation_id="guidelines_rules_retrieve",
        summary="Rule theo guideline version của snapshot",
        description=(
            "Trả thông tin một rule theo rule_id. "
            "Dùng query param version để chọn phiên bản; mặc định là phiên bản mới nhất. "
            "Trả 404 nếu rule_id không tồn tại."
        ),
        parameters=[
            OpenApiParameter(
                "version",
                str,
                description="Guideline version tag; bỏ trống là bản mới nhất.",
            ),
        ],
        responses={
            200: GuidelineRuleSerializer,
            403: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        },
        tags=["guidelines"],
    )
    def get(self, request: Request, rule_id: str) -> Response:
        version: GuidelineVersion | None = None
        version_tag = request.query_params.get("version", "").strip()
        if version_tag:
            try:
                version = GuidelineVersion.objects.get(version_tag=version_tag)
            except GuidelineVersion.DoesNotExist as exc:
                raise NotFound(f"Guideline version '{version_tag}' không tồn tại.") from exc
        else:
            version = get_latest_guideline_version()

        if version is None:
            raise NotFound(f"Rule '{rule_id}' không tồn tại.")

        try:
            rule = GuidelineRule.objects.get(version=version, rule_id=rule_id)
        except GuidelineRule.DoesNotExist as exc:
            raise NotFound(f"Rule '{rule_id}' không tồn tại.") from exc

        serializer = GuidelineRuleSerializer(rule)
        return Response(serializer.data)
