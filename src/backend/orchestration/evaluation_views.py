"""Evaluation API (M04C-02): POST /api/candidates/{id}/evaluations/ và GET /api/evaluations/{id}/.

POST trả 202 + `poll_url`/`Location` (kết quả chạy bất đồng bộ); 409 khi revision cũ hoặc
Idempotency-Key đã dùng cho payload/người khác; không ghi đè evidence/decision cũ. Chỉ
reviewer/QA/admin trong phạm vi dataset; FE chỉ gửi `reason` + `expected_revision`.
"""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.models import User
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import HasRoleAndDatasetScope
from config.exceptions import ApiError
from config.serializers import ErrorSerializer
from orchestration.evaluation_guard import (
    EvaluationKeyReusedError,
    EvaluationRequest,
    InvalidIdempotencyKeyError,
    StaleRevisionError,
)
from orchestration.evaluation_read import evaluation_read
from orchestration.evaluation_serializers import EvaluationCreateSerializer
from orchestration.evaluation_service import (
    EvaluationNotAllowedError,
    create_manual_evaluation,
)
from orchestration.models import CandidateRecord, Evaluation
from runs.models import QCRun
from runs.serializers import CandidateVlmSerializer

_ROLES = (Role.REVIEWER, Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN)


class EvaluationPolicySerializer(serializers.Serializer[object]):
    name = serializers.CharField()
    version = serializers.CharField()
    score_threshold = serializers.FloatField()
    margin_threshold = serializers.FloatField()
    threshold_semantics = serializers.CharField(
        help_text="routing_temporary: không phải calibration"
    )
    policy_sha256 = serializers.CharField()


class EvaluationSerializer(serializers.Serializer[object]):
    """Evaluation: quyết định định tuyến + trạng thái chạy Qwen (chỉ là đề xuất AI)."""

    id = serializers.IntegerField()
    candidate_id = serializers.IntegerField()
    run_id = serializers.IntegerField()
    generation = serializers.IntegerField()
    source: Any = serializers.CharField(help_text="auto | manual")
    status: Any = serializers.CharField(
        help_text="pending | running | completed | failed | cancelled"
    )
    reason_code = serializers.CharField(
        allow_null=True, help_text="reason_code của payload FE v0 do hệ thống tính"
    )
    reasons = serializers.ListField(child=serializers.CharField())
    review_required = serializers.BooleanField()
    call_qwen = serializers.BooleanField()
    policy = EvaluationPolicySerializer()
    checkpoint_status = serializers.CharField(allow_null=True)
    snapshot_revision = serializers.CharField()
    requested_by_user_id = serializers.IntegerField(allow_null=True)
    note = serializers.CharField(allow_null=True, help_text="Ghi chú audit, không vào prompt")
    vlm = CandidateVlmSerializer(allow_null=True)
    created_at = serializers.DateTimeField()
    poll_url = serializers.CharField()


class CandidateEvaluationCreateView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = _ROLES
    action_name = "candidates.evaluate"
    object_type = "candidate"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            CandidateRecord.objects.filter(pk=self.kwargs["pk"])
            .values_list("run__dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="candidates_evaluate",
        request=EvaluationCreateSerializer,
        parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, True)],
        responses={
            202: EvaluationSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
            422: ErrorSerializer,
        },
        tags=["runs"],
    )
    def post(self, request: Request, pk: int) -> Response:
        body = EvaluationCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        try:
            evaluation, _created = create_manual_evaluation(
                candidate_id=pk,
                actor=cast(User, request.user),
                request=EvaluationRequest(
                    candidate_id=pk,
                    reason=data["reason"],
                    expected_revision=data["expected_revision"],
                ),
                idempotency_key=request.headers.get("Idempotency-Key"),
            )
        except InvalidIdempotencyKeyError as exc:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", str(exc)) from exc
        except EvaluationKeyReusedError as exc:
            raise ApiError(status.HTTP_409_CONFLICT, "IDEMPOTENCY_KEY_REUSED", str(exc)) from exc
        except StaleRevisionError as exc:
            raise ApiError(
                status.HTTP_409_CONFLICT,
                "BUSINESS_RULE_UNMET",
                str(exc),
                details={"reason_code": "stale_revision"},
            ) from exc
        except EvaluationNotAllowedError as exc:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "BUSINESS_RULE_UNMET", str(exc)
            ) from exc
        payload = evaluation_read(evaluation)
        return Response(
            payload, status=status.HTTP_202_ACCEPTED, headers={"Location": payload["poll_url"]}
        )


class EvaluationDetailView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = _ROLES
    action_name = "evaluations.read"
    object_type = "evaluation"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        run_id = (
            Evaluation.objects.filter(pk=self.kwargs["pk"]).values_list("run_id", flat=True).first()
        )
        if run_id is None:
            return None
        return QCRun.objects.filter(pk=run_id).values_list("dataset_id", flat=True).first()

    @extend_schema(
        operation_id="evaluations_read",
        responses={
            200: EvaluationSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        tags=["runs"],
    )
    def get(self, _request: Request, pk: int) -> Response:
        evaluation = Evaluation.objects.select_related("vlm_unit__evidence").get(pk=pk)
        return Response(evaluation_read(evaluation))
