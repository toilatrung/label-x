"""Reference, KPI evaluation, gate, waiver, report (MBE-01): /api/references, evaluations, ..."""

from __future__ import annotations

import csv
import hashlib
import json
from typing import Any, cast

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import CvatIdentity, Role
from accounts.permissions import HasRoleAndDatasetScope, is_annotator_only, is_super_admin
from audit.services import append_audit_event
from config.exceptions import ApiError
from config.serializers import ErrorSerializer
from review.finalization_service import evaluate_operational_source
from review.models import FrameReview, Issue
from runs.kpi import (
    OPEN_STATES,
    WAIVABLE,
    compute_metrics,
    e_min_default,
    gate_result,
    ledger_entries,
    origin_of,
)
from runs.kpi_serializers import (
    EffectivenessReportSerializer,
    GateResultSerializer,
    KpiEvaluationCreateSerializer,
    KpiEvaluationSerializer,
    PaginatedKpiEvaluationListSerializer,
    PaginatedReferenceListSerializer,
    ReferenceCreateSerializer,
    ReferenceSerializer,
    WaiverCreateSerializer,
    WaiverDecisionSerializer,
    WaiverSerializer,
)
from runs.models import KpiEvaluation, QCRun, Reference, RunRanking, Waiver
from runs.summary_pagination import SummaryCursorPagination
from snapshots.models import Snapshot

IDEMPOTENCY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, True)
_ERRORS = {400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer}


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _idempotency_key(request: Request) -> str:
    key = (request.headers.get("Idempotency-Key") or "").strip()
    if not key or len(key) > 128:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Idempotency-Key phải có 1–128 ký tự."
        )
    return key


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _replay(model: Any, key: str, digest: str, actor: User, owner_field: str) -> Any | None:
    """Cùng key + payload + người ⇒ bản ghi cũ; khác ⇒ 409."""
    existing = model.objects.filter(idempotency_key=key).first()
    if existing is None:
        return None
    if existing.request_sha256 != digest or getattr(existing, owner_field) != actor.pk:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "IDEMPOTENCY_KEY_REUSED",
            "Idempotency-Key đã được dùng với yêu cầu khác.",
        )
    return existing


def _not_found(what: str) -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"{what} không tồn tại.")


def _body_dataset(request: Request, model: Any, field: str, path: str) -> int | None:
    data = request.data if isinstance(request.data, dict) else {}
    pk = _int(data.get(field))
    if pk is None:
        return None
    return cast("int | None", model.objects.filter(pk=pk).values_list(path, flat=True).first())


def _same_person(actor: User, other_id: int) -> bool:
    if actor.pk == other_id:
        return True
    mine = CvatIdentity.objects.filter(user_id=actor.pk).values_list("employee_id", flat=True)
    theirs = CvatIdentity.objects.filter(user_id=other_id).values_list("employee_id", flat=True)
    employees = {e for e in mine if e is not None}
    return bool(employees & {e for e in theirs if e is not None})


def _reference_read(ref: Reference) -> dict[str, Any]:
    return {
        "id": ref.pk,
        "snapshot_id": ref.snapshot_id,
        "gt_checksum": ref.gt_checksum,
        "mapping_version": ref.mapping_version,
        "matching_threshold": ref.matching_threshold,
        "minimum_area": ref.minimum_area,
        "algorithm_version": ref.algorithm_version,
        "status": ref.status,
        "created_by": ref.created_by_id,
        "locked_by": ref.locked_by_id,
        "locked_at": ref.locked_at,
    }


def _evaluation_read(ev: KpiEvaluation) -> dict[str, Any]:
    return {
        "id": ev.pk,
        "status": ev.status,
        "snapshot_id": ev.snapshot_id,
        "run_id": ev.run_id,
        "reference_id": ev.reference_id,
        "score_version": ev.score_version,
        "experiment_id": ev.experiment_id,
        "parameters": ev.parameters,
        "metrics": ev.metrics,
        "leakage_check": ev.leakage_check,
        "created_by": ev.created_by_id,
        "created_at": ev.created_at,
    }


def _waiver_read(waiver: Waiver) -> dict[str, Any]:
    state = waiver.status
    if state != Waiver.Status.REJECTED and waiver.expires_at <= timezone.now():
        state = "expired"
    return {
        "id": waiver.pk,
        "run_id": waiver.run_id,
        "condition": waiver.condition,
        "reason": waiver.reason,
        "evidence": waiver.evidence,
        "expires_at": waiver.expires_at,
        "requested_by": waiver.requested_by_id,
        "approved_by": waiver.approved_by_id,
        "status": state,
    }


class _FormatParamNegotiation(DefaultContentNegotiation):
    """`?format=` là tham số nghiệp vụ của báo cáo (json|csv|pdf), không phải chọn renderer DRF."""

    def filter_renderers(self, renderers: Any, format: str) -> Any:  # noqa: A002
        return list(renderers)


class _KpiView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    requires_dataset = True


# GET danh sách (BLOCKER-034 B-6): cùng vai trò với API đọc chi tiết; POST giữ vai trò cũ.
_LIST_ROLES = (Role.QA_LEAD, Role.SUPER_ADMIN, Role.PRODUCT_OWNER)
_DATASET_QUERY = OpenApiParameter("dataset_id", int, required=True)
_CURSOR_QUERY = OpenApiParameter("cursor", str)


class _KpiListPagination(SummaryCursorPagination):
    pass


def _positive_query(request: Request, name: str, *, required: bool) -> int | None:
    raw = request.query_params.get(name)
    if raw is None or raw == "":
        if required:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", f"Thiếu {name}.")
        return None
    if not raw.isascii() or not raw.isdigit() or len(raw) > 18 or int(raw) <= 0:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", f"{name} phải là số nguyên dương."
        )
    return int(raw)


class _ListOrCreateView(_KpiView):
    """GET đọc dataset_id từ query (bắt buộc); POST lấy Dataset từ body như trước."""

    create_roles: tuple[Role, ...] = ()

    @property
    def allowed_roles(self) -> tuple[Role, ...]:
        return _LIST_ROLES if self.request.method == "GET" else self.create_roles

    def get_dataset_id(self, request: Request) -> int | None:
        if request.method == "GET":
            return _positive_query(request, "dataset_id", required=True)
        return _body_dataset(request, Snapshot, "snapshot_id", "dataset_id")

    def paginate(self, request: Request, queryset: Any, read: Any) -> Response:
        paginator = _KpiListPagination()
        page = paginator.paginate_queryset(queryset, request, view=self) or []
        return paginator.get_paginated_response([read(row) for row in page])


class ReferenceCreateView(_ListOrCreateView):
    create_roles = (Role.QA_LEAD, Role.SUPER_ADMIN)
    object_type = "reference"

    @property
    def action_name(self) -> str:
        return "references.list" if self.request.method == "GET" else "references.create"

    @extend_schema(
        operation_id="references_list",
        parameters=[
            _DATASET_QUERY,
            OpenApiParameter("status", str, enum=[s.value for s in Reference.Status]),
            _CURSOR_QUERY,
        ],
        responses={
            200: PaginatedReferenceListSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
        },
        tags=["evaluation"],
    )
    def get(self, request: Request) -> Response:
        dataset_id = cast(int, _positive_query(request, "dataset_id", required=True))
        rows = Reference.objects.filter(snapshot__dataset_id=dataset_id)
        wanted = request.query_params.get("status")
        if wanted:
            if wanted not in Reference.Status.values:
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "status không hợp lệ."
                )
            rows = rows.filter(status=wanted)
        return self.paginate(request, rows, _reference_read)

    @extend_schema(
        operation_id="references_create",
        parameters=[IDEMPOTENCY],
        request=ReferenceCreateSerializer,
        responses={201: ReferenceSerializer, **_ERRORS, 409: ErrorSerializer},
        tags=["evaluation"],
    )
    def post(self, request: Request) -> Response:
        body = ReferenceCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        actor = cast(User, request.user)
        key = _idempotency_key(request)
        digest = _digest(data)
        existing = _replay(Reference, key, digest, actor, "created_by_id")
        if existing is not None:
            return Response(_reference_read(existing), status=status.HTTP_201_CREATED)
        snapshot = Snapshot.objects.get(pk=data["snapshot_id"])
        if snapshot.status != Snapshot.Status.LOCKED:
            raise ApiError(
                status.HTTP_409_CONFLICT, "BUSINESS_RULE_UNMET", "Snapshot chưa được khoá."
            )
        fields = {
            name: data[name]
            for name in ("matching_threshold", "minimum_area", "algorithm_version")
            if name in data
        }
        try:
            with transaction.atomic():
                ref = Reference.objects.create(
                    snapshot=snapshot,
                    gt_source=data["gt_source"],
                    gt_checksum=data["gt_checksum"].lower(),
                    mapping_version=data["mapping_version"],
                    created_by=actor,
                    idempotency_key=key,
                    request_sha256=digest,
                    **fields,
                )
                append_audit_event(
                    actor=actor,
                    action="reference.create",
                    object_type="reference",
                    object_id=ref.pk,
                    before=None,
                    after={"snapshot_id": snapshot.pk, "gt_checksum": ref.gt_checksum},
                    revision=snapshot.revision_sha256,
                )
        except IntegrityError:
            existing = _replay(Reference, key, digest, actor, "created_by_id")
            if existing is None:
                raise
            ref = existing
        return Response(_reference_read(ref), status=status.HTTP_201_CREATED)


class ReferenceLockView(_KpiView):
    allowed_roles = (Role.QA_LEAD, Role.SUPER_ADMIN)
    action_name = "references.lock"
    object_type = "reference"

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            Reference.objects.filter(pk=self.kwargs["pk"])
            .values_list("snapshot__dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="references_lock",
        parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, False)],
        request=None,
        responses={
            200: ReferenceSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        tags=["evaluation"],
    )
    def post(self, request: Request, pk: int) -> Response:
        actor = cast(User, request.user)
        with transaction.atomic():
            ref = Reference.objects.select_for_update().select_related("snapshot").get(pk=pk)
            if ref.status == Reference.Status.LOCKED:
                return Response(_reference_read(ref))  # khoá lại là no-op
            if not is_super_admin(actor) and _same_person(actor, ref.created_by_id):
                raise ApiError(
                    status.HTTP_403_FORBIDDEN,
                    "SAME_REQUESTER_APPROVER",
                    "Người khoá phải khác người lập GT.",
                )
            pending = Issue.objects.filter(
                frame_review__run__snapshot_id=ref.snapshot_id,
                state=Issue.State.ESCALATED,
                decision_cases__isnull=True,
            ).count()
            if pending:
                raise ApiError(
                    status.HTTP_409_CONFLICT,
                    "BUSINESS_RULE_UNMET",
                    "Còn bất đồng chưa được phân xử.",
                    details={"unadjudicated_issue_count": pending},
                )
            ref.status = Reference.Status.LOCKED
            ref.locked_by = actor
            ref.locked_at = timezone.now()
            ref.save(update_fields=["status", "locked_by", "locked_at"])
            append_audit_event(
                actor=actor,
                action="reference.lock",
                object_type="reference",
                object_id=ref.pk,
                before={"status": "draft"},
                after={
                    "status": "locked",
                    "gt_checksum": ref.gt_checksum,
                    "super_admin_override": is_super_admin(actor),
                },
                revision=ref.snapshot.revision_sha256,
            )
        return Response(_reference_read(ref))


class KpiEvaluationCreateView(_ListOrCreateView):
    create_roles = (Role.QA_LEAD, Role.SUPER_ADMIN, Role.PRODUCT_OWNER)
    object_type = "evaluation"

    @property
    def action_name(self) -> str:
        return "evaluations.list" if self.request.method == "GET" else "evaluations.create"

    @extend_schema(
        operation_id="evaluations_list",
        parameters=[_DATASET_QUERY, OpenApiParameter("run_id", int), _CURSOR_QUERY],
        responses={
            200: PaginatedKpiEvaluationListSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
        },
        tags=["evaluation"],
    )
    def get(self, request: Request) -> Response:
        dataset_id = cast(int, _positive_query(request, "dataset_id", required=True))
        rows = KpiEvaluation.objects.filter(run__dataset_id=dataset_id)
        run_id = _positive_query(request, "run_id", required=False)
        if run_id is not None:
            rows = rows.filter(run_id=run_id)
        return self.paginate(request, rows, _evaluation_read)

    @extend_schema(
        operation_id="evaluations_create",
        parameters=[IDEMPOTENCY],
        request=KpiEvaluationCreateSerializer,
        responses={
            202: KpiEvaluationSerializer,
            **_ERRORS,
            409: ErrorSerializer,
            422: ErrorSerializer,
        },
        tags=["evaluation"],
    )
    def post(self, request: Request) -> Response:
        body = KpiEvaluationCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        actor = cast(User, request.user)
        key = _idempotency_key(request)
        digest = _digest(data)
        existing = _replay(KpiEvaluation, key, digest, actor, "created_by_id")
        if existing is not None:
            return self._accepted(existing)
        run = QCRun.objects.filter(pk=data["run_id"]).first()
        ref = Reference.objects.filter(pk=data["reference_id"]).first()
        if run is None:
            raise _not_found("Run")
        if ref is None:
            raise _not_found("Reference")
        snapshot_id = data["snapshot_id"]
        if run.snapshot_id != snapshot_id or ref.snapshot_id != snapshot_id:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "BUSINESS_RULE_UNMET",
                "Run, reference và snapshot phải cùng một snapshot.",
            )
        if ref.status != Reference.Status.LOCKED:
            raise ApiError(
                status.HTTP_409_CONFLICT, "BUSINESS_RULE_UNMET", "Reference chưa được khoá."
            )
        if run.status != QCRun.Status.COMPLETED:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "BUSINESS_RULE_UNMET",
                "Chỉ đánh giá run đã Completed.",
            )
        params = dict(data["parameters"])
        e_min = _int(params.get("e_min"))
        if "e_min" in params and (e_min is None or e_min < 1):
            raise ApiError(
                status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "parameters.e_min phải là số ≥ 1."
            )
        params.setdefault("e_min", e_min_default())
        try:
            with transaction.atomic():
                metrics, sample = compute_metrics(run, e_min=int(params["e_min"]))
                ev = KpiEvaluation.objects.create(
                    status=(
                        KpiEvaluation.Status.INSUFFICIENT_SAMPLE
                        if sample < int(params["e_min"])
                        else KpiEvaluation.Status.COMPLETED
                    ),
                    snapshot_id=snapshot_id,
                    run=run,
                    reference=ref,
                    score_version=data["score_version"],
                    experiment_id=data.get("experiment_id"),
                    parameters=params,
                    metrics=metrics,
                    leakage_check="not_checked",  # chưa có mô hình held-out để kiểm leakage
                    created_by=actor,
                    idempotency_key=key,
                    request_sha256=digest,
                )
                append_audit_event(
                    actor=actor,
                    action="kpi_evaluation.create",
                    object_type="kpi_evaluation",
                    object_id=ev.pk,
                    before=None,
                    after={"run_id": run.pk, "reference_id": ref.pk, "status": ev.status},
                    revision=run.snapshot.revision_sha256,
                )
        except IntegrityError:
            existing = _replay(KpiEvaluation, key, digest, actor, "created_by_id")
            if existing is None:
                raise
            ev = existing
        return self._accepted(ev)

    @staticmethod
    def _accepted(ev: KpiEvaluation) -> Response:
        return Response(
            _evaluation_read(ev),
            status=status.HTTP_202_ACCEPTED,
            headers={"Location": f"/api/evaluations/{ev.pk}/"},
        )


class KpiEvaluationDetailView(_KpiView):
    allowed_roles = (Role.QA_LEAD, Role.SUPER_ADMIN, Role.PRODUCT_OWNER)
    action_name = "evaluations.read"
    object_type = "evaluation"

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            KpiEvaluation.objects.filter(pk=self.kwargs["pk"])
            .values_list("run__dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="evaluations_retrieve",
        responses={200: KpiEvaluationSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        tags=["evaluation"],
    )
    def get(self, _request: Request, pk: int) -> Response:
        return Response(_evaluation_read(KpiEvaluation.objects.get(pk=pk)))


class RunGateView(_KpiView):
    allowed_roles = (Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN, Role.PRODUCT_OWNER)
    action_name = "runs.gate"
    object_type = "run"

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            QCRun.objects.filter(pk=self.kwargs["pk"]).values_list("dataset_id", flat=True).first()
        )

    @extend_schema(
        operation_id="runs_gate",
        responses={200: GateResultSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        tags=["gate"],
    )
    def get(self, _request: Request, pk: int) -> Response:
        return Response(gate_result(QCRun.objects.get(pk=pk)))


class WaiverCreateView(_KpiView):
    allowed_roles = (Role.REVIEWER, Role.QA_LEAD)
    action_name = "waivers.create"
    object_type = "waiver"

    def get_dataset_id(self, request: Request) -> int | None:
        return _body_dataset(request, QCRun, "run_id", "dataset_id")

    @extend_schema(
        operation_id="waivers_create",
        parameters=[IDEMPOTENCY],
        request=WaiverCreateSerializer,
        responses={201: WaiverSerializer, **_ERRORS, 409: ErrorSerializer, 422: ErrorSerializer},
        tags=["gate"],
    )
    def post(self, request: Request) -> Response:
        body = WaiverCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        actor = cast(User, request.user)
        key = _idempotency_key(request)
        digest = _digest(data)
        existing = _replay(Waiver, key, digest, actor, "requested_by_id")
        if existing is not None:
            return Response(_waiver_read(existing), status=status.HTTP_201_CREATED)
        if data["condition"] not in WAIVABLE:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "BUSINESS_RULE_UNMET",
                "Chỉ coverage và agreement được waiver.",
            )
        if data["expires_at"] <= timezone.now():
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "BUSINESS_RULE_UNMET",
                "Hạn hiệu lực phải ở tương lai.",
            )
        run = QCRun.objects.get(pk=data["run_id"])
        try:
            with transaction.atomic():
                waiver = Waiver.objects.create(
                    run=run,
                    condition=data["condition"],
                    reason=data["reason"],
                    evidence=data["evidence"],
                    expires_at=data["expires_at"],
                    requested_by=actor,
                    idempotency_key=key,
                    request_sha256=digest,
                )
                append_audit_event(
                    actor=actor,
                    action="waiver.create",
                    object_type="waiver",
                    object_id=waiver.pk,
                    before=None,
                    after={"run_id": run.pk, "condition": waiver.condition},
                    revision=run.snapshot.revision_sha256,
                    reason=waiver.reason,
                )
        except IntegrityError:
            existing = _replay(Waiver, key, digest, actor, "requested_by_id")
            if existing is None:
                raise
            waiver = existing
        return Response(_waiver_read(waiver), status=status.HTTP_201_CREATED)


class WaiverApproveView(_KpiView):
    allowed_roles = (Role.QA_LEAD,)
    action_name = "waivers.approve"
    object_type = "waiver"

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            Waiver.objects.filter(pk=self.kwargs["pk"])
            .values_list("run__dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="waivers_approve",
        parameters=[IDEMPOTENCY],
        request=WaiverDecisionSerializer,
        responses={200: WaiverSerializer, **_ERRORS, 409: ErrorSerializer, 422: ErrorSerializer},
        tags=["gate"],
    )
    def post(self, request: Request, pk: int) -> Response:
        body = WaiverDecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        actor = cast(User, request.user)
        key = _idempotency_key(request)
        digest = _digest({"id": pk, **data})
        with transaction.atomic():
            waiver = Waiver.objects.select_for_update().select_related("run__snapshot").get(pk=pk)
            if waiver.status != Waiver.Status.PENDING:
                if waiver.decision_key == key and waiver.decision_sha256 == digest:
                    return Response(_waiver_read(waiver))
                raise ApiError(
                    status.HTTP_409_CONFLICT, "INVALID_TRANSITION", "Waiver đã được quyết định."
                )
            # DEC-011 / FR-SEC-04: administrative access cannot waive four-eyes approval.
            if _same_person(actor, waiver.requested_by_id):
                raise ApiError(
                    status.HTTP_403_FORBIDDEN,
                    "SAME_REQUESTER_APPROVER",
                    "Người duyệt phải khác người đề nghị.",
                )
            if waiver.expires_at <= timezone.now():
                raise ApiError(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "BUSINESS_RULE_UNMET",
                    "Waiver đã quá hạn hiệu lực.",
                )
            waiver.status = Waiver.Status.APPROVED if data["approved"] else Waiver.Status.REJECTED
            waiver.approved_by = actor
            waiver.decision_reason = data["reason"]
            waiver.decided_at = timezone.now()
            waiver.decision_key = key
            waiver.decision_sha256 = digest
            waiver.save()
            append_audit_event(
                actor=actor,
                action="waiver.approve" if data["approved"] else "waiver.reject",
                object_type="waiver",
                object_id=waiver.pk,
                before={"status": "pending"},
                after={"status": waiver.status, "super_admin_override": is_super_admin(actor)},
                revision=waiver.run.snapshot.revision_sha256,
                reason=data["reason"],
            )
        return Response(_waiver_read(waiver))


_REPORT_ROLES = (
    Role.ANNOTATOR,
    Role.REVIEWER,
    Role.QA_LEAD,
    Role.QC_ADMIN,
    Role.SUPER_ADMIN,
    Role.PRODUCT_OWNER,
    Role.DATA_MODEL_OWNER,
)


def _queue_summary(origin: QCRun, source: str) -> dict[str, Any]:
    frame_ids = list(
        RunRanking.objects.filter(run=origin, source=source).values_list(
            "entries__snapshot_frame_id", flat=True
        )
    )
    frames = FrameReview.objects.filter(run=origin, snapshot_frame_id__in=frame_ids)
    return {
        "frames_ranked": len([f for f in frame_ids if f is not None]),
        "frames_reviewed": frames.filter(
            state__in=["reviewed", "awaiting_followup", "completed"]
        ).count(),
        "open_issues": Issue.objects.filter(frame_review__in=frames, state__in=OPEN_STATES).count(),
    }


class ReportView(_KpiView):
    content_negotiation_class = _FormatParamNegotiation
    allowed_roles = _REPORT_ROLES
    action_name = "reports.retrieve"
    object_type = "report"

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            KpiEvaluation.objects.filter(pk=self.kwargs["pk"])
            .values_list("run__dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="reports_retrieve",
        parameters=[
            OpenApiParameter(
                "format", str, OpenApiParameter.QUERY, False, enum=["pdf", "csv", "json"]
            )
        ],
        responses={
            200: EffectivenessReportSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        tags=["reports"],
    )
    def get(self, request: Request, pk: int) -> Response | HttpResponse:
        fmt = request.query_params.get("format", "json")
        if fmt not in ("pdf", "csv", "json"):
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "format không hợp lệ.")
        ev = KpiEvaluation.objects.select_related("run").get(pk=pk)
        annotator_only = is_annotator_only(cast(User, request.user), dataset_id=ev.run.dataset_id)
        if annotator_only and fmt != "json":
            raise ApiError(
                status.HTTP_403_FORBIDDEN,
                "FORBIDDEN",
                "Annotator không có quyền xuất báo cáo ở định dạng này.",
            )
        if fmt == "pdf":
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "Xuất PDF chưa được hỗ trợ; dùng json hoặc csv.",
            )
        origin = origin_of(ev.run)
        source, reason, _attempts, _blockers = evaluate_operational_source(origin)
        report: dict[str, Any] = {
            "id": ev.pk,
            "input_snapshot_id": ev.snapshot_id,
            "reference_id": ev.reference_id,
            "source_run_id": source.pk,
            "source_reason": reason,
            "score_version": ev.score_version,
            "metrics": ev.metrics or {},
            "risk_queue": _queue_summary(origin, RunRanking.Source.RISK),
            "random_queue": _queue_summary(origin, RunRanking.Source.RANDOM_AUDIT),
            "engine_coverage": ledger_entries(source),
        }
        if annotator_only:
            report["risk_queue"] = {}
            report["random_queue"] = {}
            report["engine_coverage"] = []
        if fmt == "csv":
            response = HttpResponse(content_type="text/csv")
            writer = csv.writer(response)
            writer.writerow(["metric", "status", "value", "sample_size", "denominator", "method"])
            for name, metric in sorted(cast(dict[str, Any], report["metrics"]).items()):
                writer.writerow(
                    [
                        name,
                        metric["status"],
                        metric["value"],
                        metric["sample_size"],
                        metric["denominator"],
                        metric["method"],
                    ]
                )
            return response
        return Response(EffectivenessReportSerializer(report).data)
