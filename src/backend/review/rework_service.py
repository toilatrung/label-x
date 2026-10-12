"""T-040 rework, re-check and verification workflow."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.contrib.auth.models import User
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.request import Request

from accounts.models import CvatIdentity, Role, RoleAssignment
from accounts.permissions import record_rejection_audit
from audit.services import append_audit_event
from config.exceptions import ApiError
from review.models import (
    FrameReview,
    Issue,
    ReviewDecision,
    ReworkRecheck,
    ReworkRequest,
    ReworkVerification,
)
from review.services import _actor, _reviewer_identity
from runs.models import QCRun
from runs.services import create_qc_run
from snapshots.models import Snapshot
from snapshots.orchestration import SnapshotScope, create_snapshot_from_cvat


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
        raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "JSON không hợp lệ."
        ) from exc
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _text(value: object, field: str, *, maximum: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", f"{field} không hợp lệ.")
    clean = value.strip()
    if maximum is not None and len(clean) > maximum:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", f"{field} quá dài.")
    return clean


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", f"{field} không hợp lệ.")
    return value


def _due_at(value: object) -> datetime:
    clean = _text(value, "due_at", maximum=64)
    parsed = parse_datetime(clean)
    if parsed is None or timezone.is_naive(parsed):
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "due_at phải là date-time có timezone.",
        )
    return parsed


def _has_role(user: User, dataset_id: int, roles: tuple[Role, ...]) -> bool:
    return (
        RoleAssignment.objects.filter(user=user)
        .filter(
            Q(role__in=roles, dataset_id=dataset_id)
            | Q(role=Role.SUPER_ADMIN, dataset_id__isnull=True)
        )
        .exists()
    )


def _role(user: User, dataset_id: int, roles: tuple[Role, ...]) -> str:
    assignments = set(
        RoleAssignment.objects.filter(user=user)
        .filter(Q(dataset_id=dataset_id) | Q(role=Role.SUPER_ADMIN, dataset_id__isnull=True))
        .values_list("role", flat=True)
    )
    for role in (Role.SUPER_ADMIN, *roles):
        if role in assignments:
            return str(role)
    raise ApiError(status.HTTP_403_FORBIDDEN, "OUT_OF_SCOPE", "Ngoài phạm vi dataset.")


def _verified_identity(user: User, *, action: str, request: Request) -> CvatIdentity:
    identity = CvatIdentity.objects.select_related("employee").filter(user=user).first()
    if identity is None or identity.employee is None or not identity.employee.is_verified:
        record_rejection_audit(
            request=request,
            code="IDENTITY_MAPPING_MISSING",
            object_type="rework",
            object_id=user.pk,
            action=action,
            message="Identity is not verified.",
        )
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "IDENTITY_MAPPING_MISSING",
            "Thiếu định danh đã xác minh.",
        )
    return identity


def _validate_deep_link(value: object, issue: Issue) -> str:
    link = _text(value, "cvat_deep_link", maximum=1024)
    try:
        URLValidator(schemes=["http", "https"])(link)
    except Exception as exc:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "cvat_deep_link không hợp lệ."
        ) from exc
    parsed = urlparse(link)
    configured = urlparse(settings.CVAT_BASE_URL)
    job = issue.frame_review.snapshot_frame.snapshot_job
    expected_path = f"/tasks/{job.cvat_task_id}/jobs/{job.cvat_job_id}"
    frame = parse_qs(parsed.query).get("frame", [None])[0]
    if (
        parsed.scheme != configured.scheme
        or parsed.netloc != configured.netloc
        or parsed.path.rstrip("/") != expected_path
        or frame != str(issue.frame_review.snapshot_frame.frame_index)
    ):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "INVALID_TRANSITION",
            "CVAT deep link không trỏ đúng frame của issue.",
        )
    return link


def rework_response(rework: ReworkRequest) -> dict[str, object]:
    return {
        "id": rework.pk,
        "issue_id": rework.issue_id,
        "annotator_user_id": rework.annotator_id,
        "status": rework.status,
        "original_revision": rework.original_revision,
        "submitted_revision": rework.submitted_revision,
        "recheck_run_id": rework.recheck_run_id,
        "due_at": rework.due_at.isoformat(),
        "cvat_deep_link": rework.cvat_deep_link,
    }


@transaction.atomic
def create_rework(*, request: Request) -> ReworkRequest:
    body = _body(request)
    user = _actor(request)
    issue_id = _positive_int(body.get("issue_id"), "issue_id")
    key = _idempotency(request)
    request_hash = _request_hash(body)

    User.objects.select_for_update().get(pk=user.pk)
    relation = Issue.objects.filter(pk=issue_id).values("frame_review__run_id").first()
    if relation is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Issue không tồn tại.")
    QCRun.objects.select_for_update().get(pk=relation["frame_review__run_id"])
    issue = (
        Issue.objects.select_for_update()
        .select_related("frame_review__run__snapshot", "frame_review__snapshot_frame__snapshot_job")
        .get(pk=issue_id)
    )
    dataset_id = issue.frame_review.run.dataset_id
    actor_role = _role(user, dataset_id, (Role.REVIEWER, Role.QA_LEAD))
    _reviewer_identity(request, action="rework.create")

    if key is not None:
        replay = ReworkRequest.objects.filter(created_by=user, create_idempotency_key=key).first()
        if replay is not None:
            if replay.create_request_hash != request_hash:
                raise ApiError(
                    status.HTTP_409_CONFLICT,
                    "IDEMPOTENCY_KEY_REUSED",
                    "Idempotency-Key đã dùng với body khác.",
                )
            return replay
    if issue.state != Issue.State.CONFIRMED:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "INVALID_TRANSITION",
            "Chỉ issue confirmed mới được yêu cầu sửa.",
            {"from": issue.state, "event": "request_fix"},
        )
    if ReworkRequest.objects.filter(
        issue=issue,
        status__in=[ReworkRequest.Status.FIX_PENDING, ReworkRequest.Status.RECHECK_PENDING],
    ).exists():
        raise ApiError(
            status.HTTP_409_CONFLICT, "INVALID_TRANSITION", "Issue đã có rework đang mở."
        )

    annotator_id = _positive_int(body.get("annotator_user_id"), "annotator_user_id")
    annotator = User.objects.select_for_update().filter(pk=annotator_id).first()
    if annotator is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Annotator không tồn tại.")
    if not _has_role(annotator, dataset_id, (Role.ANNOTATOR,)):
        raise ApiError(
            status.HTTP_403_FORBIDDEN, "OUT_OF_SCOPE", "Annotator ngoài phạm vi dataset."
        )
    _verified_identity(annotator, action="rework.create", request=request)

    instruction = _text(body.get("instruction"), "instruction")
    severity = body.get("severity")
    if severity not in Issue.Severity.values:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "severity không hợp lệ.")
    deep_link = _validate_deep_link(body.get("cvat_deep_link"), issue)
    due_at = _due_at(body.get("due_at"))
    revision = issue.frame_review.run.snapshot.revision_sha256
    before = {"issue_state": issue.state}
    issue.state = Issue.State.FIX_PENDING
    issue.save(update_fields=["state"])
    audit = append_audit_event(
        actor=user,
        action="issue.request_fix",
        object_type="issue",
        object_id=issue.pk,
        before=before,
        after={
            "issue_state": issue.state,
            "annotator_user_id": annotator.pk,
            "due_at": due_at.isoformat(),
        },
        revision=revision,
        reason=instruction,
    )
    ReviewDecision.objects.create(
        issue=issue,
        actor=user,
        actor_role=actor_role,
        action=ReviewDecision.Action.REQUEST_FIX,
        revision=revision,
        reason=instruction,
        rule_ids=issue.rule_ids,
        reference_version=None,
        reference_match_status=ReviewDecision.ReferenceMatch.NOT_EVALUATED,
        reference_error_ids=[],
        audit_event=audit,
        idempotency_key=key,
        request_hash=request_hash,
    )
    try:
        return ReworkRequest.objects.create(
            issue=issue,
            annotator=annotator,
            created_by=user,
            instruction=instruction,
            severity=str(severity),
            cvat_deep_link=deep_link,
            original_revision=revision,
            due_at=due_at,
            create_idempotency_key=key,
            create_request_hash=request_hash,
        )
    except IntegrityError as exc:
        raise ApiError(
            status.HTTP_409_CONFLICT, "INVALID_TRANSITION", "Issue đã có rework đang mở."
        ) from exc


def _build_recheck_artifacts(
    *, rework: ReworkRequest, actor: User, key: str, claimed_revision: str
) -> tuple[Snapshot, QCRun]:
    """Read CVAT, lock one-job snapshot and start a re-check through the M-02 orchestrator."""

    frame = rework.issue.frame_review
    job = frame.snapshot_frame.snapshot_job
    snapshot = create_snapshot_from_cvat(
        dataset_id=frame.run.dataset_id,
        scope=SnapshotScope(cvat_job_ids=(job.cvat_job_id,)),
        note=f"T-040 rework {rework.pk} submission {claimed_revision}",
        created_by=actor,
        idempotency_key=f"rework-{rework.pk}-snapshot-{key}",
    )
    if snapshot.status != Snapshot.Status.LOCKED:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "INVALID_TRANSITION",
            "Snapshot re-check không khóa được do drift nguồn CVAT.",
        )
    if snapshot.revision_sha256 in _known_revisions(rework):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "REVISION_UNCHANGED",
            "Revision CVAT chưa thay đổi.",
        )
    if snapshot.revision_sha256 != claimed_revision:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "INVALID_TRANSITION",
            "Revision gửi lên không khớp snapshot mới đọc từ CVAT.",
        )
    run, _ = create_qc_run(
        snapshot_id=snapshot.pk,
        config_version_id=frame.run.config_version_id,
        seed=frame.run.seed,
        created_by=actor,
        idempotency_key=f"rework-{rework.pk}-run-{key}",
        origin_run_id=frame.run_id,
    )
    return snapshot, run


def _snapshot_reused_error(snapshot: Snapshot, rework: ReworkRequest) -> ApiError:
    """Same snapshot = same revision content already re-checked: a business conflict, not a 500."""

    return ApiError(
        status.HTTP_409_CONFLICT,
        "REVISION_UNCHANGED",
        "Snapshot re-check đã được dùng cho một vòng trước của rework này.",
        {"rework_id": rework.pk, "snapshot_id": snapshot.pk},
    )


def _known_revisions(rework: ReworkRequest) -> set[str]:
    """Revisions already seen by this rework: the reviewed one and every submitted round."""

    return {rework.original_revision, *rework.rechecks.values_list("revision", flat=True)}


def _existing_submission(
    *,
    rework: ReworkRequest,
    claimed_revision: str,
    key: str | None,
    request_hash: str,
) -> ReworkRequest | None:
    """Return the rework for a retried submission, None for a genuinely new round."""

    rechecks = list(rework.rechecks.all())
    if key is not None:
        keyed = next((item for item in rechecks if item.idempotency_key == key), None)
        if keyed is not None:
            if keyed.request_hash != request_hash or keyed.revision != claimed_revision:
                raise ApiError(
                    status.HTTP_409_CONFLICT,
                    "IDEMPOTENCY_KEY_REUSED",
                    "Idempotency-Key đã dùng với body khác.",
                )
            return rework
    seen = next((item for item in rechecks if item.revision == claimed_revision), None)
    if seen is not None:
        latest = rechecks[-1]
        if (
            rework.status == ReworkRequest.Status.RECHECK_PENDING
            and seen.pk == latest.pk
            and seen.idempotency_key is None
            and key is None
        ):
            return rework
        if rework.status == ReworkRequest.Status.RECHECK_PENDING:
            raise ApiError(status.HTTP_409_CONFLICT, "INVALID_TRANSITION", "Rework đã được submit.")
        raise ApiError(
            status.HTTP_409_CONFLICT, "REVISION_UNCHANGED", "Revision CVAT chưa thay đổi."
        )
    if rework.status == ReworkRequest.Status.RECHECK_PENDING:
        raise ApiError(status.HTTP_409_CONFLICT, "INVALID_TRANSITION", "Rework đã được submit.")
    return None


def submit_rework(*, request: Request, rework_id: int) -> ReworkRequest:
    body = _body(request)
    user = _actor(request)
    key = _idempotency(request)
    request_hash = _request_hash(body)
    claimed_revision = _text(body.get("cvat_revision"), "cvat_revision", maximum=64)
    lookup = (
        ReworkRequest.objects.select_related(
            "issue__frame_review__run", "issue__frame_review__snapshot_frame__snapshot_job"
        )
        .filter(pk=rework_id)
        .first()
    )
    if lookup is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Rework không tồn tại.")
    dataset_id = lookup.issue.frame_review.run.dataset_id
    is_super = _has_role(user, dataset_id, (Role.SUPER_ADMIN,))
    if lookup.annotator_id != user.pk and not is_super:
        raise ApiError(
            status.HTTP_403_FORBIDDEN, "OUT_OF_SCOPE", "Không phải annotator của rework."
        )
    _verified_identity(user, action="rework.submitted", request=request)
    if claimed_revision == lookup.original_revision:
        raise ApiError(
            status.HTTP_409_CONFLICT, "REVISION_UNCHANGED", "Revision CVAT chưa thay đổi."
        )
    replay = _existing_submission(
        rework=lookup, claimed_revision=claimed_revision, key=key, request_hash=request_hash
    )
    if replay is not None:
        return replay
    if lookup.status != ReworkRequest.Status.FIX_PENDING:
        raise ApiError(status.HTTP_409_CONFLICT, "INVALID_TRANSITION", "Rework không chờ sửa.")
    effective_key = key or str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"labelx:rework:{rework_id}:{claimed_revision}")
    )
    snapshot, run = _build_recheck_artifacts(
        rework=lookup, actor=user, key=effective_key, claimed_revision=claimed_revision
    )

    with transaction.atomic():
        User.objects.select_for_update().get(pk=user.pk)
        QCRun.objects.select_for_update().get(pk=lookup.issue.frame_review.run_id)
        rework = ReworkRequest.objects.select_for_update().select_related("issue").get(pk=rework_id)
        replay = _existing_submission(
            rework=rework, claimed_revision=claimed_revision, key=key, request_hash=request_hash
        )
        if replay is not None:
            return replay
        if rework.status != ReworkRequest.Status.FIX_PENDING:
            raise ApiError(status.HTTP_409_CONFLICT, "INVALID_TRANSITION", "Rework không chờ sửa.")
        if rework.rechecks.filter(snapshot=snapshot).exists():
            raise _snapshot_reused_error(snapshot, rework)
        before = {"status": rework.status, "issue_state": rework.issue.state}
        round_number = rework.rechecks.count() + 1
        rework.status = ReworkRequest.Status.RECHECK_PENDING
        rework.submitted_revision = claimed_revision
        rework.recheck_snapshot = snapshot
        rework.recheck_run = run
        rework.submission_idempotency_key = key
        rework.submission_request_hash = request_hash
        rework.submitted_at = timezone.now()
        rework.save(
            update_fields=[
                "status",
                "submitted_revision",
                "recheck_snapshot",
                "recheck_run",
                "submission_idempotency_key",
                "submission_request_hash",
                "submitted_at",
                "updated_at",
            ]
        )
        issue = Issue.objects.select_for_update().get(pk=rework.issue_id)
        issue.state = Issue.State.RECHECK_PENDING
        issue.save(update_fields=["state"])
        try:
            with transaction.atomic():
                ReworkRecheck.objects.create(
                    rework=rework,
                    round=round_number,
                    snapshot=snapshot,
                    run=run,
                    revision=claimed_revision,
                    idempotency_key=key,
                    request_hash=request_hash,
                )
        except IntegrityError as exc:
            if rework.rechecks.filter(snapshot=snapshot).exists():
                raise _snapshot_reused_error(snapshot, rework) from exc
            raise
        append_audit_event(
            actor=user,
            action="rework.submitted",
            object_type="rework",
            object_id=rework.pk,
            before=before,
            after={
                "status": rework.status,
                "issue_state": issue.state,
                "snapshot_id": snapshot.pk,
                "recheck_run_id": run.pk,
                "round": round_number,
            },
            revision=claimed_revision,
        )
        return rework


@transaction.atomic
def verify_rework(*, request: Request, rework_id: int) -> ReworkRequest:
    body = _body(request)
    user = _actor(request)
    key = _idempotency(request)
    request_hash = _request_hash(body)
    passed = body.get("passed")
    if not isinstance(passed, bool):
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "passed không hợp lệ.")
    revision = _text(body.get("revision"), "revision", maximum=64)
    reason_raw = body.get("reason", "")
    if not isinstance(reason_raw, str):
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "reason không hợp lệ.")
    reason = reason_raw.strip()
    if not passed and not reason:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Verify fail cần reason.")

    relation = (
        ReworkRequest.objects.filter(pk=rework_id).values("issue__frame_review__run_id").first()
    )
    if relation is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Rework không tồn tại.")
    User.objects.select_for_update().get(pk=user.pk)
    QCRun.objects.select_for_update().get(pk=relation["issue__frame_review__run_id"])
    rework = (
        ReworkRequest.objects.select_for_update(of=("self",))
        .select_related("issue__frame_review__run", "recheck_run", "recheck_snapshot")
        .get(pk=rework_id)
    )
    dataset_id = rework.issue.frame_review.run.dataset_id
    actor_role = _role(user, dataset_id, (Role.REVIEWER,))
    override_reason = str(body.get("override_reason", "")).strip()
    if actor_role == Role.SUPER_ADMIN and not override_reason:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "Super Admin cần override_reason.",
        )
    verifier_identity = _reviewer_identity(request, action="rework.verify")
    annotator_identity = _verified_identity(
        rework.annotator, action="rework.verify", request=request
    )
    if (
        user.pk == rework.annotator_id
        or verifier_identity.employee_id == annotator_identity.employee_id
    ):
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "SAME_REQUESTER_APPROVER",
            "Người verify phải khác annotator đã sửa.",
        )
    if key is not None:
        replay = ReworkVerification.objects.filter(
            rework=rework, verifier=user, idempotency_key=key
        ).first()
        if replay is not None:
            if replay.request_hash != request_hash:
                raise ApiError(
                    status.HTTP_409_CONFLICT,
                    "IDEMPOTENCY_KEY_REUSED",
                    "Idempotency-Key đã dùng với body khác.",
                )
            return rework
    if rework.status != ReworkRequest.Status.RECHECK_PENDING:
        raise ApiError(status.HTTP_409_CONFLICT, "INVALID_TRANSITION", "Rework chưa chờ verify.")
    if rework.recheck_run is None or rework.recheck_snapshot is None:
        raise ApiError(status.HTTP_409_CONFLICT, "INVALID_TRANSITION", "Thiếu lineage re-check.")
    if rework.recheck_run.status != QCRun.Status.COMPLETED:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "INVALID_TRANSITION",
            "Chỉ verify sau khi re-check hoàn tất.",
        )
    if revision != rework.submitted_revision or revision != rework.recheck_snapshot.revision_sha256:
        raise ApiError(
            status.HTTP_409_CONFLICT, "INVALID_TRANSITION", "Revision verify không khớp."
        )

    issue = Issue.objects.select_for_update().get(pk=rework.issue_id)
    before = {"status": rework.status, "issue_state": issue.state}
    outcome = ReworkVerification.Outcome.PASS if passed else ReworkVerification.Outcome.FAIL
    if passed:
        rework.status = ReworkRequest.Status.RESOLVED
        rework.resolved_at = timezone.now()
        issue.state = Issue.State.RESOLVED
    else:
        rework.status = ReworkRequest.Status.REOPENED
        issue.state = Issue.State.REOPENED
    rework.save(update_fields=["status", "resolved_at", "updated_at"])
    issue.save(update_fields=["state"])
    audit = append_audit_event(
        actor=user,
        action=f"rework.verify_{outcome}",
        object_type="rework",
        object_id=rework.pk,
        before=before,
        after={"status": rework.status, "issue_state": issue.state, "actor_role": actor_role},
        revision=revision,
        reason=reason or override_reason,
    )
    ReworkVerification.objects.create(
        rework=rework,
        verifier=user,
        recheck_run=rework.recheck_run,
        outcome=outcome,
        revision=revision,
        reason=reason,
        audit_event=audit,
        idempotency_key=key,
        request_hash=request_hash,
    )
    if not passed:
        # issue.reopen_fix: the failed round stays in history, the annotator may submit again.
        reopened = {"status": rework.status, "issue_state": issue.state}
        rework.status = ReworkRequest.Status.FIX_PENDING
        issue.state = Issue.State.FIX_PENDING
        rework.save(update_fields=["status", "updated_at"])
        issue.save(update_fields=["state"])
        append_audit_event(
            actor=user,
            action="issue.reopen_fix",
            object_type="issue",
            object_id=issue.pk,
            before=reopened,
            after={"status": rework.status, "issue_state": issue.state},
            revision=revision,
            reason=reason,
        )
    if passed:
        from review.tasks import enqueue_final_run

        transaction.on_commit(lambda: enqueue_final_run(rework.issue.frame_review.run_id, user.pk))
    frame = FrameReview.objects.select_for_update().get(pk=issue.frame_review_id)
    # Completion belongs to the final-scope path (finalization_service), never to a single verify.
    frame.state = FrameReview.State.AWAITING_FOLLOWUP
    frame.save(update_fields=["state"])
    return rework
