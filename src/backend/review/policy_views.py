"""GET /api/review-policy/: the approved, versioned policy the review UI must read."""

from __future__ import annotations

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import HasRoleAndDatasetScope
from config.exceptions import ApiError
from review.policy import ReviewPolicyNotConfigured, current_review_policy


class ReviewPolicyView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (
        Role.ANNOTATOR,
        Role.REVIEWER,
        Role.QA_LEAD,
        Role.QC_ADMIN,
        Role.SUPER_ADMIN,
    )
    action_name = "review_policy.retrieve"
    object_type = "review_policy"
    requires_dataset = False

    def get(self, _request: Request) -> Response:
        try:
            return Response(current_review_policy())
        except ReviewPolicyNotConfigured as exc:
            raise ApiError(
                status.HTTP_503_SERVICE_UNAVAILABLE, "POLICY_NOT_CONFIGURED", str(exc)
            ) from exc
