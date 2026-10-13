"""Guideline-gap collection endpoints introduced by MBE-02."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.pagination import CursorPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role, RoleAssignment
from accounts.permissions import HasRoleAndDatasetScope
from audit.services import append_audit_event
from config.exceptions import ApiError
from config.serializers import ErrorSerializer
from guideline.models import GuidelineRule, get_latest_guideline_version
from review.api_serializers import IDEMPOTENCY_KEY_PARAM
from review.case_serializers import (
    GuidelineGapCreateSerializer,
    GuidelineGapSerializer,
    PaginatedGuidelineGapSerializer,
)
from review.models import GuidelineGap, Issue


def guideline_gap_payload(gap: GuidelineGap) -> dict[str, Any]:
    return {
        "id": gap.pk,
        "issue_id": gap.issue_id,
        "rule_id": gap.rule_id,
        "description": gap.description,
        "status": gap.status,
        "guideline_version": gap.guideline_version,
        "resolved_in_version": gap.resolved_in_version,
        "created_by": gap.created_by_id,
        "created_at": gap.created_at.isoformat(),
    }


def _actor(request: Request) -> User:
    user = request.user
    if not isinstance(user, User) or user.pk is None:
        raise ApiError(status.HTTP_403_FORBIDDEN, "NOT_AUTHENTICATED", "Chưa đăng nhập.")
    return user


def _scope(user: User) -> tuple[bool, set[int]]:
    assignments = RoleAssignment.objects.filter(user=user)
    global_access = assignments.filter(
        role__in=[Role.QC_ADMIN, Role.SUPER_ADMIN], dataset_id__isnull=True
    ).exists()
    datasets = set(
        assignments.filter(
            role__in=[Role.REVIEWER, Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN],
            dataset_id__isnull=False,
        ).values_list("dataset_id", flat=True)
    )
    return global_access, {int(item) for item in datasets if item is not None}


def _idempotency(request: Request) -> str | None:
    raw = request.headers.get("Idempotency-Key", "").strip()
    if not raw:
        return None
    if len(raw) > 36:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Idempotency-Key quá dài.")
    return raw


@transaction.atomic
def create_guideline_gap(request: Request) -> GuidelineGap:
    user = _actor(request)
    serializer = GuidelineGapCreateSerializer(data=request.data)
    if not serializer.is_valid():
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "Dữ liệu guideline gap không hợp lệ.",
            {"fields": serializer.errors},
        )
    data = serializer.validated_data
    issue_id = data.get("issue_id")
    issue = None
    if issue_id is not None:
        issue = (
            Issue.objects.select_related("frame_review__run__snapshot").filter(pk=issue_id).first()
        )
        if issue is None:
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Issue không tồn tại.")
        global_access, datasets = _scope(user)
        if not global_access and issue.frame_review.run.dataset_id not in datasets:
            raise ApiError(status.HTTP_403_FORBIDDEN, "OUT_OF_SCOPE", "Ngoài phạm vi dataset.")
        version = issue.frame_review.run.snapshot.guideline_version
    else:
        latest = get_latest_guideline_version()
        if latest is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "BUSINESS_RULE_UNMET",
                "Chưa có guideline version đã nạp.",
            )
        version = latest.version_tag

    rule_id = str(data["rule_id"]).strip()
    if not GuidelineRule.objects.filter(version__version_tag=version, rule_id=rule_id).exists():
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "BUSINESS_RULE_UNMET",
            "Rule không thuộc guideline version áp dụng.",
        )
    body = {
        "issue_id": issue_id,
        "rule_id": rule_id,
        "description": str(data["description"]).strip(),
    }
    request_hash = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    key = _idempotency(request)
    if key is not None:
        replay = GuidelineGap.objects.filter(created_by=user, idempotency_key=key).first()
        if replay is not None:
            if replay.request_hash != request_hash:
                raise ApiError(
                    status.HTTP_409_CONFLICT,
                    "IDEMPOTENCY_KEY_REUSED",
                    "Idempotency-Key đã dùng với body khác.",
                )
            return replay
    if GuidelineGap.objects.filter(
        issue=issue, rule_id=rule_id, status=GuidelineGap.Status.OPEN
    ).exists():
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "INVALID_TRANSITION",
            "Đã có guideline gap đang mở cho issue và rule này.",
        )
    try:
        gap = GuidelineGap.objects.create(
            issue=issue,
            rule_id=rule_id,
            description=body["description"],
            guideline_version=version,
            created_by=user,
            idempotency_key=key,
            request_hash=request_hash,
        )
    except IntegrityError as exc:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "INVALID_TRANSITION",
            "Đã có guideline gap đang mở cho issue và rule này.",
        ) from exc
    append_audit_event(
        actor=user,
        action="guideline_gap.create",
        object_type="guideline_gap",
        object_id=gap.pk,
        before=None,
        after={"issue_id": issue_id, "rule_id": rule_id, "status": gap.status},
        revision=issue.frame_review.run.snapshot.revision_sha256 if issue else version,
        reason=gap.description,
    )
    return gap


class GapCursorPagination(CursorPagination):
    page_size = 50
    ordering = ("-created_at", "-id")


class GuidelineGapCollectionView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    action_name = "guideline_gaps.access"
    object_type = "guideline_gap"
    requires_dataset = False

    def get_permissions(self) -> list[HasRoleAndDatasetScope]:
        self.allowed_roles = (
            (Role.QA_LEAD, Role.SUPER_ADMIN)
            if self.request.method == "POST"
            else (Role.REVIEWER, Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN)
        )
        return super().get_permissions()  # type: ignore[return-value]

    @extend_schema(
        operation_id="guideline_gaps_list",
        parameters=[
            OpenApiParameter("status", str, required=False, enum=GuidelineGap.Status.values),
            OpenApiParameter("rule_id", str, required=False),
            OpenApiParameter("cursor", str, required=False),
        ],
        responses={
            200: PaginatedGuidelineGapSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
        },
        tags=["review"],
    )
    def get(self, request: Request) -> Response:
        user = _actor(request)
        global_access, datasets = _scope(user)
        queryset = GuidelineGap.objects.select_related("issue__frame_review__run", "created_by")
        if not global_access:
            queryset = queryset.filter(
                Q(issue__isnull=True) | Q(issue__frame_review__run__dataset_id__in=datasets)
            )
        selected = request.query_params.get("status")
        if selected is not None:
            if selected not in GuidelineGap.Status.values:
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "status không hợp lệ."
                )
            queryset = queryset.filter(status=selected)
        rule_id = request.query_params.get("rule_id")
        if rule_id is not None:
            queryset = queryset.filter(rule_id=rule_id.strip())
        paginator = GapCursorPagination()
        page = paginator.paginate_queryset(queryset, request, view=self) or []
        return paginator.get_paginated_response([guideline_gap_payload(gap) for gap in page])

    @extend_schema(
        operation_id="guideline_gaps_create",
        parameters=[IDEMPOTENCY_KEY_PARAM],
        request=GuidelineGapCreateSerializer,
        responses={
            201: GuidelineGapSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
            422: ErrorSerializer,
        },
        tags=["review"],
    )
    def post(self, request: Request) -> Response:
        return Response(
            guideline_gap_payload(create_guideline_gap(request)), status=status.HTTP_201_CREATED
        )
