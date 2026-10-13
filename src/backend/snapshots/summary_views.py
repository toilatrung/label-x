"""MBE-06 scoped dataset summaries, revisions and snapshot run history."""

from typing import Any, cast

from django.contrib.auth.models import User
from django.db.models import Count, Max, OuterRef, Subquery
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import SYSTEM_WIDE_ROLES, Role, RoleAssignment
from accounts.permissions import HasRoleAndDatasetScope
from config.exceptions import ApiError
from config.serializers import ErrorSerializer
from review.models import FrameReview, Issue
from runs.models import QCRun
from runs.serializers import PaginatedRunListSerializer, RunSerializer
from runs.summary_pagination import SummaryCursorPagination
from runs.summary_read import CLOSED_ISSUE_STATES, REVIEWED_STATES, logical_frame_count
from runs.summary_serializers import (
    DatasetRevisionSerializer,
    DatasetSummarySerializer,
    PaginatedDatasetRevisionListSerializer,
    PaginatedDatasetSummaryListSerializer,
)
from snapshots.dataset_views import _client, _name, _positive
from snapshots.models import Snapshot, SnapshotFrame
from snapshots.summary_read import read_cvat


class SummaryPagination(SummaryCursorPagination):
    pass


class ScopedSummaryView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = tuple(Role)
    requires_dataset = True


class SnapshotRunsView(ScopedSummaryView):
    action_name = "snapshots.runs"
    object_type = "snapshot"

    def get_dataset_id(self, request: Request) -> int | None:
        return (
            Snapshot.objects.filter(pk=self.kwargs["pk"])
            .values_list("dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="snapshots_runs",
        tags=["snapshots"],
        parameters=[OpenApiParameter("cursor", str)],
        responses={
            200: PaginatedRunListSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def get(self, request: Request, pk: int) -> Response:
        runs = (
            QCRun.objects.filter(snapshot_id=pk)
            .select_related("model_artifact")
            .prefetch_related("engine_results")
            .order_by("-id")
        )
        paginator = SummaryPagination()
        page = paginator.paginate_queryset(runs, request, view=self)
        return paginator.get_paginated_response(RunSerializer(page, many=True).data)


class DatasetRevisionsView(ScopedSummaryView):
    action_name = "datasets.revisions"
    object_type = "dataset"

    def get_dataset_id(self, request: Request) -> int:
        return cast(int, self.kwargs["id"])

    @extend_schema(
        operation_id="datasets_revisions",
        tags=["datasets"],
        parameters=[OpenApiParameter("cursor", str)],
        responses={
            200: PaginatedDatasetRevisionListSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            502: ErrorSerializer,
        },
    )
    def get(self, request: Request, id: int) -> Response:
        paginator = SummaryPagination()
        paginator.decode_cursor(request)
        # Dataset identity lives in CVAT; an existing dataset without revisions is [] not 404.
        with read_cvat(_client) as cvat:
            project = cvat.get_project(id)
            if _positive(project.get("id"), "project.id") != id:
                raise ApiError(502, "BUSINESS_RULE_UNMET", "CVAT trả sai Dataset.")
        locked = Snapshot.objects.filter(dataset_id=id, status=Snapshot.Status.LOCKED).exclude(
            revision_sha256=""
        )
        latest = (
            locked.filter(revision_sha256=OuterRef("revision_sha256"))
            .order_by("-id")
            .values("id")[:1]
        )
        revisions = (
            locked.filter(pk=Subquery(latest))
            .annotate(
                frame_count=logical_frame_count("jobs__cvat_task_id", "jobs__frames__frame_index")
            )
            .order_by("-id")
        )
        page = paginator.paginate_queryset(revisions, request, view=self) or []
        rows = [
            {
                "revision": s.revision_sha256,
                "snapshot_id": s.pk,
                "frame_count": s.frame_count,
                "created_at": s.created_at,
            }
            for s in page
        ]
        return paginator.get_paginated_response(DatasetRevisionSerializer(rows, many=True).data)


class DatasetSummaryView(ScopedSummaryView):
    action_name = "datasets.summary"
    object_type = "dataset"
    requires_dataset = False

    @extend_schema(
        operation_id="datasets_summary",
        tags=["datasets"],
        parameters=[OpenApiParameter("cursor", str)],
        responses={
            200: PaginatedDatasetSummaryListSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            502: ErrorSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        raw_cursor = request.query_params.get("cursor", "0")
        if (
            not raw_cursor.isascii()
            or not raw_cursor.isdigit()
            or len(raw_cursor) > 19
            or int(raw_cursor) > 2**63 - 1
        ):
            raise ApiError(400, "VALIDATION_ERROR", "Cursor Dataset không hợp lệ.")
        after_id = int(raw_cursor)
        assignments = list(RoleAssignment.objects.filter(user=cast(User, request.user)))
        global_access = any(
            a.role in SYSTEM_WIDE_ROLES and a.dataset_id is None for a in assignments
        )
        scoped_ids = {a.dataset_id for a in assignments if a.dataset_id is not None}
        with read_cvat(_client) as cvat:
            projects = cvat.list_projects()
        visible: dict[int, str] = {}
        for project in projects:
            dataset_id = _positive(project.get("id"), "project.id")
            if (global_access or dataset_id in scoped_ids) and dataset_id > after_id:
                visible[dataset_id] = _name(project.get("name"), "project.name")
        ids = sorted(visible)[:50]
        counts = {
            r["dataset_id"]: r
            for r in Snapshot.objects.filter(dataset_id__in=ids)
            .values("dataset_id")
            .annotate(n=Count("id"), latest=Max("id"))
        }
        latest_runs = {
            r.dataset_id: r
            for r in QCRun.objects.filter(dataset_id__in=ids)
            .order_by("dataset_id", "-id")
            .distinct("dataset_id")
        }
        open_issues = {
            r["frame_review__run__dataset_id"]: r["n"]
            for r in Issue.objects.filter(frame_review__run__dataset_id__in=ids)
            .exclude(state__in=CLOSED_ISSUE_STATES)
            .values("frame_review__run__dataset_id")
            .annotate(n=Count("id"))
        }
        # Grouped queries on the page's latest runs avoid per-dataset queries.
        totals = {
            r["snapshot_job__snapshot_id"]: r["n"]
            for r in SnapshotFrame.objects.filter(
                snapshot_job__snapshot_id__in=[r.snapshot_id for r in latest_runs.values()]
            )
            .values("snapshot_job__snapshot_id")
            .annotate(n=logical_frame_count("snapshot_job__cvat_task_id", "frame_index"))
        }
        reviewed = {
            r["run_id"]: r["n"]
            for r in FrameReview.objects.filter(
                run_id__in=[r.pk for r in latest_runs.values()], state__in=REVIEWED_STATES
            )
            .values("run_id")
            .annotate(
                n=logical_frame_count(
                    "snapshot_frame__snapshot_job__cvat_task_id", "snapshot_frame__frame_index"
                )
            )
        }
        rows: list[dict[str, Any]] = []
        for dataset_id in ids:
            snapshot_stats = counts.get(dataset_id)
            run = latest_runs.get(dataset_id)
            denominator = totals.get(run.snapshot_id, 0) if run else 0
            rows.append(
                {
                    "dataset_id": dataset_id,
                    "name": visible[dataset_id],
                    "snapshot_count": snapshot_stats["n"] if snapshot_stats else 0,
                    "latest_snapshot_id": snapshot_stats["latest"] if snapshot_stats else None,
                    "latest_run_id": run.pk if run else None,
                    "open_issue_count": open_issues.get(dataset_id, 0),
                    "reviewed_ratio": reviewed.get(run.pk, 0) / denominator
                    if run and denominator
                    else None,
                }
            )
        next_url = (
            request.build_absolute_uri(f"/api/datasets/summary/?cursor={ids[-1]}")
            if len(visible) > 50
            else None
        )
        return Response(
            {
                "next": next_url,
                "previous": None,
                "results": DatasetSummarySerializer(rows, many=True).data,
            }
        )
