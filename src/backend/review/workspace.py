"""Read model của Review Workspace (MBE-01): gộp frame issues, lease, queue và evidence AI.

Evidence AI chỉ là đề xuất của hệ thống (classifier/Qwen): không ReviewDecision hay Adjudication
nào được tạo hay suy ra ở đây; quyết định luôn thuộc người dùng.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from orchestration.evaluation_read import (
    evaluation_reason_code,
    evaluation_review_required,
    evaluation_status,
    latest_evaluations,
)
from orchestration.models import Evaluation, VlmEvidence
from review.models import FrameReview, Issue, Lease
from vlm.config import model_source

_DECIDED_STATES = frozenset(
    {Issue.State.CONFIRMED, Issue.State.REJECTED, Issue.State.RESOLVED, Issue.State.ESCALATED}
)


def _evidence_refs(evidence: VlmEvidence | None) -> dict[str, Any] | None:
    if evidence is None:
        return None
    return {
        "evidence_id": evidence.pk,
        "unit_id": evidence.unit_id,
        "crop_sha256": evidence.crop_sha256 or None,
        "crop": evidence.crop_origin,
        "request_id": evidence.request_id or None,
        "model": evidence.model,
        "prompt_version": evidence.prompt_version,
        "policy_version": evidence.policy_version,
        "snapshot_revision": evidence.snapshot_revision,
    }


def _ai_entry(issue: Issue, evaluation: Evaluation) -> dict[str, Any]:
    unit = evaluation.vlm_unit
    evidence = getattr(unit, "evidence", None) if unit is not None else None
    if unit is None:
        source = "classifier"  # định tuyến đủ tin cậy, không cần Qwen
        suggestion = None
    else:
        source = model_source(evidence.model if evidence else unit.model)
        suggestion = (
            {
                "status": evidence.status,
                "class_name": evidence.class_name or None,
                "rationale": evidence.rationale or None,
            }
            if evidence is not None
            else None
        )
    return {
        "issue_id": issue.pk,
        "candidate_id": evaluation.candidate_id,
        "evaluation_id": evaluation.pk,
        "generation": evaluation.generation,
        "evaluation_source": evaluation.source,
        "status": evaluation_status(evaluation),
        "source": source,
        "reason_code": evaluation_reason_code(evaluation),
        "reasons": list(evaluation.reasons),
        "review_required": evaluation_review_required(evaluation),
        "suggestion": suggestion,
        "evidence_refs": _evidence_refs(evidence),
        "snapshot_revision": evaluation.snapshot_revision,
        "poll_url": f"/api/candidate-evaluations/{evaluation.pk}/",
    }


def ai_evidence(issues: list[Issue]) -> list[dict[str, Any]]:
    """Đề xuất AI mới nhất của từng issue có candidate; issue thủ công không có mục."""
    candidate_ids = [issue.candidate_id for issue in issues if issue.candidate_id]
    evaluations = latest_evaluations(candidate_ids)
    return [
        _ai_entry(issue, evaluations[issue.candidate_id])
        for issue in issues
        if issue.candidate_id in evaluations
    ]


def open_lease(frame: FrameReview) -> Lease | None:
    return (
        Lease.objects.filter(
            frame_review=frame, closed_at__isnull=True, expires_at__gt=timezone.now()
        )
        .order_by("-pk")
        .first()
    )


def lease_payload(lease: Lease | None) -> dict[str, object] | None:
    if lease is None:
        return None
    return {
        "id": lease.pk,
        "frame_id": lease.frame_review_id,
        "holder_user_id": lease.holder_id,
        "expires_at": lease.expires_at.isoformat(),
    }


def undecided_issue_count(issues: list[Issue]) -> int:
    return sum(1 for issue in issues if issue.state not in _DECIDED_STATES)
