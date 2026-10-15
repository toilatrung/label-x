"""Transactional reviewer decisions sharing T-033's PostgreSQL lock order."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.request import Request

from accounts.models import Role, RoleAssignment
from accounts.permissions import record_rejection_audit
from audit.services import append_audit_event
from config.exceptions import ApiError
from guideline.models import GuidelineRule
from review.models import FrameReview, Issue, Lease, ReviewDecision
from review.services import (
    _actor,
    _deny_frame_ineligible,
    _now,
    _reviewer_identity,
    has_review_scope,
)
from runs.models import QCRun


def _body(request: Request) -> dict[str, Any]:
    if not isinstance(request.data, dict):
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Body phải là JSON object.")
    return request.data


def _idempotency(request: Request) -> str | None:
    raw = request.headers.get("Idempotency-Key")
    if raw is None:
        return None
    try:
        key = str(uuid.UUID(raw))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Idempotency-Key phải là UUID."
        ) from exc
    if key != raw.lower():
        raise ApiError(
            status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Idempotency-Key không chuẩn."
        )
    return key


def _request_hash(body: dict[str, Any]) -> str:
    try:
        payload = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "JSON không hợp lệ."
        ) from exc
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _role(user: User, dataset_id: int) -> str:
    assignments = set(
        RoleAssignment.objects.filter(user=user)
        .filter(Q(dataset_id=dataset_id) | Q(role=Role.SUPER_ADMIN, dataset_id__isnull=True))
        .values_list("role", flat=True)
    )
    for role in (Role.SUPER_ADMIN, Role.QA_LEAD, Role.REVIEWER):
        if role in assignments:
            return str(role)
    raise ApiError(status.HTTP_403_FORBIDDEN, "OUT_OF_SCOPE", "Không có quyền review.")


def _deny_lease(request: Request, lease_id: int, action: str) -> None:
    record_rejection_audit(
        request=request,
        code="LEASE_CONFLICT",
        object_type="lease",
        object_id=lease_id,
        action=action,
        message="Lease expired, wrong holder, or wrong frame.",
    )
    raise ApiError(status.HTTP_409_CONFLICT, "LEASE_CONFLICT", "Lease không còn hợp lệ.")


def _owned_lease(
    request: Request, *, frame: FrameReview, lease_id: int, action: str = "issues.decide"
) -> tuple[Lease, str]:
    """Caller already holds user then run row locks before entering here."""
    user = _actor(request)
    role = _authorize_frame(request, frame=frame, action=action)
    lease = Lease.objects.filter(pk=lease_id).first()
    if (
        lease is None
        or lease.frame_review_id != frame.pk
        or lease.holder_id != user.pk
        or lease.closed_at is not None
        or lease.expires_at <= _now()
        or frame.state != FrameReview.State.IN_REVIEW
    ):
        _deny_lease(request, lease_id, action)
    assert lease is not None
    return lease, role


def _authorize_frame(request: Request, *, frame: FrameReview, action: str) -> str:
    """Recheck server-side authorization before both first writes and keyed replays."""
    user = _actor(request)
    if not has_review_scope(user_id=user.pk, dataset_id=frame.run.dataset_id):
        raise ApiError(status.HTTP_403_FORBIDDEN, "OUT_OF_SCOPE", "Ngoài phạm vi dataset.")
    identity = _reviewer_identity(request, action=action)
    _deny_frame_ineligible(request, identity, frame, action)
    return _role(user, frame.run.dataset_id)


def _validate_rule(rule_id: object, frame: FrameReview) -> list[str]:
    if rule_id is None or rule_id == "":
        return []
    if not isinstance(rule_id, str) or len(rule_id) > 32:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "rule_id không hợp lệ.")
    version = frame.run.snapshot.guideline_version
    if not GuidelineRule.objects.filter(version__version_tag=version, rule_id=rule_id).exists():
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "BUSINESS_RULE_UNMET",
            "Rule không thuộc guideline version của snapshot.",
        )
    return [rule_id]


def _validated_action(body: dict[str, Any], issue: Issue) -> tuple[str, str, list[str]]:
    action = body.get("action")
    if action not in {
        ReviewDecision.Action.CONFIRM,
        ReviewDecision.Action.REJECT,
        ReviewDecision.Action.UNCERTAIN,
        ReviewDecision.Action.ESCALATE,
    }:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Action không hợp lệ.")
    if issue.state != Issue.State.IN_REVIEW:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "INVALID_TRANSITION",
            "Issue không ở trạng thái đang review.",
            {"from": issue.state, "event": str(action)},
        )
    reason = body.get("reason", "")
    if not isinstance(reason, str):
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "reason không hợp lệ.")
    reason = reason.strip()
    if (
        action
        in {
            ReviewDecision.Action.REJECT,
            ReviewDecision.Action.UNCERTAIN,
            ReviewDecision.Action.ESCALATE,
        }
        and not reason
    ):
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Thiếu reason.")
    if action == ReviewDecision.Action.CONFIRM:
        if body.get("family") not in Issue.Family.values:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "family không hợp lệ.")
        if body.get("severity") not in Issue.Severity.values:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "severity không hợp lệ."
            )
        if body["family"] != issue.family:
            raise ApiError(
                status.HTTP_409_CONFLICT,
                "INVALID_TRANSITION",
                "family khác Issue gốc.",
            )
    rules = _validate_rule(body.get("rule_id"), issue.frame_review)
    return str(action), reason, rules


@transaction.atomic
def write_decision(*, request: Request, issue_id: int) -> ReviewDecision:
    body = _body(request)
    lease_id = body.get("lease_id")
    if isinstance(lease_id, bool) or not isinstance(lease_id, int) or lease_id <= 0:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "lease_id không hợp lệ.")
    key = _idempotency(request)
    request_hash = _request_hash(body)
    relation = Issue.objects.filter(pk=issue_id).values("frame_review__run_id").first()
    if relation is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Issue không tồn tại.")
    user = _actor(request)
    # Same lock order as claim_next/renew: user -> run -> issue/lease.
    User.objects.select_for_update(no_key=True).get(pk=user.pk)
    QCRun.objects.select_for_update().get(pk=relation["frame_review__run_id"])
    issue = Issue.objects.select_related("frame_review__run__snapshot").get(pk=issue_id)
    frame = issue.frame_review
    _authorize_frame(request, frame=frame, action="issues.decide")
    if key is not None:
        old = ReviewDecision.objects.filter(issue=issue, actor=user, idempotency_key=key).first()
        if old is not None:
            if old.request_hash != request_hash:
                raise ApiError(
                    status.HTTP_409_CONFLICT,
                    "IDEMPOTENCY_KEY_REUSED",
                    "Idempotency-Key đã dùng với body khác.",
                )
            return old
    _, role = _owned_lease(request, frame=frame, lease_id=lease_id)
    revision = body.get("revision")
    expected_revision = frame.run.snapshot.revision_sha256
    if not isinstance(revision, str) or revision != expected_revision:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "INVALID_TRANSITION",
            "Revision không khớp snapshot đang review.",
        )
    action, reason, rules = _validated_action(body, issue)
    target: str = {
        ReviewDecision.Action.CONFIRM.value: Issue.State.CONFIRMED.value,
        ReviewDecision.Action.REJECT.value: Issue.State.REJECTED.value,
        ReviewDecision.Action.UNCERTAIN.value: Issue.State.ESCALATED.value,
        ReviewDecision.Action.ESCALATE.value: Issue.State.ESCALATED.value,
    }[action]
    before = {"state": issue.state, "family": issue.family, "severity": issue.severity}
    issue.state = target
    if action == ReviewDecision.Action.CONFIRM:
        issue.severity = body["severity"]
    issue.save(update_fields=["state", "severity"])
    override_reason = str(body.get("override_reason", "")).strip()
    audit = append_audit_event(
        actor=user,
        action=f"issue.{action}",
        object_type="issue",
        object_id=issue.pk,
        before=before,
        after={
            "state": issue.state,
            "family": issue.family,
            "severity": issue.severity,
            "rule_ids": rules,
            "override_reason": override_reason if role == Role.SUPER_ADMIN else None,
        },
        revision=expected_revision,
        reason=reason or override_reason,
    )
    return ReviewDecision.objects.create(
        issue=issue,
        actor=user,
        actor_role=role,
        action=action,
        revision=expected_revision,
        reason=reason or override_reason,
        rule_ids=rules,
        reference_version=None,
        reference_match_status=ReviewDecision.ReferenceMatch.NOT_EVALUATED,
        reference_error_ids=[],
        audit_event=audit,
        idempotency_key=key,
        request_hash=request_hash,
    )
