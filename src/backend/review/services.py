"""Atomic queue claim and lease renewal for E-13."""

from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.request import Request

from accounts.models import CvatIdentity, Role, RoleAssignment
from accounts.permissions import record_rejection_audit
from config.exceptions import ApiError
from review import decision_source
from review.models import FrameReview, Lease
from runs.models import QCRun, RunRanking, RunRankingEntry
from snapshots.models import SnapshotJob


def _now() -> datetime:
    """Server clock seam; tests inject an exact boundary, clients cannot."""
    return timezone.now()


def _policy_seconds(name: str) -> int:
    """TBD-09 values must be supplied by approved deployment configuration."""
    raw = getattr(settings, name, None)
    if isinstance(raw, bool) or raw is None or not str(raw).isdigit() or int(raw) <= 0:
        raise ImproperlyConfigured(f"{name} requires an approved positive integer policy")
    return int(raw)


def _actor(request: Request) -> User:
    user = request.user
    if not isinstance(user, User) or user.pk is None:
        raise ApiError(status.HTTP_403_FORBIDDEN, "NOT_AUTHENTICATED", "Chưa đăng nhập.")
    return user


def _reviewer_identity(request: Request, *, action: str = "queues.next") -> CvatIdentity:
    user = _actor(request)
    identity = CvatIdentity.objects.select_related("employee").filter(user=user).first()
    if identity is None or identity.employee is None or not identity.employee.is_verified:
        record_rejection_audit(
            request=request,
            code="IDENTITY_MAPPING_MISSING",
            object_type="reviewer",
            object_id=user.pk,
            action=action,
            message="Reviewer identity is not verified.",
        )
        raise ApiError(
            status.HTTP_403_FORBIDDEN, "IDENTITY_MAPPING_MISSING", "Thiếu định danh đã xác minh."
        )
    return identity


def _ineligibility_code(identity: CvatIdentity, entry: RunRankingEntry) -> str | None:
    return _ineligibility_code_for_job(identity, entry.snapshot_frame.snapshot_job)


def _ineligibility_code_for_job(identity: CvatIdentity, job: SnapshotJob) -> str | None:
    author_id = job.assignee_cvat_user_id
    if author_id is None:
        return "IDENTITY_MAPPING_MISSING"
    if author_id == identity.cvat_user_id:
        return "SELF_REVIEW_FORBIDDEN"
    author = CvatIdentity.objects.select_related("employee").filter(cvat_user_id=author_id).first()
    if author is None or author.employee is None or not author.employee.is_verified:
        return "IDENTITY_MAPPING_MISSING"
    if job.assignee_user_id is not None and author.user_id != job.assignee_user_id:
        return "IDENTITY_MAPPING_MISSING"
    if author.employee_id == identity.employee_id:
        return "SELF_REVIEW_FORBIDDEN"
    return None


def _deny_frame_ineligible(
    request: Request, identity: CvatIdentity, frame: FrameReview, action: str
) -> None:
    code = _ineligibility_code_for_job(identity, frame.snapshot_frame.snapshot_job)
    if code is None:
        return
    record_rejection_audit(
        request=request,
        code=code,
        object_type="frame",
        object_id=frame.pk,
        action=action,
        message="Snapshot assignee identity forbids this review.",
    )
    raise ApiError(status.HTTP_403_FORBIDDEN, code, "Không thể review frame này.")


def _deny_ineligible(
    request: Request, identity: CvatIdentity, entry: RunRankingEntry, action: str
) -> None:
    code = _ineligibility_code(identity, entry)
    if code is None:
        return
    record_rejection_audit(
        request=request,
        code=code,
        object_type="frame",
        object_id=entry.snapshot_frame_id,
        action=action,
        message="Snapshot assignee identity forbids this review.",
    )
    raise ApiError(status.HTTP_403_FORBIDDEN, code, "Không thể review frame này.")


def _close_expired(lease: Lease, now: datetime) -> None:
    """Materialize expiry under the same run lock as claim/renew."""
    lease.refresh_from_db()
    if lease.closed_at is not None or lease.expires_at > now:
        return
    frame = lease.frame_review
    frame.refresh_from_db()
    lease.closed_at = now
    lease.save(update_fields=["closed_at"])
    if frame.state != FrameReview.State.IN_REVIEW:
        # The frame moved on while the lease stayed open (e.g. rework verified ->
        # awaiting_followup, or reviewed/completed): expiry must not rewrite its state.
        return
    saved = decision_source.has_persisted_decision(frame)
    frame.state = FrameReview.State.INCOMPLETE if saved else FrameReview.State.UNREVIEWED
    frame.previous_reviewer_id = lease.holder_id if saved else None
    # Reservation is measured from the actual expiry, not delayed materialization.
    frame.incomplete_since = lease.expires_at if saved else None
    frame.save(update_fields=["state", "previous_reviewer", "incomplete_since"])
    decision_source.reset_undecided_issues(frame)


def _grant_payload(lease: Lease, entry: RunRankingEntry, *, resumed: bool) -> dict[str, object]:
    frame = lease.frame_review
    source_frame = entry.snapshot_frame
    return {
        "lease": {
            "id": lease.pk,
            "frame_id": frame.pk,
            "holder_user_id": lease.holder_id,
            "expires_at": lease.expires_at.isoformat(),
        },
        "frame": {
            "id": frame.pk,
            "run_id": frame.run_id,
            "frame_key": {
                "cvat_task_id": source_frame.snapshot_job.cvat_task_id,
                "frame_number": source_frame.frame_index,
            },
            "cvat_job_id": source_frame.snapshot_job.cvat_job_id,
            "rank": entry.rank,
            "review_state": frame.state,
            "missing_evidence": entry.missing_evidence,
            "width": source_frame.width,
            "height": source_frame.height,
        },
        "resumed": resumed,
    }


def _ranking_entry(run_id: int, frame_id: int, source: str) -> RunRankingEntry:
    ranking_source = RunRanking.Source.RISK if source == "risk" else RunRanking.Source.RANDOM_AUDIT
    entry = (
        RunRankingEntry.objects.select_related("snapshot_frame__snapshot_job")
        .filter(ranking__run_id=run_id, ranking__source=ranking_source, snapshot_frame_id=frame_id)
        .first()
    )
    if entry is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Không còn ranking provenance cho lease."
        )
    return entry


@transaction.atomic
def claim_next(*, request: Request, run_id: int, queue: str) -> dict[str, object] | None:
    if queue not in {"risk", "random"}:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Queue không hợp lệ.")
    ttl = _policy_seconds("REVIEW_LEASE_TTL_SECONDS")
    reservation = _policy_seconds("REVIEW_INCOMPLETE_RESERVATION_SECONDS")
    identity = _reviewer_identity(request)
    user = _actor(request)
    user_id = int(user.pk)
    # Lock order: user, then run. This serializes claims across runs for one reviewer,
    # and all contenders for a frame in one run. Do not use SKIP LOCKED here.
    User.objects.select_for_update().get(pk=user_id)
    open_for_user = list(
        Lease.objects.select_related("frame_review").filter(holder=user, closed_at__isnull=True)
    )
    lock_ids = {run_id, *(lease.frame_review.run_id for lease in open_for_user)}
    list(QCRun.objects.select_for_update().filter(pk__in=lock_ids).order_by("pk"))
    run = QCRun.objects.filter(pk=run_id).first()
    if run is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Run không tồn tại.")
    now = _now()
    for lease in open_for_user:
        lease.refresh_from_db()
        if lease.closed_at is not None:
            continue
        if lease.expires_at <= now:
            _close_expired(lease, now)
        else:
            active_run = lease.frame_review.run
            if not has_review_scope(user_id=user_id, dataset_id=active_run.dataset_id):
                raise ApiError(
                    status.HTTP_403_FORBIDDEN, "OUT_OF_SCOPE", "Lease ngoài phạm vi hiện tại."
                )
            entry = _ranking_entry(
                active_run.pk, lease.frame_review.snapshot_frame_id, lease.queue_source
            )
            _deny_ineligible(request, identity, entry, "queues.next")
            return _grant_payload(lease, entry, resumed=True)

    ranking_source = RunRanking.Source.RISK if queue == "risk" else RunRanking.Source.RANDOM_AUDIT
    ranking = RunRanking.objects.filter(run=run, source=ranking_source).first()
    if ranking is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Run chưa có queue đã lưu.")
    entries = list(
        RunRankingEntry.objects.filter(ranking=ranking)
        .select_related("snapshot_frame__snapshot_job")
        .order_by("rank", "pk")
    )
    eligible = []
    for entry in entries:
        if _ineligibility_code(identity, entry) is not None:
            continue
        frame, _ = FrameReview.objects.get_or_create(run=run, snapshot_frame=entry.snapshot_frame)
        open_lease = (
            Lease.objects.select_related("frame_review")
            .filter(frame_review=frame, closed_at__isnull=True)
            .first()
        )
        if open_lease is not None:
            if open_lease.expires_at > now:
                continue
            _close_expired(open_lease, now)
            frame.refresh_from_db()
        if frame.state not in {FrameReview.State.UNREVIEWED, FrameReview.State.INCOMPLETE}:
            continue
        if (
            frame.state == FrameReview.State.INCOMPLETE
            and frame.previous_reviewer_id != user_id
            and frame.incomplete_since is not None
            and now < frame.incomplete_since + timedelta(seconds=reservation)
        ):
            continue
        eligible.append((entry, frame))
    if not eligible:
        return None
    # Prefer the holder's unfinished frame before rank order; preserve source provenance.
    entry, frame = min(
        eligible,
        key=lambda pair: (
            pair[1].state != FrameReview.State.INCOMPLETE
            or pair[1].previous_reviewer_id != user_id,
            pair[0].rank,
        ),
    )
    resumed = frame.state == FrameReview.State.INCOMPLETE and frame.previous_reviewer_id == user_id
    try:
        with transaction.atomic():
            decision_source.materialize_candidate_issues(frame)
            frame.state = FrameReview.State.IN_REVIEW
            frame.incomplete_since = None
            frame.save(update_fields=["state", "incomplete_since"])
            decision_source.claim_undecided_issues(frame)
            lease = Lease.objects.create(
                frame_review=frame,
                holder=user,
                queue_source=queue,
                expires_at=now + timedelta(seconds=ttl),
            )
    except IntegrityError as exc:
        if getattr(exc.__cause__, "sqlstate", None) != "23505":
            raise
        # DB constraints are the final backstop if another writer bypasses the lock protocol.
        frame.refresh_from_db()
        existing = Lease.objects.filter(holder=user, closed_at__isnull=True).first()
        if existing is not None and existing.expires_at > now:
            if not has_review_scope(
                user_id=user_id, dataset_id=existing.frame_review.run.dataset_id
            ):
                raise ApiError(
                    status.HTTP_403_FORBIDDEN, "OUT_OF_SCOPE", "Lease ngoài phạm vi hiện tại."
                ) from None
            entry = _ranking_entry(
                existing.frame_review.run_id,
                existing.frame_review.snapshot_frame_id,
                existing.queue_source,
            )
            _deny_ineligible(request, identity, entry, "queues.next")
            return _grant_payload(existing, entry, resumed=True)
        return None
    return _grant_payload(lease, entry, resumed=resumed)


@transaction.atomic
def renew(*, request: Request, lease_id: int) -> Lease | None:
    ttl = _policy_seconds("REVIEW_LEASE_TTL_SECONDS")
    user = _actor(request)
    user_id = int(user.pk)
    # Read only immutable relation IDs first; ownership and expiry are checked after locks.
    relation = Lease.objects.filter(pk=lease_id).values("holder_id", "frame_review__run_id").first()
    if relation is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Lease không tồn tại.")
    User.objects.select_for_update().get(pk=user_id)
    QCRun.objects.select_for_update().get(pk=relation["frame_review__run_id"])
    lease = Lease.objects.select_related("frame_review").get(pk=lease_id)
    now = _now()
    if lease.expires_at <= now and lease.closed_at is None:
        _close_expired(lease, now)
    if lease.holder_id != user_id or lease.closed_at is not None:
        record_rejection_audit(
            request=request,
            code="LEASE_CONFLICT",
            object_type="lease",
            object_id=lease_id,
            action="leases.renew",
            message="Lease expired or caller is not holder.",
        )
        return None
    if not has_review_scope(user_id=user_id, dataset_id=lease.frame_review.run.dataset_id):
        raise ApiError(status.HTTP_403_FORBIDDEN, "OUT_OF_SCOPE", "Lease ngoài phạm vi hiện tại.")
    identity = _reviewer_identity(request, action="leases.renew")
    entry = _ranking_entry(
        lease.frame_review.run_id, lease.frame_review.snapshot_frame_id, lease.queue_source
    )
    _deny_ineligible(request, identity, entry, "leases.renew")
    lease.expires_at = now + timedelta(seconds=ttl)
    lease.renewed_at = now
    lease.save(update_fields=["expires_at", "renewed_at"])
    return lease


def has_review_scope(*, user_id: int, dataset_id: int) -> bool:
    return (
        RoleAssignment.objects.filter(
            user_id=user_id, role__in=[Role.REVIEWER, Role.QA_LEAD, Role.SUPER_ADMIN]
        )
        .filter(Q(dataset_id=dataset_id) | Q(role=Role.SUPER_ADMIN, dataset_id__isnull=True))
        .exists()
    )
