"""Persisted T-035 decision source for T-033 lease transitions."""

from rest_framework import status

from config.exceptions import ApiError
from orchestration.models import CandidateRecord
from review.models import FrameReview, Issue, ReviewDecision


def has_persisted_decision(frame: FrameReview) -> bool:
    return ReviewDecision.objects.filter(issue__frame_review=frame).exists()


def reset_undecided_issues(frame: FrameReview) -> None:
    """Expiry only requeues issues without a committed human decision."""
    Issue.objects.filter(frame_review=frame, state=Issue.State.IN_REVIEW).exclude(
        review_decisions__isnull=False
    ).update(state=Issue.State.PENDING_REVIEW)


def claim_undecided_issues(frame: FrameReview) -> None:
    Issue.objects.filter(frame_review=frame, state=Issue.State.PENDING_REVIEW).update(
        state=Issue.State.IN_REVIEW
    )


def materialize_candidate_issue(
    frame: FrameReview, candidate: CandidateRecord
) -> tuple[Issue, bool]:
    """Create (once) the pending issue for one immutable engine candidate."""
    anchor = candidate.anchor
    if candidate.family not in Issue.Family.values or not isinstance(anchor, dict):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "BUSINESS_RULE_UNMET",
            "Candidate family/anchor không thuộc contract review.",
        )
    objects = anchor.get("objects", [])
    count = max(len(objects) - 1, 1) if candidate.family == Issue.Family.E3 else 1
    rule = anchor.get("rule_id")
    return Issue.objects.get_or_create(
        candidate=candidate,
        defaults={
            "frame_review": frame,
            "family": candidate.family,
            "origin": Issue.Origin.ENGINE,
            "state": Issue.State.PENDING_REVIEW,
            "anchor": anchor,
            "n_i": count,
            "rule_ids": [rule] if isinstance(rule, str) and rule else [],
        },
    )


def materialize_candidate_issues(frame: FrameReview) -> None:
    """Create one issue per immutable engine candidate, only under the run row lock."""
    source = frame.snapshot_frame
    job = source.snapshot_job
    for candidate in CandidateRecord.objects.filter(
        run_id=frame.run_id, cvat_task_id=job.cvat_task_id, frame_number=source.frame_index
    ).order_by("pk"):
        materialize_candidate_issue(frame, candidate)
