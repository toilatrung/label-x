"""D04 read-only rework endpoints: GET /api/rework/ and GET /api/rework/{id}/."""

from __future__ import annotations

from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.pagination import CursorPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role, RoleAssignment
from accounts.permissions import HasRoleAndDatasetScope
from config.exceptions import ApiError
from config.serializers import ErrorSerializer
from review.api_serializers import (
    PaginatedReworkSerializer,
    ReworkDetailSerializer,
)
from review.models import ReworkRequest
from review.rework_timeline import rework_timeline
from review.rework_views import ReworkCreateView

_READ_ROLES = (Role.ANNOTATOR, Role.REVIEWER, Role.QA_LEAD, Role.SUPER_ADMIN)
_BROAD_ROLES = (Role.REVIEWER, Role.QA_LEAD)


class ReworkCursorPagination(CursorPagination):
    page_size = 50
    ordering = ("created_at", "id")


def rework_read(rework: ReworkRequest) -> dict[str, object]:
    frame_review = rework.issue.frame_review
    return {
        "id": rework.pk,
        "dataset_id": frame_review.run.dataset_id,
        "issue_id": rework.issue_id,
        "frame_id": frame_review.pk,
        "annotator_user_id": rework.annotator_id,
        "created_by_user_id": rework.created_by_id,
        "status": rework.status,
        "instruction": rework.instruction,
        "severity": rework.severity,
        "original_revision": rework.original_revision,
        "submitted_revision": rework.submitted_revision,
        "recheck_run_id": rework.recheck_run_id,
        "due_at": rework.due_at.isoformat(),
        "cvat_deep_link": rework.cvat_deep_link,
        "submitted_at": rework.submitted_at.isoformat() if rework.submitted_at else None,
        "resolved_at": rework.resolved_at.isoformat() if rework.resolved_at else None,
        "created_at": rework.created_at.isoformat(),
        "updated_at": rework.updated_at.isoformat(),
        "round_count": len(rework_timeline(rework)),
    }


def rework_detail(rework: ReworkRequest) -> dict[str, object]:
    return {
        **rework_read(rework),
        "review_state": rework.issue.frame_review.state,
        "timeline": rework_timeline(rework),
    }


def _sees_all(user_id: int | None, dataset_id: int) -> bool:
    """Reviewer/QA Lead in the dataset, or Super Admin, read beyond their own assignments."""

    if user_id is None:
        return False
    return (
        RoleAssignment.objects.filter(user_id=user_id)
        .filter(
            Q(role__in=_BROAD_ROLES, dataset_id=dataset_id)
            | Q(role=Role.SUPER_ADMIN, dataset_id__isnull=True)
        )
        .exists()
    )


def _base_queryset() -> QuerySet[ReworkRequest]:
    return ReworkRequest.objects.select_related(
        "issue__frame_review__run", "issue__frame_review__snapshot_frame"
    ).prefetch_related("rechecks__run", "verifications__recheck_run")


class ReworkListView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = _READ_ROLES
    action_name = "rework.list"
    object_type = "rework"
    requires_dataset = True

    @extend_schema(
        operation_id="rework_list",
        parameters=[
            OpenApiParameter("dataset_id", int, required=True),
            OpenApiParameter("status", str, required=False, enum=ReworkRequest.Status.values),
            OpenApiParameter("cursor", str, required=False),
        ],
        responses={200: PaginatedReworkSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
        tags=["rework"],
    )
    def get(self, request: Request) -> Response:
        dataset_id = int(request.query_params["dataset_id"])
        selected = request.query_params.get("status")
        if selected is not None and selected not in ReworkRequest.Status.values:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "status không hợp lệ.")
        visible = _base_queryset().filter(issue__frame_review__run__dataset_id=dataset_id)
        if not _sees_all(request.user.pk, dataset_id):
            visible = visible.filter(annotator_id=request.user.pk)
        counts = {value: 0 for value in ReworkRequest.Status.values}
        counts.update(
            {
                row["status"]: row["total"]
                for row in visible.order_by().values("status").annotate(total=Count("pk"))
            }
        )
        queryset = visible.filter(status=selected) if selected else visible
        paginator = ReworkCursorPagination()
        page = paginator.paginate_queryset(queryset, request, view=self) or []
        response = paginator.get_paginated_response([rework_read(row) for row in page])
        response.data["counts"] = counts
        return response


class ReworkDetailView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = _READ_ROLES
    action_name = "rework.retrieve"
    object_type = "rework"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            ReworkRequest.objects.filter(pk=self.kwargs["pk"])
            .values_list("issue__frame_review__run__dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="rework_retrieve",
        responses={200: ReworkDetailSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        tags=["rework"],
    )
    def get(self, request: Request, pk: int) -> Response:
        rework = _base_queryset().get(pk=pk)
        dataset_id = rework.issue.frame_review.run.dataset_id
        if rework.annotator_id != request.user.pk and not _sees_all(request.user.pk, dataset_id):
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Rework không tồn tại.")
        return Response(rework_detail(rework))


@csrf_exempt
def rework_collection(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
    """Same route, method-specific view: GET lists, POST creates (T-040)."""

    view = ReworkListView if request.method == "GET" else ReworkCreateView
    return view.as_view()(request, *args, **kwargs)
