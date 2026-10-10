"""QC Run REST API endpoints matching OpenAPI contract (docs/04-api/openapi.yaml)."""

from __future__ import annotations

from typing import cast

from django.contrib.auth.models import User
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
from engines.interface import EngineStatus, public_status
from orchestration.models import CandidateRecord
from orchestration.services import ledger_counts
from runs.config_versions import create_config_version, publish_config_version
from runs.models import ConfigVersion, QCRun, WorkUnit
from runs.serializers import (
    CandidateSerializer,
    ConfigVersionCreateSerializer,
    ConfigVersionSerializer,
    LedgerEntrySerializer,
    PaginatedCandidateListSerializer,
    PaginatedConfigVersionSerializer,
    PaginatedRunListSerializer,
    PaginatedWorkUnitSerializer,
    RunCreateSerializer,
    RunSerializer,
    WorkUnitSerializer,
)
from runs.services import (
    BusinessRuleUnmetError,
    ConfigVersionNotFoundError,
    IdempotencyKeyReusedError,
    InvalidTransitionError,
    ScopeBusyError,
    SnapshotNotFoundError,
    cancel_qc_run,
    create_qc_run,
    retry_failed_qc_run,
)
from snapshots.models import Snapshot


class RunCursorPagination(CursorPagination):
    page_size = 50
    ordering = "-id"


class ConfigVersionListView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles: tuple[Role, ...] = (Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN)
    action_name = "config_versions.list"
    object_type = "config_version"
    requires_dataset = False

    def get_permissions(self) -> list[HasRoleAndDatasetScope]:
        self.allowed_roles = (
            (Role.QC_ADMIN, Role.SUPER_ADMIN)
            if self.request.method == "POST"
            else (Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN)
        )
        return super().get_permissions()  # type: ignore[return-value]

    @extend_schema(
        operation_id="config_versions_list",
        parameters=[OpenApiParameter("status", str, required=False)],
        responses={200: PaginatedConfigVersionSerializer},
        tags=["config"],
    )
    def get(self, request: Request) -> Response:
        queryset = ConfigVersion.objects.select_related("created_by").order_by("-id")
        selected_status = request.query_params.get("status")
        if selected_status:
            if selected_status not in (ConfigVersion.Status.DRAFT, ConfigVersion.Status.PUBLISHED):
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Status không hợp lệ."
                )
            queryset = queryset.filter(status=selected_status)
        paginator = RunCursorPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(ConfigVersionSerializer(page, many=True).data)

    @extend_schema(
        operation_id="config_versions_create",
        request=ConfigVersionCreateSerializer,
        responses={201: ConfigVersionSerializer},
        tags=["config"],
    )
    def post(self, request: Request) -> Response:
        serializer = ConfigVersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = request.headers.get("Idempotency-Key", "").strip()
        if not key or len(key) > 128:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Idempotency-Key không hợp lệ."
            )
        try:
            config = create_config_version(
                **serializer.validated_data,
                created_by=cast(User, request.user),
                idempotency_key=key,
            )
        except IdempotencyKeyReusedError as exc:
            raise ApiError(status.HTTP_409_CONFLICT, "IDEMPOTENCY_KEY_REUSED", str(exc)) from exc
        return Response(ConfigVersionSerializer(config).data, status=status.HTTP_201_CREATED)


class ConfigVersionPublishView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.QC_ADMIN, Role.SUPER_ADMIN)
    action_name = "config_versions.publish"
    object_type = "config_version"
    requires_dataset = False

    @extend_schema(
        operation_id="config_versions_publish",
        responses={200: ConfigVersionSerializer},
        tags=["config"],
    )
    def post(self, request: Request, pk: int) -> Response:
        try:
            config = publish_config_version(config_id=pk, actor=cast(User, request.user))
        except ConfigVersionNotFoundError as exc:
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", str(exc)) from exc
        except InvalidTransitionError as exc:
            raise ApiError(status.HTTP_409_CONFLICT, "INVALID_TRANSITION", str(exc)) from exc
        return Response(ConfigVersionSerializer(config).data)


class RunCollectionView(APIView):
    """Collection endpoint: GET /api/runs/ and POST /api/runs/."""

    permission_classes = [HasRoleAndDatasetScope]
    action_name = "runs.access"
    object_type = "run"
    requires_dataset = False

    def get_permissions(self) -> list[HasRoleAndDatasetScope]:
        self.allowed_roles = (
            (Role.QA_LEAD, Role.SUPER_ADMIN)
            if self.request.method == "POST"
            else (Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN)
        )
        return super().get_permissions()  # type: ignore[return-value]

    @extend_schema(
        operation_id="runs_list",
        parameters=[
            OpenApiParameter("dataset", int, required=False),
            OpenApiParameter("snapshot", int, required=False),
        ],
        responses={200: PaginatedRunListSerializer},
        tags=["runs"],
    )
    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        queryset = (
            QCRun.objects.select_related("model_artifact", "origin_run", "created_by")
            .prefetch_related("engine_results")
            .order_by("-id")
        )

        # Scope enforcement
        is_global_reader = (
            user.is_superuser
            or RoleAssignment.objects.filter(
                user=user,
                role__in=[Role.SUPER_ADMIN, Role.QC_ADMIN],
                dataset_id__isnull=True,
            ).exists()
        )

        dataset_param = request.query_params.get("dataset") or request.query_params.get(
            "dataset_id"
        )
        if dataset_param is not None:
            try:
                ds_id = int(dataset_param)
            except (ValueError, TypeError) as exc:
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST,
                    "VALIDATION_ERROR",
                    "dataset parameter phải là số nguyên.",
                ) from exc

            if not is_global_reader:
                has_perm = RoleAssignment.objects.filter(
                    user=user,
                    role__in=[Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN],
                    dataset_id=ds_id,
                ).exists()
                if not has_perm:
                    raise ApiError(
                        status.HTTP_403_FORBIDDEN, "OUT_OF_SCOPE", "Dataset ngoài phạm vi của bạn."
                    )
            queryset = queryset.filter(dataset_id=ds_id)
        else:
            if not is_global_reader:
                allowed_datasets = list(
                    RoleAssignment.objects.filter(
                        user=user,
                        role__in=[Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN],
                    ).values_list("dataset_id", flat=True)
                )
                queryset = queryset.filter(dataset_id__in=allowed_datasets)

        snapshot_param = request.query_params.get("snapshot") or request.query_params.get(
            "snapshot_id"
        )
        if snapshot_param is not None:
            try:
                snap_id = int(snapshot_param)
                queryset = queryset.filter(snapshot_id=snap_id)
            except (ValueError, TypeError) as exc:
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST,
                    "VALIDATION_ERROR",
                    "snapshot parameter phải là số nguyên.",
                ) from exc

        paginator = RunCursorPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = RunSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        operation_id="runs_create",
        request=RunCreateSerializer,
        responses={
            201: RunSerializer,
            400: RunSerializer,
            403: RunSerializer,
            404: RunSerializer,
            409: RunSerializer,
            422: RunSerializer,
        },
        tags=["runs"],
    )
    def post(self, request: Request) -> Response:
        serializer = RunCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        key = request.headers.get("Idempotency-Key", "").strip()
        if not key:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Thiếu header Idempotency-Key."
            )
        if len(key) > 128:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "Idempotency-Key không được dài quá 128 ký tự.",
            )

        data = serializer.validated_data
        snapshot_id = data["snapshot_id"]
        config_version_id = data["config_version_id"]
        seed = data["seed"]

        # Authoritative dataset lookup from snapshot
        snap = Snapshot.objects.filter(pk=snapshot_id).values("dataset_id").first()
        if snap is None:
            raise ApiError(
                status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"Snapshot {snapshot_id} không tồn tại."
            )

        dataset_id = snap["dataset_id"]
        user = cast(User, request.user)
        is_super = (
            user.is_superuser
            or RoleAssignment.objects.filter(user=user, role=Role.SUPER_ADMIN).exists()
        )
        if not is_super:
            has_perm = RoleAssignment.objects.filter(
                user=user,
                role__in=[Role.QA_LEAD, Role.SUPER_ADMIN],
                dataset_id=dataset_id,
            ).exists()
            if not has_perm:
                raise ApiError(
                    status.HTTP_403_FORBIDDEN,
                    "OUT_OF_SCOPE",
                    "Snapshot ngoài phạm vi dataset của bạn.",
                )

        try:
            run, _created = create_qc_run(
                snapshot_id=snapshot_id,
                config_version_id=config_version_id,
                seed=seed,
                created_by=user,
                idempotency_key=key,
            )
        except SnapshotNotFoundError as exc:
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", str(exc)) from exc
        except ConfigVersionNotFoundError as exc:
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", str(exc)) from exc
        except BusinessRuleUnmetError as exc:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "BUSINESS_RULE_UNMET", str(exc)
            ) from exc
        except IdempotencyKeyReusedError as exc:
            raise ApiError(status.HTTP_409_CONFLICT, "IDEMPOTENCY_KEY_REUSED", str(exc)) from exc
        except ScopeBusyError as exc:
            raise ApiError(status.HTTP_409_CONFLICT, "SCOPE_BUSY", str(exc)) from exc

        return Response(RunSerializer(run).data, status=status.HTTP_201_CREATED)


class RunDetailView(APIView):
    """Retrieve run details: GET /api/runs/{id}/."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.REVIEWER, Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN)
    action_name = "runs.retrieve"
    object_type = "run"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            QCRun.objects.filter(pk=self.kwargs["pk"]).values_list("dataset_id", flat=True).first()
        )

    @extend_schema(
        operation_id="runs_retrieve",
        responses={200: RunSerializer, 403: RunSerializer, 404: RunSerializer},
        tags=["runs"],
    )
    def get(self, _request: Request, pk: int) -> Response:
        run = (
            QCRun.objects.select_related("model_artifact", "origin_run", "created_by")
            .prefetch_related("engine_results")
            .filter(pk=pk)
            .first()
        )
        if run is None:
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Run không tồn tại.")
        return Response(RunSerializer(run).data)


class RunCancelView(APIView):
    """Cancel run: POST /api/runs/{id}/cancel/."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.QA_LEAD, Role.SUPER_ADMIN)
    action_name = "runs.cancel"
    object_type = "run"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            QCRun.objects.filter(pk=self.kwargs["pk"]).values_list("dataset_id", flat=True).first()
        )

    @extend_schema(
        operation_id="runs_cancel",
        responses={200: RunSerializer, 403: RunSerializer, 404: RunSerializer, 409: RunSerializer},
        tags=["runs"],
    )
    def post(self, request: Request, pk: int) -> Response:
        user = cast(User, request.user)
        try:
            run = cancel_qc_run(run_id=pk, actor=user)
        except InvalidTransitionError as exc:
            raise ApiError(status.HTTP_409_CONFLICT, "INVALID_TRANSITION", str(exc)) from exc

        return Response(RunSerializer(run).data, status=status.HTTP_200_OK)


class RunRetryFailedView(APIView):
    """Retry failed work units: POST /api/runs/{id}/retry-failed/."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.QA_LEAD, Role.SUPER_ADMIN)
    action_name = "runs.retry_failed"
    object_type = "run"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            QCRun.objects.filter(pk=self.kwargs["pk"]).values_list("dataset_id", flat=True).first()
        )

    @extend_schema(
        operation_id="runs_retry_failed",
        responses={202: RunSerializer, 403: RunSerializer, 404: RunSerializer, 409: RunSerializer},
        tags=["runs"],
    )
    def post(self, request: Request, pk: int) -> Response:
        user = cast(User, request.user)
        try:
            run = retry_failed_qc_run(run_id=pk, actor=user)
        except InvalidTransitionError as exc:
            raise ApiError(status.HTTP_409_CONFLICT, "INVALID_TRANSITION", str(exc)) from exc

        return Response(RunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


class RunScopedReadView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles: tuple[Role, ...] = (Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN)
    object_type = "run"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            QCRun.objects.filter(pk=self.kwargs["pk"]).values_list("dataset_id", flat=True).first()
        )


class RunLedgerView(RunScopedReadView):
    action_name = "runs.ledger"

    @extend_schema(
        operation_id="runs_ledger", responses={200: LedgerEntrySerializer(many=True)}, tags=["runs"]
    )
    def get(self, _request: Request, pk: int) -> Response:
        run = QCRun.objects.prefetch_related("engine_results").get(pk=pk)
        finished = run.status not in (QCRun.Status.QUEUED, QCRun.Status.RUNNING)
        entries = []
        for result in run.engine_results.all():
            counts = ledger_counts(pk, result.engine)
            displayed_status = result.status
            if counts.total:
                displayed_status = public_status(counts, finished=finished).value
            elif finished and displayed_status == EngineStatus.RUNNING:
                displayed_status = EngineStatus.NOT_CHECKED
            entries.append(
                {
                    "engine": result.engine,
                    "status": displayed_status,
                    "required": result.required,
                    "unit": result.unit,
                    "total": counts.total,
                    "eligible": counts.eligible,
                    "excluded": counts.excluded,
                    "applicability_version": result.applicability_version,
                    "completed": counts.completed,
                    "failed": counts.failed,
                    "pending": counts.pending,
                    "not_checked": counts.not_checked,
                    "not_checked_reasons": {
                        key.value: value for key, value in counts.not_checked_reasons.items()
                    },
                    "coverage": counts.coverage,
                }
            )
        return Response(LedgerEntrySerializer(entries, many=True).data)


class RunShardView(RunScopedReadView):
    action_name = "runs.shards"

    @extend_schema(
        operation_id="runs_shards", responses={200: PaginatedWorkUnitSerializer}, tags=["runs"]
    )
    def get(self, request: Request, pk: int) -> Response:
        queryset = WorkUnit.objects.filter(run_id=pk).order_by("-id")
        paginator = RunCursorPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(WorkUnitSerializer(page, many=True).data)


class CandidateCursorPagination(CursorPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100
    ordering = "id"


class RunCandidateListView(RunScopedReadView):
    """List candidates for a QC run: GET /api/runs/{id}/candidates/ (CR-108 Option 2)."""

    allowed_roles = (Role.REVIEWER, Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN)
    action_name = "runs.candidates"

    @extend_schema(
        operation_id="runs_candidates",
        parameters=[
            OpenApiParameter("cursor", str, required=False),
            OpenApiParameter("page_size", int, required=False),
            OpenApiParameter("engine", str, required=False),
            OpenApiParameter("family", str, required=False),
        ],
        responses={
            200: PaginatedCandidateListSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        tags=["runs"],
    )
    def get(self, request: Request, pk: int) -> Response:
        queryset = CandidateRecord.objects.filter(run_id=pk).order_by("id")
        engine_filter = request.query_params.get("engine")
        if engine_filter:
            queryset = queryset.filter(engine=engine_filter)
        family_filter = request.query_params.get("family")
        if family_filter:
            queryset = queryset.filter(family=family_filter)

        dedup_count = CandidateRecord.objects.filter(run_id=pk).count()

        paginator = CandidateCursorPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = CandidateSerializer(page, many=True)
        response = paginator.get_paginated_response(serializer.data)
        response.data.update(raw_count=None, dedup_count=dedup_count)
        return response
