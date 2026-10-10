"""Dataset selectors backed by CVAT projects; dataset_id equals CVAT project ID."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import httpx
from django.conf import settings
from django.contrib.auth.models import User
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import SYSTEM_WIDE_ROLES, Role, RoleAssignment
from accounts.permissions import HasRoleAndDatasetScope
from config.exceptions import ApiError
from cvat_adapter.client import CvatReadClient


class DatasetSerializer(serializers.Serializer[dict[str, Any]]):
    id = serializers.IntegerField()
    name = serializers.CharField()
    cvat_project_id = serializers.IntegerField()
    taxonomy_version = serializers.CharField(allow_null=True, required=False, default=None)
    guideline_version = serializers.CharField(allow_null=True, required=False, default=None)


class PaginatedDatasetSerializer(serializers.Serializer[dict[str, Any]]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = DatasetSerializer(many=True)


class CvatJobSerializer(serializers.Serializer[dict[str, Any]]):
    cvat_job_id = serializers.IntegerField()
    assignee_cvat_user_id = serializers.IntegerField(allow_null=True)
    frame_count = serializers.IntegerField(required=False)
    updated_date = serializers.DateTimeField()


class CvatTaskSerializer(serializers.Serializer[dict[str, Any]]):
    cvat_task_id = serializers.IntegerField()
    name = serializers.CharField()
    jobs = CvatJobSerializer(many=True)


def _positive(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ApiError(status.HTTP_502_BAD_GATEWAY, "BUSINESS_RULE_UNMET", f"CVAT thiếu {field}.")
    return value


def _name(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiError(status.HTTP_502_BAD_GATEWAY, "BUSINESS_RULE_UNMET", f"CVAT thiếu {field}.")
    return value


def _related_id(data: Mapping[str, object], name: str) -> object:
    value = data.get(f"{name}_id")
    if value is not None:
        return value
    relation = data.get(name)
    return relation.get("id") if isinstance(relation, Mapping) else None


def _client() -> CvatReadClient:
    return CvatReadClient(settings.CVAT_BASE_URL, settings.CVAT_SERVICE_TOKEN)


class DatasetListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="datasets_list",
        parameters=[
            OpenApiParameter(
                name="cursor",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Con trỏ trang từ trường next/previous (CursorPagination, PAGE_SIZE=50)"
                ),
            ),
        ],
        responses={
            200: PaginatedDatasetSerializer,
            400: OpenApiResponse(description="Cursor Dataset không hợp lệ."),
            403: OpenApiResponse(description="Không có phạm vi Dataset."),
            502: OpenApiResponse(description="Không đọc được project CVAT."),
        },
        tags=["datasets"],
    )
    def get(self, request: Request) -> Response:
        cursor_text = request.query_params.get("cursor")
        if cursor_text:
            if not cursor_text.isdigit() or int(cursor_text) < 0:
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Cursor Dataset không hợp lệ."
                )
            after_id = int(cursor_text)
        else:
            after_id = 0
        assignments = list(RoleAssignment.objects.filter(user=cast(User, request.user)))
        if not assignments:
            raise ApiError(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Không có phạm vi Dataset.")
        global_access = any(
            item.role in SYSTEM_WIDE_ROLES and item.dataset_id is None for item in assignments
        )
        scoped_ids = {item.dataset_id for item in assignments if item.dataset_id is not None}
        try:
            with _client() as cvat:
                projects: list[dict[str, object]] = []
                if global_access:
                    projects = cvat.list_projects()
                else:
                    for id_ in sorted(scoped_ids):
                        try:
                            projects.append(cvat.get_project(id_))
                        except httpx.HTTPStatusError as exc:
                            if exc.response.status_code == 404:
                                continue
                            raise
        except (httpx.HTTPError, RuntimeError, ValueError, TypeError) as exc:
            raise ApiError(
                status.HTTP_502_BAD_GATEWAY, "BUSINESS_RULE_UNMET", "Không đọc được project CVAT."
            ) from exc
        results: list[dict[str, Any]] = []
        for project in projects:
            project_id = _positive(project.get("id"), "project.id")
            if global_access or project_id in scoped_ids:
                results.append(
                    {
                        "id": project_id,
                        "cvat_project_id": project_id,
                        "name": _name(project.get("name"), "project.name"),
                        "taxonomy_version": None,
                        "guideline_version": None,
                    }
                )
        results.sort(key=lambda item: cast(int, item["id"]))
        remaining = [item for item in results if cast(int, item["id"]) > after_id]
        page = remaining[:50]
        next_url = (
            request.build_absolute_uri(f"/api/datasets/?cursor={page[-1]['id']}")
            if len(remaining) > 50
            else None
        )
        return Response({"next": next_url, "previous": None, "results": page})


class DatasetTasksView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN)
    action_name = "datasets.tasks"
    object_type = "dataset"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        raw = self.kwargs.get("id") or self.kwargs.get("dataset_id")
        return int(raw) if raw is not None and str(raw).isdigit() else None

    @extend_schema(
        operation_id="datasets_tasks",
        parameters=[
            OpenApiParameter(
                name="id",
                type=int,
                location=OpenApiParameter.PATH,
                description="ID của dataset (CVAT project ID)",
            ),
        ],
        responses={
            200: CvatTaskSerializer(many=True),
            400: OpenApiResponse(description="Yêu cầu không hợp lệ."),
            403: OpenApiResponse(description="Không có quyền truy cập Dataset."),
            404: OpenApiResponse(description="Dataset không tồn tại."),
            502: OpenApiResponse(description="Không đọc được Task/Job CVAT."),
        },
        tags=["datasets"],
    )
    def get(
        self, _request: Request, id: int | None = None, dataset_id: int | None = None
    ) -> Response:
        target_id = id if id is not None else dataset_id
        if target_id is None:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Thiếu ID Dataset.")
        try:
            with _client() as cvat:
                try:
                    cvat.get_project(target_id)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        raise ApiError(
                            status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Dataset không tồn tại."
                        ) from exc
                    raise
                tasks = cvat.list_tasks(project_id=target_id)
                output: list[dict[str, Any]] = []
                for task in tasks:
                    task_id = _positive(task.get("id"), "task.id")
                    project_id = _related_id(task, "project")
                    if _positive(project_id, "task.project_id") != target_id:
                        raise ApiError(
                            status.HTTP_502_BAD_GATEWAY,
                            "BUSINESS_RULE_UNMET",
                            "Task nằm ngoài Dataset.",
                        )
                    jobs: list[dict[str, Any]] = []
                    for job in cvat.list_jobs(task_id=task_id):
                        job_id = _positive(job.get("id"), "job.id")
                        linked_task = _related_id(job, "task")
                        if _positive(linked_task, "job.task_id") != task_id:
                            raise ApiError(
                                status.HTTP_502_BAD_GATEWAY,
                                "BUSINESS_RULE_UNMET",
                                "Job nằm ngoài Task.",
                            )
                        assignee = job.get("assignee")
                        if isinstance(assignee, dict):
                            assignee = assignee.get("id")
                        frame_count = job.get("frame_count")
                        row = {
                            "cvat_job_id": job_id,
                            "assignee_cvat_user_id": _positive(assignee, "job.assignee")
                            if assignee is not None
                            else None,
                            "updated_date": _name(job.get("updated_date"), "job.updated_date"),
                        }
                        if isinstance(frame_count, int) and frame_count >= 0:
                            row["frame_count"] = frame_count
                        jobs.append(row)
                    output.append(
                        {
                            "cvat_task_id": task_id,
                            "name": _name(task.get("name"), "task.name"),
                            "jobs": sorted(jobs, key=lambda job: cast(int, job["cvat_job_id"])),
                        }
                    )
        except ApiError:
            raise
        except (httpx.HTTPError, RuntimeError, ValueError, TypeError) as exc:
            raise ApiError(
                status.HTTP_502_BAD_GATEWAY, "BUSINESS_RULE_UNMET", "Không đọc được Task/Job CVAT."
            ) from exc
        return Response(sorted(output, key=lambda task: cast(int, task["cvat_task_id"])))
