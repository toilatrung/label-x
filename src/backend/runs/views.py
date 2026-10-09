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
from runs.models import QCRun, RunRanking
from runs.serializers import (
    PaginatedRankedFrameListSerializer,
    PaginatedRunListSerializer,
    RankedFrameSerializer,
    RunCreateSerializer,
    RunSerializer,
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
        is_super = (
            user.is_superuser
            or RoleAssignment.objects.filter(user=user, role=Role.SUPER_ADMIN).exists()
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

            if not is_super:
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
            if not is_super:
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


class RunRankingView(APIView):
    """Read a persisted risk or independent random-audit queue for one run."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.REVIEWER, Role.QA_LEAD, Role.SUPER_ADMIN)
    action_name = "runs.ranking"
    object_type = "run"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            QCRun.objects.filter(pk=self.kwargs["pk"]).values_list("dataset_id", flat=True).first()
        )

    @extend_schema(
        operation_id="runs_ranking",
        parameters=[
            OpenApiParameter("queue", str, required=False, enum=["risk", "random"]),
            OpenApiParameter("family", str, required=False),
            OpenApiParameter("origin", str, required=False, enum=["engine", "reviewer"]),
            OpenApiParameter("review_state", str, required=False),
        ],
        responses={200: PaginatedRankedFrameListSerializer},
        tags=["runs"],
    )
    def get(self, request: Request, pk: int) -> Response:
        if not QCRun.objects.filter(pk=pk).exists():
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Run không tồn tại.")

        queue = request.query_params.get("queue", "risk")
        source_by_queue = {
            "risk": RunRanking.Source.RISK,
            "random": RunRanking.Source.RANDOM_AUDIT,
        }
        if queue not in source_by_queue:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "queue phải là 'risk' hoặc 'random'.",
            )
        ranking = RunRanking.objects.filter(run_id=pk, source=source_by_queue[queue]).first()
        if ranking is None:
            raise ApiError(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                "Run chưa có ranking đã lưu cho queue này.",
            )

        entries = ranking.entries.select_related("ranking", "snapshot_frame__snapshot_job")
        family = request.query_params.get("family")
        if family is not None:
            if family not in {"E1", "E2", "E3", "structural"}:
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST,
                    "VALIDATION_ERROR",
                    "family không hợp lệ.",
                )
            entries = entries.filter(issue_counts__has_key=family)  # noqa: E711

        origin = request.query_params.get("origin")
        if origin not in {None, "engine", "reviewer"}:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "origin không hợp lệ.")
        if origin == "reviewer":
            entries = entries.none()

        review_state = request.query_params.get("review_state")
        valid_review_states = {
            "unreviewed",
            "in_review",
            "incomplete",
            "reviewed",
            "awaiting_followup",
            "completed",
        }
        if review_state is not None and review_state not in valid_review_states:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "review_state không hợp lệ.",
            )
        if review_state not in {None, "unreviewed"}:
            entries = entries.none()

        paginator = RunCursorPagination()
        paginator.ordering = "rank"
        page = paginator.paginate_queryset(entries, request, view=self)
        response = paginator.get_paginated_response(RankedFrameSerializer(page, many=True).data)
        response.data["source"] = ranking.source
        response.data["content_hash"] = ranking.content_hash
        response.data["ranking_hash"] = ranking.ranking_hash
        return response
