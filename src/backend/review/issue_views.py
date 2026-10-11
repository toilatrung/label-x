"""Approved T-035 review endpoints from docs/04-api/openapi.yaml."""

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import HasRoleAndDatasetScope
from config.exceptions import ApiError
from review.decision_service import write_decision
from review.issue_service import _positive_int, complete_frame, create_manual_issue
from review.models import FrameReview, Issue
from review.serialization import (
    decision_response,
    frame_engines,
    frame_summary,
    issue_response,
)
from review.services import _deny_frame_ineligible, _reviewer_identity


class _ReviewView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.REVIEWER, Role.QA_LEAD, Role.SUPER_ADMIN)
    requires_dataset = True


class FrameIssuesView(_ReviewView):
    action_name = "frames.issues"
    object_type = "frame"

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            FrameReview.objects.filter(pk=self.kwargs["pk"])
            .values_list("run__dataset_id", flat=True)
            .first()
        )

    def get(self, request: Request, pk: int) -> Response:
        frame = FrameReview.objects.select_related(
            "run__snapshot", "snapshot_frame__snapshot_job"
        ).get(pk=pk)
        identity = _reviewer_identity(request, action="frames.issues")
        _deny_frame_ineligible(request, identity, frame, "frames.issues")
        issues = Issue.objects.filter(frame_review=frame).select_related("candidate")
        return Response(
            {
                "frame": frame_summary(frame),
                "guideline_version": frame.run.snapshot.guideline_version,
                "engines": frame_engines(frame),
                "issues": [issue_response(issue) for issue in issues.order_by("pk")],
            }
        )


class FrameCompleteView(_ReviewView):
    action_name = "frames.complete"
    object_type = "frame"

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            FrameReview.objects.filter(pk=self.kwargs["pk"])
            .values_list("run__dataset_id", flat=True)
            .first()
        )

    def post(self, request: Request, pk: int) -> Response:
        frame = complete_frame(request=request, frame_id=pk)
        return Response(frame_summary(frame))


class ManualIssueView(_ReviewView):
    action_name = "issues.create"
    object_type = "frame"

    def get_dataset_id(self, request: Request) -> int | None:
        if not isinstance(request.data, dict):
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Body không hợp lệ.")
        frame_id = _positive_int(request.data.get("frame_id"), "frame_id")
        return (
            FrameReview.objects.filter(pk=frame_id)
            .values_list("run__dataset_id", flat=True)
            .first()
        )

    def post(self, request: Request) -> Response:
        issue = create_manual_issue(request=request)
        return Response(issue_response(issue), status=status.HTTP_201_CREATED)


class IssueDetailView(_ReviewView):
    action_name = "issues.detail"
    object_type = "issue"

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            Issue.objects.filter(pk=self.kwargs["pk"])
            .values_list("frame_review__run__dataset_id", flat=True)
            .first()
        )

    def get(self, request: Request, pk: int) -> Response:
        issue = Issue.objects.select_related(
            "candidate", "frame_review__snapshot_frame__snapshot_job"
        ).get(pk=pk)
        identity = _reviewer_identity(request, action="issues.detail")
        _deny_frame_ineligible(request, identity, issue.frame_review, "issues.detail")
        return Response(issue_response(issue))


class IssueDecisionView(_ReviewView):
    action_name = "issues.decide"
    object_type = "issue"

    def get_dataset_id(self, _request: Request) -> int | None:
        return (
            Issue.objects.filter(pk=self.kwargs["pk"])
            .values_list("frame_review__run__dataset_id", flat=True)
            .first()
        )

    def post(self, request: Request, pk: int) -> Response:
        decision = write_decision(request=request, issue_id=pk)
        return Response(decision_response(decision), status=status.HTTP_201_CREATED)
