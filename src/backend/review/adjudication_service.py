"""T-038 escalation and adjudication domain service."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Case, FloatField, Q, Value, When
from django.utils import timezone
from rest_framework import status
from rest_framework.request import Request

from accounts.models import CvatIdentity, Role, RoleAssignment
from accounts.permissions import record_rejection_audit
from audit.services import append_audit_event
from config.exceptions import ApiError
from guideline.models import GuidelineRule
from review.models import DecisionCase, GuidelineGap, Issue, ReviewDecision, ReworkRequest
from review.rework_service import create_rework
from review.serialization import issue_response
from runs.models import QCRun


def _actor(request: Request) -> User:
    user = request.user
    if not isinstance(user, User) or user.pk is None:
        raise ApiError(status.HTTP_403_FORBIDDEN, "NOT_AUTHENTICATED", "Chưa đăng nhập.")
    return user


def _request_hash(body: dict[str, Any]) -> str:
    serialized = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _idempotency_key(request: Request) -> str | None:
    raw = request.headers.get("Idempotency-Key")
    if not raw:
        return None
    key = raw.strip()
    if len(key) > 36:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Idempotency-Key quá dài.")
    return key or None


def _validate_rule(rule_id: object, issue: Issue) -> str:
    if not isinstance(rule_id, str) or not rule_id.strip() or len(rule_id) > 32:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "rule_id không hợp lệ.")
    rule_id_clean = rule_id.strip()
    version = issue.frame_review.run.snapshot.guideline_version
    rule_exists = GuidelineRule.objects.filter(
        version__version_tag=version, rule_id=rule_id_clean
    ).exists()
    if not rule_exists:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "BUSINESS_RULE_UNMET",
            "Rule không thuộc guideline version của snapshot.",
        )
    return rule_id_clean


PUBLIC_GUIDELINE_GAP = "guideline_gap"
LEGACY_GUIDELINE_MISSING = DecisionCase.Outcome.GUIDELINE_MISSING.value
PUBLIC_OUTCOMES = (
    DecisionCase.Outcome.CONFIRM.value,
    DecisionCase.Outcome.REJECT.value,
    PUBLIC_GUIDELINE_GAP,
)
CASE_PAGE_SIZE = 50


def public_outcome(stored: str) -> str:
    """Rows are append-only; legacy ``guideline_missing`` is mapped to the public enum on read."""
    return PUBLIC_GUIDELINE_GAP if stored == LEGACY_GUIDELINE_MISSING else stored


def _case_payload(case: DecisionCase) -> dict[str, Any]:
    return {
        "id": case.pk,
        "issue_id": case.issue_id,
        "outcome": public_outcome(case.outcome),
        "actor_user_id": case.actor_id,
        "rule_id": case.rule_id,
        "correct_label": case.correct_label,
        "reason": case.reason,
        "case_version": case.case_version,
        "created_at": case.created_at.isoformat(),
    }


def list_escalations(request: Request) -> dict[str, Any]:
    """GET /api/escalations/ - List issues waiting for adjudication, oldest first."""
    user = _actor(request)
    assignments = list(RoleAssignment.objects.filter(user=user))
    has_global_sa = any(a.role == Role.SUPER_ADMIN and a.dataset_id is None for a in assignments)
    allowed_dataset_ids = {
        a.dataset_id
        for a in assignments
        if a.role in (Role.QA_LEAD, Role.SUPER_ADMIN) and a.dataset_id is not None
    }

    if not has_global_sa and not allowed_dataset_ids:
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "PERMISSION_DENIED",
            "Chỉ QA Lead hoặc Super Admin mới có quyền truy cập escalations.",
        )

    qs = Issue.objects.filter(state=Issue.State.ESCALATED)

    run_param = request.query_params.get("run")
    if run_param is not None:
        if not run_param.isdigit() or int(run_param) <= 0:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "run không hợp lệ.")
        run_id = int(run_param)
        run_obj = QCRun.objects.filter(pk=run_id).first()
        if run_obj is None:
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Run không tồn tại.")
        if not has_global_sa and run_obj.dataset_id not in allowed_dataset_ids:
            raise ApiError(status.HTTP_403_FORBIDDEN, "OUT_OF_SCOPE", "Ngoài phạm vi dataset.")
        qs = qs.filter(frame_review__run_id=run_id)
    else:
        if not has_global_sa:
            qs = qs.filter(frame_review__run__dataset_id__in=allowed_dataset_ids)

    # Order oldest first per contract
    qs = qs.order_by("created_at", "pk")

    cursor_text = request.query_params.get("cursor")
    if cursor_text:
        if not cursor_text.isdigit() or int(cursor_text) < 0:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Cursor không hợp lệ.")
        after_id = int(cursor_text)
        qs = qs.filter(pk__gt=after_id)

    limit = 50
    items = list(
        qs.select_related(
            "candidate",
            "frame_review__snapshot_frame__snapshot_job",
        ).prefetch_related("review_decisions")[: limit + 1]
    )

    has_next = len(items) > limit
    page = items[:limit]
    next_url: str | None = None
    if has_next and page:
        next_cursor = page[-1].pk
        params = f"cursor={next_cursor}"
        if run_param:
            params += f"&run={run_param}"
        next_url = request.build_absolute_uri(f"/api/escalations/?{params}")

    return {
        "next": next_url,
        "previous": None,
        "results": [issue_response(issue) for issue in page],
    }


@transaction.atomic
def adjudicate_issue(*, request: Request, issue_id: int) -> dict[str, Any]:
    """POST /api/issues/{id}/adjudications/ - Adjudicate an escalated issue atomically."""
    user = _actor(request)
    body = request.data
    if not isinstance(body, dict):
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Body không hợp lệ.")

    key = _idempotency_key(request)
    request_hash = _request_hash(body)

    # Serialization locks: User -> Run -> Issue
    User.objects.select_for_update(no_key=True).get(pk=user.pk)

    relation = (
        Issue.objects.filter(pk=issue_id)
        .values("frame_review__run_id", "frame_review__run__dataset_id")
        .first()
    )
    if relation is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Issue không tồn tại.")

    run_id = relation["frame_review__run_id"]
    dataset_id = relation["frame_review__run__dataset_id"]
    QCRun.objects.select_for_update().get(pk=run_id)

    issue = (
        Issue.objects.select_for_update()
        .select_related("frame_review__run__snapshot")
        .get(pk=issue_id)
    )

    # 1. Scope & Role validation
    assignments = list(RoleAssignment.objects.filter(user=user))
    is_sa = any(
        a.role == Role.SUPER_ADMIN and (a.dataset_id is None or a.dataset_id == dataset_id)
        for a in assignments
    )
    is_qa = any(a.role == Role.QA_LEAD and a.dataset_id == dataset_id for a in assignments)
    if not is_sa and not is_qa:
        record_rejection_audit(
            request=request,
            code="OUT_OF_SCOPE",
            object_type="issue",
            object_id=issue.pk,
            action="issues.adjudicate",
            message="User does not have QA Lead or Super Admin role in dataset scope.",
        )
        raise ApiError(status.HTTP_403_FORBIDDEN, "OUT_OF_SCOPE", "Ngoài phạm vi dataset.")

    actor_role = Role.SUPER_ADMIN if is_sa else Role.QA_LEAD

    # 2. Adjudicator identity verification check (fail-closed)
    adjudicator_identity = CvatIdentity.objects.select_related("employee").filter(user=user).first()
    if not is_sa and (
        adjudicator_identity is None
        or adjudicator_identity.employee is None
        or not adjudicator_identity.employee.is_verified
    ):
        record_rejection_audit(
            request=request,
            code="IDENTITY_MAPPING_MISSING",
            object_type="reviewer",
            object_id=user.pk,
            action="issues.adjudicate",
            message="Adjudicator identity is not verified.",
        )
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "IDENTITY_MAPPING_MISSING",
            "Thiếu định danh đã xác minh.",
        )

    # 3. Separation of duties: adjudicator cannot be escalator (account & natural person)
    escalator_decision = (
        issue.review_decisions.filter(
            action__in=[ReviewDecision.Action.ESCALATE, ReviewDecision.Action.UNCERTAIN]
        )
        .order_by("recorded_at", "pk")
        .last()
    )

    if escalator_decision is not None and not is_sa:
        escalator_user = escalator_decision.actor
        # 3a. Same account check
        if user.pk == escalator_user.pk:
            record_rejection_audit(
                request=request,
                code="SAME_REQUESTER_APPROVER",
                object_type="issue",
                object_id=issue.pk,
                action="issues.adjudicate",
                message="Adjudicator cannot be the same user account that escalated.",
            )
            raise ApiError(
                status.HTTP_403_FORBIDDEN,
                "SAME_REQUESTER_APPROVER",
                "Người phân xử không được là người đã chuyển cấp.",
            )

        # 3b. Same natural person / EmployeeIdentity check
        escalator_identity = (
            CvatIdentity.objects.select_related("employee").filter(user=escalator_user).first()
        )
        if escalator_identity is not None:
            is_same_emp = (
                escalator_identity.employee_id is not None
                and adjudicator_identity.employee_id == escalator_identity.employee_id
            )
            is_same_cvat = adjudicator_identity.cvat_user_id == escalator_identity.cvat_user_id
            if is_same_emp or is_same_cvat:
                record_rejection_audit(
                    request=request,
                    code="SAME_REQUESTER_APPROVER",
                    object_type="issue",
                    object_id=issue.pk,
                    action="issues.adjudicate",
                    message="Adjudicator shares employee identity with the escalator.",
                )
                raise ApiError(
                    status.HTTP_403_FORBIDDEN,
                    "SAME_REQUESTER_APPROVER",
                    "Người phân xử không được cùng thể nhân với người đã chuyển cấp.",
                )

    # 4. Idempotency replay check BEFORE state transition check
    if key is not None:
        old_case = DecisionCase.objects.filter(issue=issue, actor=user, idempotency_key=key).first()
        if old_case is not None:
            if old_case.request_hash != request_hash:
                raise ApiError(
                    status.HTTP_409_CONFLICT,
                    "IDEMPOTENCY_KEY_REUSED",
                    "Idempotency-Key đã dùng với body khác.",
                )
            rework_id = (
                ReworkRequest.objects.filter(
                    issue=issue, created_by=user, create_idempotency_key=key
                )
                .values_list("pk", flat=True)
                .first()
            )
            return {**_case_payload(old_case), "rework_id": rework_id}

    # 5. Transition state check: must be ESCALATED
    if issue.state != Issue.State.ESCALATED:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "INVALID_TRANSITION",
            "Issue không ở trạng thái escalated.",
            {"from": issue.state, "event": "issue.adjudicate"},
        )

    # 6. Body fields validation
    outcome = body.get("outcome")
    if outcome not in PUBLIC_OUTCOMES:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "Outcome không hợp lệ; chỉ chấp nhận confirm, reject, guideline_gap.",
        )

    after_adjudication = body.get("after_adjudication", "none")
    if after_adjudication not in {"none", "request_rework"}:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "after_adjudication không hợp lệ.",
        )
    if after_adjudication == "request_rework" and outcome != DecisionCase.Outcome.CONFIRM:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "BUSINESS_RULE_UNMET",
            "request_rework chỉ hợp lệ khi outcome là confirm.",
        )

    rule_id = _validate_rule(body.get("rule_id"), issue)

    reason = body.get("reason", "")
    if not isinstance(reason, str) or not reason.strip():
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Thiếu reason.")
    reason = reason.strip()

    correct_label = body.get("correct_label")
    if correct_label is not None:
        if not isinstance(correct_label, str) or len(correct_label) > 64:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "correct_label không hợp lệ."
            )
        correct_label = correct_label.strip() or None

    override_reason = str(body.get("override_reason", "")).strip()

    # 7. Compute next case_version (v1, v2...)
    version_count = DecisionCase.objects.filter(issue=issue).count()
    case_version = f"v{version_count + 1}"

    # 8. State transition
    before_state = {
        "state": issue.state,
        "family": issue.family,
        "severity": issue.severity,
    }

    if outcome == DecisionCase.Outcome.CONFIRM:
        issue.state = Issue.State.CONFIRMED
    elif outcome == DecisionCase.Outcome.REJECT:
        issue.state = Issue.State.REJECTED
    elif outcome == PUBLIC_GUIDELINE_GAP:
        # Keep escalated waiting for new guideline version (FR-ESC-05 deferred)
        issue.state = Issue.State.ESCALATED

    issue.save(update_fields=["state"])

    # 9. Append AuditEvent (transaction atomic rolls back everything if audit fails)
    expected_revision = issue.frame_review.run.snapshot.revision_sha256
    after_state = {
        "state": issue.state,
        "outcome": str(outcome),
        "rule_id": rule_id,
        "correct_label": correct_label,
        "case_version": case_version,
        "override_reason": override_reason if actor_role == Role.SUPER_ADMIN else None,
    }

    append_audit_event(
        actor=user,
        action=f"issue.adjudicate.{outcome}",
        object_type="issue",
        object_id=issue.pk,
        before=before_state,
        after=after_state,
        revision=expected_revision,
        reason=reason or override_reason,
    )

    # 10. Persist versioned DecisionCase
    case = DecisionCase.objects.create(
        issue=issue,
        review_decision=escalator_decision,
        case_version=case_version,
        outcome=str(outcome),
        rule_id=rule_id,
        correct_label=correct_label,
        reason=reason,
        override_reason=override_reason,
        actor=user,
        idempotency_key=key,
        request_hash=request_hash,
    )

    if outcome == PUBLIC_GUIDELINE_GAP:
        GuidelineGap.objects.get_or_create(
            issue=issue,
            rule_id=rule_id,
            status=GuidelineGap.Status.OPEN,
            defaults={
                "description": reason,
                "guideline_version": issue.frame_review.run.snapshot.guideline_version,
                "created_by": user,
            },
        )

    rework_id = None
    if after_adjudication == "request_rework":
        job = issue.frame_review.snapshot_frame.snapshot_job
        if job.assignee_user_id is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "BUSINESS_RULE_UNMET",
                "Snapshot job chưa ánh xạ annotator để tạo rework.",
            )
        if issue.severity not in Issue.Severity.values:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "BUSINESS_RULE_UNMET",
                "Issue chưa có severity để tạo rework.",
            )
        due_hours = int(settings.REWORK_DEFAULT_DUE_HOURS)
        deep_link = (
            f"{settings.CVAT_BASE_URL.rstrip('/')}"
            f"/tasks/{job.cvat_task_id}/jobs/{job.cvat_job_id}"
            f"?frame={issue.frame_review.snapshot_frame.frame_index}"
        )
        rework = create_rework(
            request=request,
            body_override={
                "issue_id": issue.pk,
                "instruction": reason,
                "annotator_user_id": job.assignee_user_id,
                "due_at": (timezone.now() + timedelta(hours=due_hours)).isoformat(),
                "severity": issue.severity,
                "cvat_deep_link": deep_link,
            },
        )
        rework_id = rework.pk

    return {**_case_payload(case), "rework_id": rework_id}


def _case_scope(user: User) -> tuple[bool, set[int]]:
    assignments = list(RoleAssignment.objects.filter(user=user))
    has_global = any(
        a.role in (Role.SUPER_ADMIN, Role.QC_ADMIN) and a.dataset_id is None for a in assignments
    )
    allowed = {
        a.dataset_id
        for a in assignments
        if a.role in (Role.REVIEWER, Role.QA_LEAD, Role.SUPER_ADMIN) and a.dataset_id is not None
    }
    return has_global, allowed


def get_decision_case(*, request: Request, case_id: int) -> dict[str, Any]:
    """GET /api/decision-cases/{id}/ - one version plus the append-only history of its issue."""
    user = _actor(request)
    case = (
        DecisionCase.objects.select_related("issue__frame_review__run").filter(pk=case_id).first()
    )
    if case is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "DecisionCase không tồn tại.")

    dataset_id = case.issue.frame_review.run.dataset_id
    has_global, allowed = _case_scope(user)
    if not has_global and dataset_id not in allowed:
        raise ApiError(status.HTTP_403_FORBIDDEN, "OUT_OF_SCOPE", "Ngoài phạm vi dataset.")

    history = DecisionCase.objects.filter(issue_id=case.issue_id).order_by("pk")
    return {
        **_case_payload(case),
        "history": [
            {
                "id": row.pk,
                "case_version": row.case_version,
                "outcome": public_outcome(row.outcome),
                "actor_user_id": row.actor_id,
                "created_at": row.created_at.isoformat(),
            }
            for row in history
        ],
    }


def list_decision_cases(request: Request) -> dict[str, Any]:
    """GET /api/decision-cases/ - filtered, cursor-paginated, scope-limited (UC-12)."""
    user = _actor(request)
    has_global, allowed = _case_scope(user)
    if not has_global and not allowed:
        raise ApiError(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Không có quyền đọc Decision Case.")

    qs = DecisionCase.objects.select_related("issue__frame_review__run")
    if not has_global:
        qs = qs.filter(issue__frame_review__run__dataset_id__in=allowed)

    params: dict[str, str] = {}

    def _positive(name: str) -> int | None:
        raw = request.query_params.get(name)
        if raw is None:
            return None
        if not raw.isdigit() or int(raw) <= 0:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", f"{name} không hợp lệ.")
        params[name] = raw
        return int(raw)

    rule_param = request.query_params.get("rule_id")
    if rule_param and rule_param.strip():
        qs = qs.filter(rule_id=rule_param.strip())
        params["rule_id"] = rule_param.strip()

    issue_id = _positive("issue")
    if issue_id is not None:
        qs = qs.filter(issue_id=issue_id)

    version_param = request.query_params.get("version")
    if version_param and version_param.strip():
        qs = qs.filter(case_version=version_param.strip())
        params["version"] = version_param.strip()

    outcome_param = request.query_params.get("outcome")
    if outcome_param is not None:
        if outcome_param not in PUBLIC_OUTCOMES:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "outcome không hợp lệ.")
        stored = (
            [PUBLIC_GUIDELINE_GAP, LEGACY_GUIDELINE_MISSING]
            if outcome_param == PUBLIC_GUIDELINE_GAP
            else [outcome_param]
        )
        qs = qs.filter(outcome__in=stored)
        params["outcome"] = outcome_param

    after = request.query_params.get("cursor")
    if after:
        if not after.isdigit():
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Cursor không hợp lệ.")
        qs = qs.filter(pk__gt=int(after))

    rows = list(qs.order_by("pk")[: CASE_PAGE_SIZE + 1])
    page = rows[:CASE_PAGE_SIZE]
    next_url: str | None = None
    if len(rows) > CASE_PAGE_SIZE:
        query = "&".join(f"{k}={v}" for k, v in {**params, "cursor": page[-1].pk}.items())
        next_url = request.build_absolute_uri(f"/api/decision-cases/?{query}")
    return {"next": next_url, "previous": None, "results": [_case_payload(c) for c in page]}


def similar_case_queryset(*, issue_id: int) -> tuple[Issue, Any]:
    """Rank prior adjudications by exact rule and family overlap."""

    issue = Issue.objects.select_related("frame_review__run").filter(pk=issue_id).first()
    if issue is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Issue không tồn tại.")
    rule_ids = [str(item) for item in issue.rule_ids if str(item).strip()]
    same_rule = Q(rule_id__in=rule_ids) if rule_ids else Q(pk__in=[])
    same_family = Q(issue__family=issue.family)
    queryset = (
        DecisionCase.objects.select_related("issue__frame_review__run")
        .filter(issue__frame_review__run__dataset_id=issue.frame_review.run.dataset_id)
        .exclude(issue_id=issue.pk)
        .filter(same_rule | same_family)
        .annotate(
            similarity=Case(
                When(same_rule & same_family, then=Value(1.0)),
                When(same_rule, then=Value(0.75)),
                default=Value(0.5),
                output_field=FloatField(),
            )
        )
        .order_by("-similarity", "-pk")
    )
    return issue, queryset
