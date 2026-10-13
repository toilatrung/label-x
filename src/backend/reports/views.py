from __future__ import annotations

from django.db import transaction
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import HasRoleAndDatasetScope
from config.exceptions import ApiError
from config.serializers import ErrorSerializer
from reports.models import EffectivenessReport, ReportExport
from reports.serializers import (
    EffectivenessReportSerializer,
    ReportExportCreateSerializer,
    ReportExportSerializer,
    RunReportSerializer,
)
from reports.services import (
    ExportIdempotencyConflict,
    build_run_report,
    create_report_export,
    render_report,
)
from reports.tasks import enqueue_report_export
from runs.models import QCRun

_READ_ROLES = tuple(Role.values)
_EXPORT_ROLES = (
    Role.REVIEWER,
    Role.QA_LEAD,
    Role.QC_ADMIN,
    Role.SUPER_ADMIN,
    Role.PRODUCT_OWNER,
    Role.DATA_MODEL_OWNER,
)


class RunReportView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = _READ_ROLES
    action_name = "runs.report"
    object_type = "run"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            QCRun.objects.filter(pk=self.kwargs["pk"]).values_list("dataset_id", flat=True).first()
        )

    @extend_schema(
        operation_id="runs_report",
        responses={200: RunReportSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        tags=["reports"],
    )
    def get(self, _request: Request, pk: int) -> Response:
        run = (
            QCRun.objects.prefetch_related("engine_results", "report_exports").filter(pk=pk).first()
        )
        if run is None:
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Run không tồn tại.")
        return Response(RunReportSerializer(build_run_report(run)).data)


class RunReportExportView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = _EXPORT_ROLES
    action_name = "runs.report_export"
    object_type = "run"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            QCRun.objects.filter(pk=self.kwargs["pk"]).values_list("dataset_id", flat=True).first()
        )

    @extend_schema(
        operation_id="runs_report_export",
        parameters=[OpenApiParameter("Idempotency-Key", str, location="header", required=False)],
        request=ReportExportCreateSerializer,
        responses={
            202: ReportExportSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
            422: ErrorSerializer,
        },
        tags=["reports"],
    )
    def post(self, request: Request, pk: int) -> Response:
        serializer = ReportExportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = request.headers.get("Idempotency-Key", "").strip()
        if not key or len(key) > 128:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "Idempotency-Key bắt buộc và không được dài quá 128 ký tự.",
            )
        run = QCRun.objects.filter(pk=pk).first()
        if run is None:
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Run không tồn tại.")
        try:
            export, created = create_report_export(
                run=run,
                export_format=serializer.validated_data["format"],
                idempotency_key=key,
            )
        except ExportIdempotencyConflict as exc:
            raise ApiError(status.HTTP_409_CONFLICT, "IDEMPOTENCY_KEY_REUSED", str(exc)) from exc
        if created:
            transaction.on_commit(lambda: enqueue_report_export(export.pk))
        return Response(ReportExportSerializer(export).data, status=status.HTTP_202_ACCEPTED)


class EffectivenessReportDetailView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = _READ_ROLES
    action_name = "reports.retrieve"
    object_type = "effectiveness_report"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            EffectivenessReport.objects.filter(pk=self.kwargs["pk"])
            .values_list("input_snapshot__dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="reports_retrieve",
        parameters=[OpenApiParameter("format", str, required=False, enum=["pdf", "csv", "json"])],
        responses={
            200: EffectivenessReportSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        tags=["reports"],
    )
    def get(self, request: Request, pk: int) -> Response | HttpResponse:
        report = EffectivenessReport.objects.filter(pk=pk).first()
        if report is None:
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Báo cáo không tồn tại.")
        export_format = request.query_params.get("format", "json")
        if export_format not in ReportExport.Format.values:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Format không hợp lệ.")
        data = EffectivenessReportSerializer(report).data
        if export_format == ReportExport.Format.JSON:
            return Response(data)
        content, content_type = render_report(
            {
                "run_id": report.source_run_id,
                "snapshot_id": report.input_snapshot_id,
                "source_run_id": report.source_run_id,
                "source_reason": report.source_reason,
                "score_version": report.score_version,
                "generated_at": report.created_at,
                "metrics": report.metrics,
                "exports": [],
            },
            export_format,
        )
        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = (
            f'attachment; filename="report-{report.pk}.{export_format}"'
        )
        return response
