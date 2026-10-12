"""Manual issue creation and frame completion under the queue's run lock."""

from __future__ import annotations

import math
import uuid

from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import status
from rest_framework.request import Request

from accounts.permissions import record_rejection_audit
from audit.models import AuditEvent
from audit.services import append_audit_event
from config.exceptions import ApiError
from review import decision_source
from review.decision_service import (
    _authorize_frame,
    _body,
    _idempotency,
    _owned_lease,
    _request_hash,
)
from review.models import FrameReview, Issue, Lease
from review.services import (
    _actor,
    _deny_frame_ineligible,
    _now,
    _reviewer_identity,
    has_review_scope,
)
from runs.models import QCRun


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", f"{name} không hợp lệ.")
    return value


def _manual_anchor(raw: object, frame: FrameReview) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Thiếu anchor.")
    kind = raw.get("kind")
    if kind not in ("manual_object", "manual_region"):
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Anchor không thủ công.")
    if raw.get("policy_version") not in (None, "anchor-v1"):
        raise ApiError(
            status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "policy_version không hợp lệ."
        )
    if kind == "manual_object":
        objects = raw.get("objects")
        if not isinstance(objects, list) or len(objects) != 1:
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Chọn đúng một object.")
        obj = objects[0]
        if not isinstance(obj, dict) or obj.get("namespace") != "cvat_shape":
            raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Object không hợp lệ.")
        valid_ids = {
            str(shape["source"]["id"])
            for shape in frame.snapshot_frame.shapes
            if isinstance(shape, dict)
            and isinstance(shape.get("source"), dict)
            and shape["source"].get("kind") == "shape"
        }
        if obj.get("id") not in valid_ids:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Object không thuộc frame."
            )
        return {
            "kind": kind,
            "objects": [{"namespace": "cvat_shape", "id": obj["id"]}],
            "rule_id": None,
            "bbox": None,
            "policy_version": "anchor-v1",
        }
    bbox = raw.get("bbox")
    if not isinstance(bbox, dict) or set(bbox) != {"x1", "y1", "x2", "y2"}:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Thiếu bbox.")
    coords = [bbox[name] for name in ("x1", "y1", "x2", "y2")]
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        for value in coords
    ):
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "bbox không hợp lệ.")
    x1, y1, x2, y2 = (float(value) for value in coords)
    source = frame.snapshot_frame
    if not (0 <= x1 < x2 <= source.width and 0 <= y1 < y2 <= source.height):
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "bbox ngoài frame.")
    if raw.get("objects") not in (None, []):
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Region ID do server cấp.")
    return {
        "kind": kind,
        "objects": [{"namespace": "reviewer_region", "id": str(uuid.uuid4())}],
        "rule_id": None,
        "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        "policy_version": "anchor-v1",
    }


@transaction.atomic
def create_manual_issue(*, request: Request) -> Issue:
    body = _body(request)
    frame_id = _positive_int(body.get("frame_id"), "frame_id")
    lease_id = _positive_int(body.get("lease_id"), "lease_id")
    family = body.get("family")
    if family not in Issue.Family.values:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "family không hợp lệ.")
    description = body.get("description", "")
    if not isinstance(description, str) or len(description) > 2000:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "description không hợp lệ.")
    key = _idempotency(request)
    request_hash = _request_hash(body)
    relation = FrameReview.objects.filter(pk=frame_id).values("run_id").first()
    if relation is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Frame không tồn tại.")
    user = _actor(request)
    User.objects.select_for_update().get(pk=user.pk)
    QCRun.objects.select_for_update().get(pk=relation["run_id"])
    frame = FrameReview.objects.select_related("snapshot_frame__snapshot_job", "run").get(
        pk=frame_id
    )
    _authorize_frame(request, frame=frame, action="issues.create")
    if key is not None:
        old = Issue.objects.filter(created_by=user, idempotency_key=key).first()
        if old is not None:
            if old.request_hash != request_hash:
                raise ApiError(
                    status.HTTP_409_CONFLICT,
                    "IDEMPOTENCY_KEY_REUSED",
                    "Idempotency-Key đã dùng với body khác.",
                )
            return old
    _owned_lease(request, frame=frame, lease_id=lease_id, action="issues.create")
    anchor = _manual_anchor(body.get("anchor"), frame)
    if (
        anchor["kind"] == "manual_object"
        and Issue.objects.filter(frame_review=frame, family=family, anchor=anchor).exists()
    ):
        raise ApiError(status.HTTP_409_CONFLICT, "ISSUE_EXISTS", "Issue đã tồn tại.")
    issue = Issue.objects.create(
        frame_review=frame,
        family=family,
        origin=Issue.Origin.REVIEWER,
        state=Issue.State.IN_REVIEW,
        anchor=anchor,
        description=description.strip(),
        created_by=user,
        idempotency_key=key,
        request_hash=request_hash,
    )
    append_audit_event(
        actor=user,
        action="issue.create_manual",
        object_type="issue",
        object_id=issue.pk,
        before=None,
        after={"state": issue.state, "family": issue.family, "anchor": issue.anchor},
        revision=frame.run.snapshot.revision_sha256,
        reason=issue.description,
    )
    return issue


_PAST_REVIEW_STATES = (
    FrameReview.State.REVIEWED,
    FrameReview.State.AWAITING_FOLLOWUP,
    FrameReview.State.COMPLETED,
)


def _record_completion_once(user: User, frame: FrameReview) -> None:
    """Audit frame.complete for a retry whose first completion left no event (hand-over)."""

    if AuditEvent.objects.filter(
        action="frame.complete", object_type="frame", object_id=str(frame.pk)
    ).exists():
        return
    append_audit_event(
        actor=user,
        action="frame.complete",
        object_type="frame",
        object_id=frame.pk,
        before={"state": frame.state},
        after={"state": frame.state},
        revision=frame.run.snapshot.revision_sha256,
        reason="Review completed (lease already closed by hand-over)",
    )


def _conflict_details(frame: FrameReview) -> dict[str, object]:
    return {"frame_state": frame.state}


@transaction.atomic
def complete_frame(*, request: Request, frame_id: int) -> FrameReview:
    body = _body(request)
    lease_id = _positive_int(body.get("lease_id"), "lease_id")
    relation = FrameReview.objects.filter(pk=frame_id).values("run_id").first()
    if relation is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Frame không tồn tại.")
    user = _actor(request)
    User.objects.select_for_update().get(pk=user.pk)
    QCRun.objects.select_for_update().get(pk=relation["run_id"])
    frame = FrameReview.objects.select_related("run__snapshot", "snapshot_frame__snapshot_job").get(
        pk=frame_id
    )
    if not has_review_scope(user_id=user.pk, dataset_id=frame.run.dataset_id):
        raise ApiError(status.HTTP_403_FORBIDDEN, "OUT_OF_SCOPE", "Ngoài phạm vi dataset.")
    identity = _reviewer_identity(request, action="frames.complete")
    _deny_frame_ineligible(request, identity, frame, "frames.complete")
    lease = Lease.objects.filter(pk=lease_id, frame_review=frame, holder=user).first()
    if (
        lease is not None
        and lease.closed_at is not None
        and frame.state in _PAST_REVIEW_STATES
        and not decision_source.undecided_issue_ids(frame)
    ):
        # Idempotent retry by the former holder: the frame already left review (completed by
        # this call earlier, handed over by a verify, or finished by the final scope). No state,
        # lease or effort effect; the completion audit is written once.
        _record_completion_once(user, frame)
        return frame
    if frame.state != FrameReview.State.IN_REVIEW:
        record_rejection_audit(
            request=request,
            code="LEASE_CONFLICT",
            object_type="lease",
            object_id=lease_id,
            action="frames.complete",
            message="Frame is no longer in review.",
        )
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "LEASE_CONFLICT",
            "Frame không còn ở trạng thái đang review nên không thể hoàn tất bằng lease này.",
            _conflict_details(frame),
        )
    try:
        _owned_lease(request, frame=frame, lease_id=lease_id, action="frames.complete")
    except ApiError as exc:
        if exc.error_code != "LEASE_CONFLICT":
            raise
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "LEASE_CONFLICT",
            "Lease không còn hợp lệ.",
            _conflict_details(frame),
        ) from exc
    undecided = decision_source.undecided_issue_ids(frame)
    if undecided:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "BUSINESS_RULE_UNMET",
            "Còn issue chưa có quyết định.",
            {"undecided_issue_ids": sorted(undecided)},
        )
    assert lease is not None
    lease.closed_at = _now()
    lease.save(update_fields=["closed_at"])
    frame.state = FrameReview.State.REVIEWED
    # Rework verified while the reviewer was still deciding: hand the frame over to follow-up
    # now that nothing is left to decide (same transaction; a repeat call is a no-op above).
    if decision_source.frame_reworks_all_resolved(frame):
        frame.state = FrameReview.State.AWAITING_FOLLOWUP
    frame.save(update_fields=["state"])
    append_audit_event(
        actor=user,
        action="frame.complete",
        object_type="frame",
        object_id=frame.pk,
        before={"state": FrameReview.State.IN_REVIEW},
        after={"state": frame.state},
        revision=frame.run.snapshot.revision_sha256,
        reason="Review completed",
    )
    return frame
