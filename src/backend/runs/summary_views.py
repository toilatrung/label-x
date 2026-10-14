"""MBE-06 run statistics endpoints, guarded by authoritative dataset scope."""

from typing import Any, cast

from django.contrib.auth.models import User
from django.db.models import Count
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import Role
from config.exceptions import ApiError
from config.serializers import ErrorSerializer
from review.models import Issue
from runs.models import QCRun
from runs.summary_pagination import SummaryCursorPagination
from runs.summary_read import (
    candidate_categories,
    engine_stats,
    frames_for_run,
    logical_frame_count,
    ratio,
    review_volume,
    reviewed_for_run,
    run_metrics,
)
from runs.summary_serializers import (
    CandidateCategoriesSerializer,
    PaginatedTaskQualityListSerializer,
    ReviewVolumeQuerySerializer,
    ReviewVolumeSerializer,
    RunEngineStatsSerializer,
    RunMetricsSerializer,
    TaskQualitySerializer,
)
from runs.views import RunScopedReadView
from snapshots.dataset_views import _client, _name, _positive, _related_id
from snapshots.summary_read import read_cvat


class TaskQualityPagination(SummaryCursorPagination):
    ordering = "cvat_task_id"


class SummaryReadView(RunScopedReadView):
    allowed_roles = tuple(Role)

    def run(self, pk: int) -> QCRun:
        run = QCRun.objects.filter(pk=pk).first()
        if run is None:
            raise ApiError(404, "NOT_FOUND", "Run không tồn tại.")
        return run


class RunMetricsView(SummaryReadView):
    action_name = "runs.metrics"

    @extend_schema(
        operation_id="runs_metrics",
        tags=["runs"],
        responses={200: RunMetricsSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    )
    def get(self, request: Request, pk: int) -> Response:
        return Response(RunMetricsSerializer(run_metrics(self.run(pk))).data)


class RunEnginesStatsView(SummaryReadView):
    action_name = "runs.engines"

    @extend_schema(
        operation_id="runs_engines_stats",
        tags=["runs"],
        responses={200: RunEngineStatsSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    )
    def get(self, request: Request, pk: int) -> Response:
        return Response(RunEngineStatsSerializer(engine_stats(self.run(pk))).data)


class RunReviewVolumeView(SummaryReadView):
    action_name = "runs.review_volume"

    @extend_schema(
        operation_id="runs_review_volume",
        tags=["runs"],
        parameters=[ReviewVolumeQuerySerializer],
        responses={
            200: ReviewVolumeSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def get(self, request: Request, pk: int) -> Response:
        query = ReviewVolumeQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(
            ReviewVolumeSerializer(review_volume(self.run(pk), query.validated_data)).data
        )


class RunCandidateCategoriesView(SummaryReadView):
    action_name = "runs.candidate_categories"

    @extend_schema(
        operation_id="runs_candidate_categories",
        tags=["runs"],
        responses={200: CandidateCategoriesSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    )
    def get(self, request: Request, pk: int) -> Response:
        return Response(CandidateCategoriesSerializer(candidate_categories(self.run(pk))).data)


class RunTasksQualityView(SummaryReadView):
    action_name = "runs.tasks_quality"

    @extend_schema(
        operation_id="runs_tasks_quality",
        tags=["runs"],
        parameters=[OpenApiParameter("cursor", str)],
        responses={
            200: PaginatedTaskQualityListSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            502: ErrorSerializer,
        },
    )
    def get(self, request: Request, pk: int) -> Response:
        run = self.run(pk)
        tasks = run.snapshot.jobs.order_by("cvat_task_id").values("cvat_task_id").distinct()
        paginator = TaskQualityPagination()
        page = paginator.paginate_queryset(tasks, request, view=self) or []
        task_ids = [row["cvat_task_id"] for row in page]
        if not task_ids:
            return paginator.get_paginated_response([])
        # One CVAT list operation, not get_task per row. Paginated upstream by the adapter.
        with read_cvat(lambda: _client(cast(User, request.user))) as cvat:
            source = cvat.list_tasks(project_id=run.dataset_id)
        if any(
            _positive(_related_id(row, "project"), "task.project_id") != run.dataset_id
            for row in source
        ):
            raise ApiError(502, "BUSINESS_RULE_UNMET", "CVAT trả Task ngoài Dataset.")
        names = {
            _positive(row.get("id"), "task.id"): _name(row.get("name"), "task.name")
            for row in source
        }
        if any(task_id not in names for task_id in task_ids):
            raise ApiError(502, "BUSINESS_RULE_UNMET", "CVAT không còn task của snapshot.")
        totals = {
            r["snapshot_job__cvat_task_id"]: r["n"]
            for r in frames_for_run(run)
            .filter(snapshot_job__cvat_task_id__in=task_ids)
            .values("snapshot_job__cvat_task_id")
            .annotate(n=logical_frame_count("snapshot_job__cvat_task_id", "frame_index"))
        }
        reviewed = {
            r["snapshot_frame__snapshot_job__cvat_task_id"]: r["n"]
            for r in reviewed_for_run(run)
            .filter(snapshot_frame__snapshot_job__cvat_task_id__in=task_ids)
            .values("snapshot_frame__snapshot_job__cvat_task_id")
            .annotate(
                n=logical_frame_count(
                    "snapshot_frame__snapshot_job__cvat_task_id", "snapshot_frame__frame_index"
                )
            )
        }
        issues = {
            r["frame_review__snapshot_frame__snapshot_job__cvat_task_id"]: r["n"]
            for r in Issue.objects.filter(
                frame_review__run=run,
                frame_review__snapshot_frame__snapshot_job__cvat_task_id__in=task_ids,
            )
            .values("frame_review__snapshot_frame__snapshot_job__cvat_task_id")
            .annotate(n=Count("id"))
        }
        rows: list[dict[str, Any]] = []
        for task_id in task_ids:
            total = totals.get(task_id, 0)
            rows.append(
                {
                    "cvat_task_id": task_id,
                    "name": names[task_id],
                    "frames": total,
                    "issues": issues.get(task_id, 0),
                    "issue_rate": ratio(issues.get(task_id, 0), total),
                    "reviewed_ratio": ratio(reviewed.get(task_id, 0), total),
                }
            )
        return paginator.get_paginated_response(TaskQualitySerializer(rows, many=True).data)
