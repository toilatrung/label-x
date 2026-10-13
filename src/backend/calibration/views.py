"""Views for Calibration & Audit Sampling (MBE-04, E-17, E-18, E-20)."""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.models import User
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.pagination import CursorPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import HasRoleAndDatasetScope
from calibration.models import AuditSample, Benchmark
from calibration.serializers import (
    AuditSampleCreateSerializer,
    AuditSampleDetailSerializer,
    AuditSampleSerializer,
    BenchmarkCreateSerializer,
    BenchmarkImportCvatSerializer,
    BenchmarkSerializer,
    CalibrationAssignmentCreateSerializer,
    CalibrationAssignmentSerializer,
    CalibrationModelSerializer,
    CalibrationReviewerSerializer,
    PerformanceEntrySerializer,
)
from calibration.services import (
    create_benchmark,
    create_calibration_assignment,
    get_calibration_models,
    get_calibration_reviewers,
    get_performance_entries,
    import_cvat_benchmark,
    sample_audit,
)
from config.exceptions import ApiError
from config.serializers import ErrorSerializer
from runs.models import QCRun


class CalibrationCursorPagination(CursorPagination):
    page_size = 50
    ordering = "-id"


class InMemoryCursorPagination:
    """Cursor-compatible paginator for synthesized/aggregated in-memory lists."""

    def __init__(self, page_size: int = 50) -> None:
        self.page_size = page_size

    def paginate(self, items: list[dict[str, Any]], request: Request) -> dict[str, Any]:
        cursor_str = request.query_params.get("cursor")
        offset = 0
        if cursor_str and cursor_str.isdigit():
            offset = int(cursor_str)

        page_items = items[offset : offset + self.page_size]
        next_cursor = (
            str(offset + self.page_size) if (offset + self.page_size) < len(items) else None
        )
        prev_cursor = str(max(0, offset - self.page_size)) if offset > 0 else None

        return {
            "next": f"{request.build_absolute_uri(request.path)}?cursor={next_cursor}"
            if next_cursor
            else None,
            "previous": f"{request.build_absolute_uri(request.path)}?cursor={prev_cursor}"
            if prev_cursor
            else None,
            "results": page_items,
        }


class AuditSampleListCreateView(APIView):
    """GET /api/audit-samples/ & POST /api/audit-samples/."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles: tuple[Role, ...] = ()
    object_type = "audit_sample"

    def get_permissions(self) -> list[HasRoleAndDatasetScope]:
        if self.request.method == "POST":
            self.allowed_roles = (Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN)
            self.action_name = "audit_samples.create"
            self.requires_dataset = True
        else:
            self.allowed_roles = (
                Role.QA_LEAD,
                Role.QC_ADMIN,
                Role.SUPER_ADMIN,
                Role.PRODUCT_OWNER,
                Role.DATA_MODEL_OWNER,
            )
            self.action_name = "audit_samples.list"
            self.requires_dataset = False
        return super().get_permissions()  # type: ignore[return-value]

    def get_dataset_id(self, request: Request) -> int | None:
        if request.method == "POST":
            data = request.data if isinstance(request.data, dict) else {}
            raw_run_id = data.get("run_id")
            if raw_run_id is None or isinstance(raw_run_id, bool) or not str(raw_run_id).isdigit():
                return None
            run_id = int(str(raw_run_id))
            return QCRun.objects.filter(pk=run_id).values_list("dataset_id", flat=True).first()
        return None

    @extend_schema(
        operation_id="audit_samples_list",
        tags=["audit"],
        summary="Danh sách mẫu kiểm định (audit sample)",
        parameters=[
            OpenApiParameter(name="run_id", type=int, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="stream", type=str, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="cursor", type=str, location=OpenApiParameter.QUERY),
        ],
        responses={
            200: AuditSampleSerializer(many=True),
            400: ErrorSerializer,
            403: ErrorSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        qs = AuditSample.objects.all().select_related("run", "created_by")
        run_id_param = request.query_params.get("run_id")
        if run_id_param:
            if not run_id_param.isdigit():
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "run_id phải là số nguyên."
                )
            qs = qs.filter(run_id=int(run_id_param))

        stream_param = request.query_params.get("stream")
        if stream_param:
            if stream_param not in ["random", "risk"]:
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST,
                    "VALIDATION_ERROR",
                    "stream phải là random hoặc risk.",
                )
            qs = qs.filter(stream=stream_param)

        paginator = CalibrationCursorPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = AuditSampleSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        operation_id="audit_samples_create",
        tags=["audit"],
        summary="Tạo mẫu kiểm định theo stream random hoặc risk",
        request=AuditSampleCreateSerializer,
        responses={
            201: AuditSampleDetailSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
            422: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = AuditSampleCreateSerializer(data=request.data)
        if not serializer.is_valid():
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "Dữ liệu không hợp lệ.",
                serializer.errors,
            )

        data = serializer.validated_data
        sample = sample_audit(
            run_id=cast(int, data["run_id"]),
            stream=cast(str, data["stream"]),
            size=cast(int, data["size"]),
            seed=cast(int | None, data.get("seed")),
            created_by=cast(User, request.user),
            idempotency_key=request.headers.get("Idempotency-Key"),
            raw_payload=request.data if isinstance(request.data, dict) else None,
        )

        detail_serializer = AuditSampleDetailSerializer(sample)
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)


class BenchmarkListCreateView(APIView):
    """GET /api/benchmarks/ & POST /api/benchmarks/."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles: tuple[Role, ...] = ()
    object_type = "benchmark"

    def get_permissions(self) -> list[HasRoleAndDatasetScope]:
        if self.request.method == "POST":
            self.allowed_roles = (Role.QC_ADMIN, Role.SUPER_ADMIN, Role.DATA_MODEL_OWNER)
            self.action_name = "benchmarks.create"
            self.requires_dataset = True
        else:
            self.allowed_roles = (
                Role.QA_LEAD,
                Role.QC_ADMIN,
                Role.SUPER_ADMIN,
                Role.PRODUCT_OWNER,
                Role.DATA_MODEL_OWNER,
            )
            self.action_name = "benchmarks.list"
            self.requires_dataset = False
        return super().get_permissions()  # type: ignore[return-value]

    @extend_schema(
        operation_id="benchmarks_list",
        tags=["audit"],
        summary="Danh sách benchmark",
        parameters=[
            OpenApiParameter(name="dataset_id", type=int, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="cursor", type=str, location=OpenApiParameter.QUERY),
        ],
        responses={200: BenchmarkSerializer(many=True), 400: ErrorSerializer, 403: ErrorSerializer},
    )
    def get(self, request: Request) -> Response:
        qs = Benchmark.objects.all().select_related("snapshot", "created_by")
        dataset_id_param = request.query_params.get("dataset_id")
        if dataset_id_param:
            if not dataset_id_param.isdigit():
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "dataset_id phải là số nguyên."
                )
            qs = qs.filter(dataset_id=int(dataset_id_param))

        paginator = CalibrationCursorPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = BenchmarkSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        operation_id="benchmarks_create",
        tags=["audit"],
        summary="Tạo benchmark từ frame của snapshot",
        request=BenchmarkCreateSerializer,
        responses={
            201: BenchmarkSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
            422: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = BenchmarkCreateSerializer(data=request.data)
        if not serializer.is_valid():
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "Dữ liệu không hợp lệ.",
                serializer.errors,
            )

        data = serializer.validated_data
        benchmark = create_benchmark(
            name=cast(str, data["name"]),
            dataset_id=cast(int, data["dataset_id"]),
            snapshot_id=cast(int, data["snapshot_id"]),
            frame_ids=cast(list[int], data["frame_ids"]),
            created_by=cast(User, request.user),
            idempotency_key=request.headers.get("Idempotency-Key"),
            raw_payload=request.data if isinstance(request.data, dict) else None,
        )

        return Response(BenchmarkSerializer(benchmark).data, status=status.HTTP_201_CREATED)


class BenchmarkImportCvatView(APIView):
    """POST /api/benchmarks/import-cvat/."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.QC_ADMIN, Role.SUPER_ADMIN, Role.DATA_MODEL_OWNER)
    action_name = "benchmarks.import_cvat"
    object_type = "benchmark"
    requires_dataset = True

    @extend_schema(
        operation_id="benchmarks_import_cvat",
        tags=["audit"],
        summary="Nhập benchmark từ task CVAT (chỉ đọc)",
        request=BenchmarkImportCvatSerializer,
        responses={
            202: BenchmarkSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
            422: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = BenchmarkImportCvatSerializer(data=request.data)
        if not serializer.is_valid():
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "Dữ liệu không hợp lệ.",
                serializer.errors,
            )

        data = serializer.validated_data
        benchmark, _ = import_cvat_benchmark(
            name=cast(str, data["name"]),
            dataset_id=cast(int, data["dataset_id"]),
            cvat_task_id=cast(int, data["cvat_task_id"]),
            created_by=cast(User, request.user),
            idempotency_key=request.headers.get("Idempotency-Key"),
            raw_payload=request.data if isinstance(request.data, dict) else None,
        )

        return Response(BenchmarkSerializer(benchmark).data, status=status.HTTP_202_ACCEPTED)


class EvaluationPerformanceView(APIView):
    """GET /api/evaluation/performance/."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (
        Role.QA_LEAD,
        Role.QC_ADMIN,
        Role.SUPER_ADMIN,
        Role.PRODUCT_OWNER,
        Role.DATA_MODEL_OWNER,
    )
    action_name = "evaluation.performance"
    object_type = "evaluation"
    requires_dataset = False

    @extend_schema(
        operation_id="evaluation_performance",
        tags=["evaluation"],
        summary="Tổng hợp hiệu năng từ các evaluation",
        parameters=[
            OpenApiParameter(name="dataset_id", type=int, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="run_id", type=int, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="cursor", type=str, location=OpenApiParameter.QUERY),
        ],
        responses={
            200: PerformanceEntrySerializer(many=True),
            400: ErrorSerializer,
            403: ErrorSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        dataset_id_param = request.query_params.get("dataset_id")
        run_id_param = request.query_params.get("run_id")

        dataset_id: int | None = None
        if dataset_id_param:
            if not dataset_id_param.isdigit():
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "dataset_id phải là số nguyên."
                )
            dataset_id = int(dataset_id_param)

        run_id: int | None = None
        if run_id_param:
            if not run_id_param.isdigit():
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "run_id phải là số nguyên."
                )
            run_id = int(run_id_param)

        entries = get_performance_entries(dataset_id=dataset_id, run_id=run_id)
        paginator = InMemoryCursorPagination(page_size=50)
        paginated = paginator.paginate(entries, request)
        serializer = PerformanceEntrySerializer(paginated["results"], many=True)
        return Response(
            {
                "next": paginated["next"],
                "previous": paginated["previous"],
                "results": serializer.data,
            }
        )


class CalibrationReviewersListView(APIView):
    """GET /api/calibration/reviewers/."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN, Role.DATA_MODEL_OWNER)
    action_name = "calibration.reviewers_list"
    object_type = "calibration_reviewer"
    requires_dataset = False

    @extend_schema(
        operation_id="calibration_reviewers_list",
        tags=["calibration"],
        summary="Danh sách reviewer và độ hiệu chỉnh",
        parameters=[
            OpenApiParameter(name="dataset_id", type=int, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="cursor", type=str, location=OpenApiParameter.QUERY),
        ],
        responses={
            200: CalibrationReviewerSerializer(many=True),
            400: ErrorSerializer,
            403: ErrorSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        dataset_id_param = request.query_params.get("dataset_id")
        dataset_id: int | None = None
        if dataset_id_param:
            if not dataset_id_param.isdigit():
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "dataset_id phải là số nguyên."
                )
            dataset_id = int(dataset_id_param)

        reviewers = get_calibration_reviewers(dataset_id=dataset_id)
        paginator = InMemoryCursorPagination(page_size=50)
        paginated = paginator.paginate(reviewers, request)
        serializer = CalibrationReviewerSerializer(paginated["results"], many=True)
        return Response(
            {
                "next": paginated["next"],
                "previous": paginated["previous"],
                "results": serializer.data,
            }
        )


class CalibrationModelsListView(APIView):
    """GET /api/calibration/models/."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN, Role.DATA_MODEL_OWNER)
    action_name = "calibration.models_list"
    object_type = "calibration_model"
    requires_dataset = False

    @extend_schema(
        operation_id="calibration_models_list",
        tags=["calibration"],
        summary="Danh sách model và độ hiệu chỉnh",
        parameters=[
            OpenApiParameter(name="cursor", type=str, location=OpenApiParameter.QUERY),
        ],
        responses={
            200: CalibrationModelSerializer(many=True),
            400: ErrorSerializer,
            403: ErrorSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        models_data = get_calibration_models()
        paginator = InMemoryCursorPagination(page_size=50)
        paginated = paginator.paginate(models_data, request)
        serializer = CalibrationModelSerializer(paginated["results"], many=True)
        return Response(
            {
                "next": paginated["next"],
                "previous": paginated["previous"],
                "results": serializer.data,
            }
        )


class CalibrationAssignmentsCreateView(APIView):
    """POST /api/calibration/assignments/."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN)
    action_name = "calibration.assignments_create"
    object_type = "calibration_assignment"
    requires_dataset = True

    def get_dataset_id(self, request: Request) -> int | None:
        data = request.data if isinstance(request.data, dict) else {}
        raw_sample_id = data.get("audit_sample_id")
        if (
            raw_sample_id is None
            or isinstance(raw_sample_id, bool)
            or not str(raw_sample_id).isdigit()
        ):
            return None
        sample_id = int(str(raw_sample_id))
        return (
            AuditSample.objects.filter(pk=sample_id)
            .values_list("run__dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="calibration_assignments_create",
        tags=["calibration"],
        summary="Ghi nhận giao mẫu hiệu chỉnh cho reviewer hoặc model",
        request=CalibrationAssignmentCreateSerializer,
        responses={
            201: CalibrationAssignmentSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
            422: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = CalibrationAssignmentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "Dữ liệu không hợp lệ.",
                serializer.errors,
            )

        data = serializer.validated_data
        assignment = create_calibration_assignment(
            target_kind=cast(str, data["target_kind"]),
            target_id=cast(int, data["target_id"]),
            audit_sample_id=cast(int, data["audit_sample_id"]),
            note=cast(str, data.get("note", "")),
            created_by=cast(User, request.user),
            idempotency_key=request.headers.get("Idempotency-Key"),
            raw_payload=request.data if isinstance(request.data, dict) else None,
        )

        return Response(
            CalibrationAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED
        )
