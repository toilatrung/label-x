from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.models import User
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import CvatIdentity, Role
from accounts.permissions import HasRoleAndDatasetScope
from config.exceptions import ApiError
from config.serializers import ErrorSerializer
from effort.serializers import EffortEventBatchSerializer, EffortEventReceiptSerializer
from effort.services import (
    EffortEventConflictError,
    EffortPolicyError,
    ingest_effort_events,
)
from review.models import FrameReview


class EffortEventCollectionView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.REVIEWER, Role.QA_LEAD, Role.SUPER_ADMIN)
    action_name = "effort_events.create"
    object_type = "effort_event"
    requires_dataset = True

    def _raw_frame_ids(self, request: Request) -> list[int]:
        data = request.data
        raw_events = data.get("events") if isinstance(data, dict) else None
        if not isinstance(raw_events, list) or not raw_events:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "events is required.")
        ids: list[int] = []
        for event in raw_events:
            raw_id = event.get("frame_id") if isinstance(event, dict) else None
            if isinstance(raw_id, bool) or not isinstance(raw_id, int) or raw_id <= 0:
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST,
                    "VALIDATION_ERROR",
                    "Every event must contain a positive integer frame_id.",
                )
            ids.append(raw_id)
        return ids

    def get_dataset_id(self, request: Request) -> int | None:
        frame_ids = set(self._raw_frame_ids(request))
        rows = list(
            FrameReview.objects.filter(pk__in=frame_ids).values_list("pk", "run__dataset_id")
        )
        if {row[0] for row in rows} != frame_ids:
            return None
        dataset_ids = {row[1] for row in rows}
        if len(dataset_ids) != 1:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "A batch may only contain frames from one dataset.",
            )
        return dataset_ids.pop()

    @extend_schema(
        operation_id="effort_events_create",
        request=EffortEventBatchSerializer,
        responses={
            202: EffortEventReceiptSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
        tags=["evaluation"],
    )
    def post(self, request: Request) -> Response:
        actor = cast(User, request.user)
        if not CvatIdentity.objects.filter(user=actor).exists():
            raise ApiError(
                status.HTTP_403_FORBIDDEN,
                "IDENTITY_MAPPING_MISSING",
                "The actor does not have a linked CVAT identity.",
            )
        serializer = EffortEventBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            receipt = ingest_effort_events(
                actor=actor,
                events=cast(list[dict[str, Any]], serializer.validated_data["events"]),
            )
        except FrameReview.DoesNotExist as exc:
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Frame not found.") from exc
        except EffortPolicyError as exc:
            raise ApiError(status.HTTP_409_CONFLICT, exc.code, str(exc)) from exc
        except EffortEventConflictError as exc:
            raise ApiError(
                status.HTTP_409_CONFLICT,
                "IDEMPOTENCY_KEY_REUSED",
                str(exc),
            ) from exc
        return Response(
            EffortEventReceiptSerializer(
                {"accepted": receipt.accepted, "duplicates": receipt.duplicates}
            ).data,
            status=status.HTTP_202_ACCEPTED,
        )
