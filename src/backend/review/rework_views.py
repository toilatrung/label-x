"""HTTP endpoints for the approved T-040 rework contract."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import HasRoleAndDatasetScope
from config.serializers import ErrorSerializer
from review.api_serializers import (
    IDEMPOTENCY_KEY_PARAM,
    ReworkCreateRequestSerializer,
    ReworkRequestSerializer,
    ReworkSubmissionRequestSerializer,
    ReworkVerifyRequestSerializer,
)
from review.models import Issue, ReworkRequest
from review.rework_service import create_rework, rework_response, submit_rework, verify_rework


class ReworkCreateView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.REVIEWER, Role.QA_LEAD, Role.SUPER_ADMIN)
    action_name = "rework.create"
    object_type = "issue"
    requires_dataset = True

    def get_dataset_id(self, request: Request) -> int | None:
        if not isinstance(request.data, dict):
            return None
        issue_id = request.data.get("issue_id")
        if isinstance(issue_id, bool) or not isinstance(issue_id, int):
            return None
        return (
            Issue.objects.filter(pk=issue_id)
            .values_list("frame_review__run__dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="rework_create",
        parameters=[IDEMPOTENCY_KEY_PARAM],
        request=ReworkCreateRequestSerializer,
        responses={
            201: ReworkRequestSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        tags=["rework"],
    )
    def post(self, request: Request) -> Response:
        rework = create_rework(request=request)
        return Response(rework_response(rework), status=status.HTTP_201_CREATED)


class ReworkSubmittedView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.ANNOTATOR, Role.SUPER_ADMIN)
    action_name = "rework.submitted"
    object_type = "rework"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            ReworkRequest.objects.filter(pk=self.kwargs["pk"])
            .values_list("issue__frame_review__run__dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="rework_submitted",
        parameters=[IDEMPOTENCY_KEY_PARAM],
        request=ReworkSubmissionRequestSerializer,
        responses={
            202: ReworkRequestSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: OpenApiResponse(
                ErrorSerializer,
                description=(
                    "INVALID_TRANSITION | IDEMPOTENCY_KEY_REUSED | REVISION_UNCHANGED "
                    "(revision or snapshot already used by the original or an earlier round)."
                ),
            ),
        },
        tags=["rework"],
    )
    def post(self, request: Request, pk: int) -> Response:
        rework = submit_rework(request=request, rework_id=pk)
        return Response(rework_response(rework), status=status.HTTP_202_ACCEPTED)


class ReworkVerifyView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.REVIEWER, Role.SUPER_ADMIN)
    action_name = "rework.verify"
    object_type = "rework"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            ReworkRequest.objects.filter(pk=self.kwargs["pk"])
            .values_list("issue__frame_review__run__dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="rework_verify",
        parameters=[IDEMPOTENCY_KEY_PARAM],
        request=ReworkVerifyRequestSerializer,
        responses={
            200: ReworkRequestSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        tags=["rework"],
    )
    def post(self, request: Request, pk: int) -> Response:
        rework = verify_rework(request=request, rework_id=pk)
        return Response(rework_response(rework))
