"""Contract endpoints for queue claim and lease renewal."""

from drf_spectacular.utils import extend_schema
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
)
from review.models import Lease
from review.services import claim_next, renew
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
        },
        tags=["review"],
    )
    def post(self, request: Request, name: str) -> Response:
        if name not in {"risk", "random"}:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Queue không hợp lệ.")
        result = claim_next(request=request, run_id=int(request.data["run_id"]), queue=name)
        return (
            Response(result, status=status.HTTP_200_OK)
            if result
            else Response(status=status.HTTP_204_NO_CONTENT)
        )


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
