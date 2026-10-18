"""QC Run REST API endpoints matching OpenAPI contract (docs/04-api/openapi.yaml)."""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Case, CharField, Count, Exists, F, OuterRef, Q, Subquery, Value, When
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
from orchestration.evaluation_read import latest_evaluations
from orchestration.models import CandidateRecord
from review import services as review_services
from review.lineage import run_lineage
from review.models import FrameReview, Lease, ReviewDecision
from runs.config_versions import create_config_version, publish_config_version
from runs.kpi import ledger_entries
from runs.models import AIModel, ConfigVersion, ModelKind, QCRun, RunRanking, WorkUnit
from runs.ranking_presentation import HAS_SUSPICIONS, PRIORITIES, run_evidence_incomplete
from runs.serializers import (
    CandidateSerializer,
    ConfigVersionCreateSerializer,
    ConfigVersionRulesSerializer,
    ConfigVersionSerializer,
    LedgerEntrySerializer,
    ModelPatchSerializer,
    ModelSerializer,
    PaginatedCandidateListSerializer,
    PaginatedConfigVersionSerializer,
    PaginatedModelListSerializer,
    PaginatedRankedFrameListSerializer,
    PaginatedRunListSerializer,
    PaginatedWorkUnitSerializer,
    RankedFrameSerializer,
    RunCreateSerializer,
    RunDetailSerializer,
    RunLineageSerializer,
    RunRetryFailedSerializer,
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
from runs.vlm_read import load_candidate_units
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
        request=None,
        responses={
            200: ConfigVersionSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
            422: ErrorSerializer,
        },
        tags=["config"],
    )
    def post(self, request: Request, pk: int) -> Response:
        try:
            config = publish_config_version(config_id=pk, actor=cast(User, request.user))
        except ConfigVersionNotFoundError as exc:
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", str(exc)) from exc
        except InvalidTransitionError as exc:
            raise ApiError(status.HTTP_409_CONFLICT, "INVALID_TRANSITION", str(exc)) from exc
        except BusinessRuleUnmetError as exc:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "BUSINESS_RULE_UNMET", str(exc)
            ) from exc
        return Response(ConfigVersionSerializer(config).data)


class ConfigVersionRulesView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles: tuple[Role, ...] = (
        Role.QA_LEAD,
        Role.QC_ADMIN,
        Role.SUPER_ADMIN,
        Role.PRODUCT_OWNER,
        Role.DATA_MODEL_OWNER,
    )
    action_name = "config_versions.rules"
    object_type = "config_version"
    requires_dataset = False
    scope_type = "system"

    @extend_schema(
        operation_id="config_versions_rules",
        tags=["config"],
        summary="Rule, ngưỡng phát hành và chính sách lấy mẫu của config version",
        responses={
            200: ConfigVersionRulesSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def get(self, request: Request, pk: int) -> Response:
        config = ConfigVersion.objects.filter(pk=pk).first()
        if config is None:
            raise ApiError(
                status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"Config version {pk} không tồn tại."
            )

        payload = config.payload or {}
        rules_data = payload.get("rules")
        if not rules_data:
            rules_data = []
            for eng_name, eng_val in (config.engines or {}).items():
                enabled = (
                    eng_val.get("enabled", True) if isinstance(eng_val, dict) else bool(eng_val)
                )
                params = (
                    {k: v for k, v in eng_val.items() if k != "enabled"}
                    if isinstance(eng_val, dict)
                    else {}
                )
                rules_data.append(
                    {
                        "rule_id": f"engine-{eng_name}",
                        "name": f"Engine {eng_name}",
                        "enabled": enabled,
                        "parameters": params,
                    }
                )

        release_thresholds = (
            (config.thresholds or {}).get("release_thresholds")
            or payload.get("release_thresholds")
            or (config.thresholds or {}).get("release")
            or {}
        )
        sampling_policy = (
            payload.get("sampling_policy") or (config.thresholds or {}).get("sampling_policy") or {}
        )

        return Response(
            {
                "config_version_id": config.pk,
                "status": config.status,
                "rules": rules_data,
                "release_thresholds": release_thresholds,
                "sampling_policy": sampling_policy,
            }
        )


class ModelListView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles: tuple[Role, ...] = (
        Role.QA_LEAD,
        Role.QC_ADMIN,
        Role.SUPER_ADMIN,
        Role.DATA_MODEL_OWNER,
    )
    action_name = "models.list"
    object_type = "model"
    requires_dataset = False
    scope_type = "system"

    @extend_schema(
        operation_id="models_list",
        parameters=[
            OpenApiParameter("kind", str, required=False, enum=[k.value for k in ModelKind]),
            OpenApiParameter("cursor", str, required=False),
        ],
        responses={
            200: PaginatedModelListSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
        },
        tags=["config"],
        summary="Danh sách model",
    )
    def get(self, request: Request) -> Response:
        queryset = AIModel.objects.all().order_by("-id")
        kind_param = request.query_params.get("kind")
        if kind_param:
            valid_kinds = {k.value for k in ModelKind}
            if kind_param not in valid_kinds:
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST,
                    "VALIDATION_ERROR",
                    f"Kind không hợp lệ. Cho phép: {sorted(valid_kinds)}",
                )
            queryset = queryset.filter(kind=kind_param)

        paginator = RunCursorPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(ModelSerializer(page, many=True).data)


class ModelUpdateView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles: tuple[Role, ...] = (Role.QC_ADMIN, Role.SUPER_ADMIN, Role.DATA_MODEL_OWNER)
    action_name = "models.update"
    object_type = "model"
    requires_dataset = False
    scope_type = "system"

    @extend_schema(
        operation_id="models_update",
        request=ModelPatchSerializer,
        responses={
            200: ModelSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
            422: ErrorSerializer,
        },
        tags=["config"],
        summary="Bật/tắt hoặc đổi phiên bản model",
    )
    def patch(self, request: Request, pk: int) -> Response:
        serializer = ModelPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            model = AIModel.objects.select_for_update().filter(pk=pk).first()
            if model is None:
                raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"Model {pk} không tồn tại.")

            if data["expected_revision"] != model.revision:
                raise ApiError(
                    status.HTTP_409_CONFLICT,
                    "INVALID_TRANSITION",
                    "expected_revision không khớp revision hiện tại.",
                )

            if self._is_model_attached_to_published_config(model):
                raise ApiError(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "BUSINESS_RULE_UNMET",
                    "Không đổi model đã gắn config version đã publish.",
                )

            before = {
                "name": model.name,
                "kind": model.kind,
                "version": model.version,
                "enabled": model.enabled,
                "revision": model.revision,
            }

            update_fields = ["revision", "updated_at"]
            if "enabled" in data:
                model.enabled = data["enabled"]
                update_fields.append("enabled")
            if "version" in data:
                model.version = data["version"]
                update_fields.append("version")

            model.revision += 1
            model.save(update_fields=update_fields)

            after = {
                "name": model.name,
                "kind": model.kind,
                "version": model.version,
                "enabled": model.enabled,
                "revision": model.revision,
            }

            append_audit_event(
                actor=cast(User, request.user),
                action="model.update",
                object_type="model",
                object_id=str(model.id),
                before=before,
                after=after,
                revision=str(model.revision),
            )

            return Response(ModelSerializer(model).data)

    def _is_model_attached_to_published_config(self, model: AIModel) -> bool:
        published_configs = ConfigVersion.objects.filter(status=ConfigVersion.Status.PUBLISHED)
        for cfg in published_configs:
            cfg_models = cfg.models or (cfg.payload or {}).get("models", {})
            if isinstance(cfg_models, dict):
                if cfg_models.get("model_id") == model.pk or cfg_models.get("id") == model.pk:
                    return True
                if (
                    cfg_models.get("name") == model.name
                    and cfg_models.get("version") == model.version
                ):
                    return True
                for _k, v in cfg_models.items():
                    if isinstance(v, dict):
                        if v.get("model_id") == model.pk or v.get("id") == model.pk:
                            return True
                        if v.get("name") == model.name and v.get("version") == model.version:
                            return True
                        if v.get("model") == model.name:
                            return True
            elif isinstance(cfg_models, list):
                for item in cfg_models:
                    if isinstance(item, dict):
                        if item.get("model_id") == model.pk or item.get("id") == model.pk:
                            return True
                        if item.get("name") == model.name and item.get("version") == model.version:
                            return True
        return False


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
            with transaction.atomic():
                run, _created = create_qc_run(
                    snapshot_id=snapshot_id,
                    config_version_id=config_version_id,
                    seed=seed,
                    metric_reference_id=data.get("metric_reference_id"),
                    created_by=user,
                    idempotency_key=key,
                )
                # Reject incomplete user requests before the run and its dispatch
                # callbacks commit. A replay still returns its original run, even
                # after successful processing has cleaned up the temporary GT.
                if _created and "metric" in run.engine_versions:
                    if run.metric_reference_id is None:
                        raise BusinessRuleUnmetError(
                            "Metric cần Ground Truth hợp lệ, đã duyệt "
                            "và thuộc đúng Snapshot đang chọn trước khi chạy."
                        )
                    if run.model_artifact_id is None:
                        raise BusinessRuleUnmetError("Metric cần model Detector đã đăng ký.")
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
        responses={
            200: RunDetailSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
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
        return Response(RunDetailSerializer(run).data)


class RunLineageView(APIView):
    """Run lineage: GET /api/runs/{id}/lineage/."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (
        Role.REVIEWER,
        Role.QA_LEAD,
        Role.QC_ADMIN,
        Role.SUPER_ADMIN,
        Role.PRODUCT_OWNER,
        Role.DATA_MODEL_OWNER,
    )
    action_name = "runs.lineage"
    object_type = "run"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            QCRun.objects.filter(pk=self.kwargs["pk"]).values_list("dataset_id", flat=True).first()
        )

    @extend_schema(
        operation_id="runs_lineage",
        responses={
            200: RunLineageSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        tags=["runs"],
    )
    def get(self, _request: Request, pk: int) -> Response:
        run = QCRun.objects.filter(pk=pk).first()
        if run is None:
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Run không tồn tại.")
        return Response(run_lineage(run))


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
        request=None,
        responses={
            200: RunSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
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
        request=RunRetryFailedSerializer,
        responses={
            202: RunSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        tags=["runs"],
    )
    def post(self, request: Request, pk: int) -> Response:
        user = cast(User, request.user)
        serializer = RunRetryFailedSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not QCRun.objects.filter(pk=pk).exists():
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Run không tồn tại.")
        try:
            if engine := serializer.validated_data.get("engine"):
                from runs.engine_retry import retry_failed_engine

                run = retry_failed_engine(run_id=pk, engine=engine, actor=user)
            else:
                run = retry_failed_qc_run(run_id=pk, actor=user)
        except InvalidTransitionError as exc:
            raise ApiError(status.HTTP_409_CONFLICT, "INVALID_TRANSITION", str(exc)) from exc
        except BusinessRuleUnmetError as exc:
            raise ApiError(status.HTTP_409_CONFLICT, "BUSINESS_RULE_UNMET", str(exc)) from exc

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
        operation_id="runs_ledger",
        responses={
            200: LedgerEntrySerializer(many=True),
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        tags=["runs"],
    )
    def get(self, _request: Request, pk: int) -> Response:
        run = QCRun.objects.prefetch_related("engine_results").get(pk=pk)
        entries = ledger_entries(run)
        return Response(LedgerEntrySerializer(entries, many=True).data)


class RunShardView(RunScopedReadView):
    action_name = "runs.shards"

    @extend_schema(
        operation_id="runs_shards",
        responses={
            200: PaginatedWorkUnitSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        tags=["runs"],
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
        serializer = CandidateSerializer(
            page,
            many=True,
            context={
                "vlm_units": load_candidate_units(c.pk for c in page or []),
                "latest_evaluations": latest_evaluations([c.pk for c in page or []]),
            },
        )
        response = paginator.get_paginated_response(serializer.data)
        response.data.update(raw_count=None, dedup_count=dedup_count)
        return response


def _annotate_review_state(entries: Any, *, run_id: int) -> Any:
    """Attach persisted, expiry-aware review state and lease holder to ranking rows.

    An open lease past its expiry is treated as already closed (same rule as
    ``review.services._close_expired``) without writing from a GET: the frame is
    incomplete when a decision was saved, otherwise unreviewed.
    """
    now = review_services._now()
    frame_reviews = FrameReview.objects.filter(
        run_id=run_id, snapshot_frame_id=OuterRef("snapshot_frame_id")
    )
    open_leases = Lease.objects.filter(
        frame_review__run_id=run_id,
        frame_review__snapshot_frame_id=OuterRef("snapshot_frame_id"),
        closed_at__isnull=True,
    )
    active = open_leases.filter(expires_at__gt=now)
    decided = ReviewDecision.objects.filter(
        issue__frame_review__run_id=run_id,
        issue__frame_review__snapshot_frame_id=OuterRef("snapshot_frame_id"),
    )
    return entries.annotate(
        stored_review_state=Subquery(frame_reviews.values("state")[:1]),
        active_lease_holder_id=Subquery(active.values("holder_id")[:1]),
        has_active_lease=Exists(active),
        has_saved_decision=Exists(decided),
    ).annotate(
        effective_review_state=Case(
            When(stored_review_state__isnull=True, then=Value(FrameReview.State.UNREVIEWED)),
            When(
                stored_review_state=FrameReview.State.IN_REVIEW,
                has_active_lease=True,
                then=Value(FrameReview.State.IN_REVIEW),
            ),
            When(
                stored_review_state=FrameReview.State.IN_REVIEW,
                has_saved_decision=True,
                then=Value(FrameReview.State.INCOMPLETE),
            ),
            When(
                stored_review_state=FrameReview.State.IN_REVIEW,
                then=Value(FrameReview.State.UNREVIEWED),
            ),
            default=F("stored_review_state"),
            output_field=CharField(),
        )
    )


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
            OpenApiParameter("family", str, required=False, enum=["E1", "E2", "E3", "structural"]),
            OpenApiParameter("origin", str, required=False, enum=["engine", "reviewer"]),
            OpenApiParameter(
                "review_state",
                str,
                required=False,
                enum=[
                    "unreviewed",
                    "in_review",
                    "incomplete",
                    "reviewed",
                    "awaiting_followup",
                    "completed",
                ],
            ),
            OpenApiParameter("q", str, required=False),
            OpenApiParameter("priority", str, required=False, enum=list(PRIORITIES)),
            OpenApiParameter("cursor", str, required=False),
        ],
        responses={
            200: PaginatedRankedFrameListSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
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

        entries = _annotate_review_state(
            ranking.entries.select_related("ranking", "snapshot_frame__snapshot_job").defer(
                "snapshot_frame__snapshot_job__normalized_json",
                "snapshot_frame__snapshot_job__skipped_shape_counts",
            ),
            run_id=pk,
        )
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
        if review_state is not None:
            entries = entries.filter(effective_review_state=review_state)

        query = request.query_params.get("q")
        if query is not None and query.strip():
            clean = query.strip()
            if ":" in clean:
                task, frame, *extra = clean.split(":")
                if extra or not task.isdigit() or not frame.isdigit():
                    entries = entries.none()
                else:
                    entries = entries.filter(
                        snapshot_frame__snapshot_job__cvat_task_id=int(task),
                        snapshot_frame__frame_index=int(frame),
                    )
            elif clean.isdigit():
                number = int(clean)
                entries = entries.filter(
                    Q(snapshot_frame__snapshot_job__cvat_task_id=number)
                    | Q(snapshot_frame__frame_index=number)
                )
            else:
                entries = entries.none()

        incomplete = run_evidence_incomplete(ranking.run)
        entries = entries.annotate(
            has_scored_suspicions=Case(When(HAS_SUSPICIONS, then=Value(True)), default=Value(False))
        )
        groups = {
            "suspected": Q(has_scored_suspicions=True),
            "unassessed": Q(has_scored_suspicions=False, missing_evidence=True),
            "no_suspicions": Q(has_scored_suspicions=False, missing_evidence=False),
        }
        if incomplete:
            groups["unassessed"] = Q(has_scored_suspicions=False)
            groups["no_suspicions"] = Q(pk__in=[])
        priority = request.query_params.get("priority")
        if priority is not None and priority not in PRIORITIES:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "priority không hợp lệ."
            )
        # Facets cover the entire filtered queue before applying the selected priority
        # or cursor, so other priority choices remain useful when a bucket is selected.
        priority_counts = entries.aggregate(
            **{name: Count("pk", filter=condition) for name, condition in groups.items()}
        )
        if priority is not None:
            entries = entries.filter(groups[priority])

        paginator = RunCursorPagination()
        paginator.ordering = "rank"
        page = paginator.paginate_queryset(entries, request, view=self)
        response = paginator.get_paginated_response(
            RankedFrameSerializer(
                page, many=True, context={"run_evidence_incomplete": incomplete}
            ).data
        )
        response.data["source"] = ranking.source
        response.data["content_hash"] = ranking.content_hash
        response.data["ranking_hash"] = ranking.ranking_hash
        response.data["priority_counts"] = priority_counts
        return response
