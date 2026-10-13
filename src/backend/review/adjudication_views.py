"""API views for T-038 escalation and adjudication."""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import HasRoleAndDatasetScope
from config.serializers import ErrorSerializer
from review.adjudication_service import (
    adjudicate_issue,
    get_decision_case,
    list_decision_cases,
    list_escalations,
)
from review.api_serializers import IDEMPOTENCY_KEY_PARAM, PaginatedEscalationSerializer
from review.case_serializers import (
    AdjudicationCreateSerializer,
    DecisionCaseDetailSerializer,
    DecisionCaseSerializer,
    PaginatedDecisionCaseSerializer,
)
from review.models import DecisionCase, Issue


class EscalationsListView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.QA_LEAD, Role.SUPER_ADMIN)
    action_name = "escalations.list"
    object_type = "issue"
    requires_dataset = False

    def get_dataset_id(self, request: Request) -> int | None:
        return None

    @extend_schema(
        operation_id="escalations_list",
        parameters=[
            OpenApiParameter("run", int, required=False),
            OpenApiParameter("cursor", str, required=False),
        ],
        responses={
            200: PaginatedEscalationSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        tags=["review"],
    )
    def get(self, request: Request) -> Response:
        data = list_escalations(request)
        return Response(data)


class IssueAdjudicationView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.QA_LEAD, Role.SUPER_ADMIN)
    action_name = "issues.adjudicate"
    object_type = "issue"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            Issue.objects.filter(pk=self.kwargs["pk"])
            .values_list("frame_review__run__dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="issues_adjudicate",
        parameters=[IDEMPOTENCY_KEY_PARAM],
        request=AdjudicationCreateSerializer,
        responses={
            201: DecisionCaseSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
            422: ErrorSerializer,
        },
        tags=["review"],
    )
    def post(self, request: Request, pk: int) -> Response:
        payload = adjudicate_issue(request=request, issue_id=pk)
        return Response(payload, status=status.HTTP_201_CREATED)


class DecisionCaseDetailView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.REVIEWER, Role.QA_LEAD, Role.SUPER_ADMIN)
    action_name = "decision_cases.detail"
    object_type = "decision_case"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            DecisionCase.objects.filter(pk=self.kwargs["pk"])
            .values_list("issue__frame_review__run__dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="decision_cases_detail",
        responses={
            200: DecisionCaseDetailSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        tags=["review"],
    )
    def get(self, request: Request, pk: int) -> Response:
        payload = get_decision_case(request=request, case_id=pk)
        return Response(payload)


class DecisionCaseListView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.REVIEWER, Role.QA_LEAD, Role.SUPER_ADMIN)
    action_name = "decision_cases.list"
    object_type = "decision_case"
    requires_dataset = False

    def get_dataset_id(self, _request: Request) -> int | None:
        return None

    @extend_schema(
        operation_id="decision_cases_list",
        parameters=[
            OpenApiParameter("rule_id", str, required=False),
            OpenApiParameter("issue", int, required=False),
            OpenApiParameter("version", str, required=False),
            OpenApiParameter(
                "outcome", str, required=False, enum=["confirm", "reject", "guideline_gap"]
            ),
            OpenApiParameter("cursor", str, required=False),
        ],
        responses={
            200: PaginatedDecisionCaseSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
        },
        tags=["review"],
    )
    def get(self, request: Request) -> Response:
        payload = list_decision_cases(request)
        return Response(payload)
