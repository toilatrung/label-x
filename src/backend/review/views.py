"""Contract endpoints for queue claim and lease renewal."""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import HasRoleAndDatasetScope
from config.exceptions import ApiError
from config.serializers import ErrorSerializer
from review.api_serializers import (
    LeaseGrantSerializer,
    LeaseSerializer,
    QueueNextRequestSerializer,
    QueueSummarySerializer,
)
from review.models import Lease
from review.services import claim_next, current_lease, queue_summary, renew
from runs.models import QCRun


class QueueNextView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.REVIEWER, Role.QA_LEAD, Role.SUPER_ADMIN)
    action_name = "queues.next"
    object_type = "run"
    requires_dataset = True

    def get_dataset_id(self, request: Request) -> int | None:
        raw = request.data.get("run_id") if hasattr(request.data, "get") else None
        if isinstance(raw, bool) or raw is None or not str(raw).isdigit() or int(raw) <= 0:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "run_id phải là số nguyên dương."
            )
        return QCRun.objects.filter(pk=int(raw)).values_list("dataset_id", flat=True).first()

    @extend_schema(
        operation_id="queues_next",
        request=QueueNextRequestSerializer,
        responses={
            200: LeaseGrantSerializer,
            204: None,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            # BUSINESS_RULE_UNMET: a candidate's family/anchor is outside the review contract
            # (review/decision_source.py materialize_candidate_issue).
            422: ErrorSerializer,
        },
        tags=["review"],
    )
    def post(self, request: Request, name: str) -> Response:
        if name not in {"risk", "random"}:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Queue không hợp lệ.")
        frame_id = request.data.get("frame_id")
        if isinstance(frame_id, bool) or (
            frame_id is not None and (not str(frame_id).isdigit() or int(frame_id) <= 0)
        ):
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "frame_id phải là số nguyên dương.",
            )
        previous_lease_id = request.data.get("previous_lease_id")
        if previous_lease_id is not None and (
            isinstance(previous_lease_id, bool)
            or not str(previous_lease_id).isdigit()
            or int(previous_lease_id) <= 0
            or frame_id is None
        ):
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "previous_lease_id phải là số nguyên dương và cần frame_id đích.",
            )
        result = claim_next(
            request=request,
            run_id=int(request.data["run_id"]),
            queue=name,
            frame_id=int(frame_id) if frame_id is not None else None,
            previous_lease_id=int(previous_lease_id) if previous_lease_id is not None else None,
        )
        return (
            Response(result, status=status.HTTP_200_OK)
            if result
            else Response(status=status.HTTP_204_NO_CONTENT)
        )


class QueueSummaryView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.REVIEWER, Role.QA_LEAD, Role.SUPER_ADMIN)
    action_name = "queues.retrieve"
    object_type = "run"
    requires_dataset = True

    def _run_id(self, request: Request) -> int:
        raw = request.query_params.get("run_id")
        if isinstance(raw, bool) or raw is None or not str(raw).isdigit() or int(raw) <= 0:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "run_id phải là số nguyên dương."
            )
        return int(raw)

    def get_dataset_id(self, request: Request) -> int | None:
        return (
            QCRun.objects.filter(pk=self._run_id(request))
            .values_list("dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="queues_retrieve",
        parameters=[OpenApiParameter("run_id", int, required=True)],
        responses={
            200: QueueSummarySerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        tags=["review"],
    )
    def get(self, request: Request, name: str) -> Response:
        return Response(queue_summary(run_id=self._run_id(request), queue=name))


class LeaseRenewView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.REVIEWER, Role.QA_LEAD, Role.SUPER_ADMIN)
    action_name = "leases.renew"
    object_type = "lease"
    requires_dataset = True

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            Lease.objects.filter(pk=self.kwargs["pk"])
            .values_list("frame_review__run__dataset_id", flat=True)
            .first()
        )

    @extend_schema(
        operation_id="leases_renew",
        request=None,
        responses={
            200: LeaseSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        tags=["review"],
    )
    def post(self, request: Request, pk: int) -> Response:
        lease = renew(request=request, lease_id=pk)
        if lease is None:
            request_id = getattr(request, "request_id", None) or getattr(
                request._request, "request_id", ""
            )
            return Response(
                {
                    "code": "LEASE_CONFLICT",
                    "message": "Lease đã hết hạn hoặc thuộc người khác.",
                    "details": {},
                    "request_id": request_id,
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {
                "id": lease.pk,
                "frame_id": lease.frame_review_id,
                "holder_user_id": lease.holder_id,
                "expires_at": lease.expires_at.isoformat(),
            }
        )


class CurrentLeaseView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.REVIEWER, Role.QA_LEAD, Role.SUPER_ADMIN)
    action_name = "leases.current"
    object_type = "lease"
    requires_dataset = True

    def get_dataset_id(self, request: Request) -> int:
        raw = request.query_params.get("dataset_id", "")
        if not raw.isdigit() or int(raw) <= 0:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Cần dataset_id hợp lệ."
            )
        return int(raw)

    @extend_schema(
        operation_id="leases_current",
        tags=["review"],
        parameters=[OpenApiParameter("dataset_id", int, required=True)],
        responses={
            200: LeaseGrantSerializer,
            204: None,
            400: ErrorSerializer,
            403: ErrorSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        grant = current_lease(request=request, dataset_id=self.get_dataset_id(request))
        return Response(grant) if grant else Response(status=status.HTTP_204_NO_CONTENT)
