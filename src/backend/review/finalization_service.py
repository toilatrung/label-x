"""Build and select the full-scope final QC run (FR-RWK-06/08)."""

from __future__ import annotations

import hashlib
import json

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Exists, OuterRef, QuerySet

from engines.interface import EngineStatus
from orchestration.models import CandidateRecord
from orchestration.services import ledger_counts
from review import decision_source
from review.models import (
    FinalRunVerification,
    FrameReview,
    Issue,
    ReworkRequest,
    ReworkVerification,
)
from runs.models import QCRun
from runs.services import ScopeBusyError, create_qc_run
from snapshots.models import Snapshot, SnapshotFrame
from snapshots.orchestration import SnapshotScope, create_snapshot_from_cvat


class FinalRunNotReady(RuntimeError):
    """The origin scope still has unresolved review or rework."""


class FinalSnapshotFailed(RuntimeError):
    """The authoritative full-scope CVAT read could not produce a locked snapshot."""


_CLOSED_ISSUE_STATES = (Issue.State.REJECTED, Issue.State.RESOLVED)


def _scope_reworks(origin_run: QCRun) -> QuerySet[ReworkRequest]:
    return ReworkRequest.objects.filter(issue__frame_review__run=origin_run).order_by("pk")


def _assert_scope_ready(origin_run: QCRun) -> list[ReworkVerification]:
    """Validate readiness while the caller holds the origin QCRun row lock."""

    if origin_run.is_final or origin_run.origin_run_id is not None:
        raise FinalRunNotReady("Chỉ run gốc mới có thể tạo final run toàn phạm vi.")
    if origin_run.status != QCRun.Status.COMPLETED:
        raise FinalRunNotReady("Run gốc chưa Completed.")
    if (
        Issue.objects.filter(frame_review__run=origin_run)
        .exclude(state__in=_CLOSED_ISSUE_STATES)
        .exists()
    ):
        raise FinalRunNotReady("Phạm vi còn issue mở hoặc đang chờ review.")

    reworks = list(_scope_reworks(origin_run).select_for_update())
    if not reworks:
        raise FinalRunNotReady("Phạm vi không có rework; run gốc là nguồn cuối.")
    if any(rework.status != ReworkRequest.Status.RESOLVED for rework in reworks):
        raise FinalRunNotReady("Phạm vi còn rework chưa resolved.")

    verifications = list(
        ReworkVerification.objects.filter(rework__in=reworks)
        .select_related("rework")
        .order_by("pk")
    )
    passed_reworks = {
        verification.rework_id
        for verification in verifications
        if verification.outcome == ReworkVerification.Outcome.PASS
    }
    if passed_reworks != {rework.pk for rework in reworks}:
        raise FinalRunNotReady("Mỗi rework resolved phải có verification pass.")
    return verifications


def _lineage_token(origin_run: QCRun, verifications: list[ReworkVerification]) -> str:
    payload = {
        "origin_run_id": origin_run.pk,
        "verifications": [
            {
                "id": verification.pk,
                "outcome": verification.outcome,
                "revision": verification.revision,
            }
            for verification in verifications
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _assert_snapshot_contains_verified_revisions(
    snapshot: Snapshot, verifications: list[ReworkVerification]
) -> None:
    """Fail closed when the full export does not contain the latest verified job revision."""

    latest_by_job: dict[int, ReworkRequest] = {}
    for verification in verifications:
        rework = verification.rework
        if verification.outcome != ReworkVerification.Outcome.PASS:
            continue
        job_id = rework.issue.frame_review.snapshot_frame.snapshot_job.cvat_job_id
        previous = latest_by_job.get(job_id)
        if previous is None or rework.pk > previous.pk:
            latest_by_job[job_id] = rework

    final_hashes = dict(snapshot.jobs.values_list("cvat_job_id", "sha256"))
    for job_id, rework in latest_by_job.items():
        recheck_snapshot = rework.recheck_snapshot
        if recheck_snapshot is None:
            raise FinalRunNotReady("Rework resolved thiếu snapshot re-check.")
        verified_hash = (
            recheck_snapshot.jobs.filter(cvat_job_id=job_id)
            .values_list("sha256", flat=True)
            .first()
        )
        if verified_hash is None or final_hashes.get(job_id) != verified_hash:
            raise FinalRunNotReady(
                f"Snapshot final không chứa revision đã verify của CVAT job {job_id}."
            )


@transaction.atomic
def build_final_run(*, origin_run_id: int, actor: User) -> tuple[QCRun, bool]:
    """Snapshot the complete original scope and create one idempotent final run.

    The origin QCRun lock is intentionally held across the read-only CVAT export. All
    issue/rework writers take this lock first, so a concurrent verify or new issue
    cannot make the readiness decision stale between export and final-run creation.
    """

    origin_run = (
        QCRun.objects.select_for_update()
        .select_related("snapshot", "config_version")
        .get(pk=origin_run_id)
    )
    verifications = _assert_scope_ready(origin_run)
    token = _lineage_token(origin_run, verifications)
    run_key_base = f"final-run-{origin_run.pk}-{token}"
    previous_attempts = list(
        QCRun.objects.select_for_update()
        .filter(
            origin_run=origin_run,
            is_final=True,
            idempotency_key__startswith=run_key_base,
        )
        .order_by("pk")
    )
    existing = next(
        (
            run
            for run in reversed(previous_attempts)
            if run.status in (QCRun.Status.QUEUED, QCRun.Status.RUNNING, QCRun.Status.COMPLETED)
        ),
        None,
    )
    if existing is not None:
        FinalRunVerification.objects.bulk_create(
            [
                FinalRunVerification(final_run=existing, verification=verification)
                for verification in verifications
            ],
            ignore_conflicts=True,
        )
        return existing, False
    attempt = len(previous_attempts) + 1
    run_key = run_key_base if attempt == 1 else f"{run_key_base}-{attempt}"

    job_ids = tuple(
        origin_run.snapshot.jobs.order_by("cvat_job_id").values_list("cvat_job_id", flat=True)
    )
    if not job_ids:
        raise FinalRunNotReady("Snapshot run gốc không có job trong phạm vi.")
    snapshot = create_snapshot_from_cvat(
        dataset_id=origin_run.dataset_id,
        scope=SnapshotScope(cvat_job_ids=job_ids),
        note=f"T-041 final scope for origin run {origin_run.pk}",
        created_by=actor,
        idempotency_key=f"final-snapshot-{origin_run.pk}-{token}",
    )
    if snapshot.status != Snapshot.Status.LOCKED:
        raise FinalSnapshotFailed("Snapshot final không khóa được do source drift hoặc export lỗi.")
    _assert_snapshot_contains_verified_revisions(snapshot, verifications)

    try:
        final_run, created = create_qc_run(
            snapshot_id=snapshot.pk,
            config_version_id=origin_run.config_version_id,
            seed=origin_run.seed,
            created_by=actor,
            idempotency_key=run_key,
            is_final=True,
            origin_run_id=origin_run.pk,
        )
    except ScopeBusyError:
        # A different origin may cover the same immutable scope. Never redirect
        # lineage silently: let the retry re-evaluate after that active run ends.
        raise

    FinalRunVerification.objects.bulk_create(
        [
            FinalRunVerification(final_run=final_run, verification=verification)
            for verification in verifications
        ],
        ignore_conflicts=True,
    )
    return final_run, created


def has_complete_required_coverage(run: QCRun) -> bool:
    """True only when every required engine has a complete persisted ledger."""

    if run.status != QCRun.Status.COMPLETED:
        return False
    required = list(run.engine_results.filter(required=True))
    if not required:
        return False
    for result in required:
        ledger = ledger_counts(run.pk, result.engine)
        if (
            result.status != EngineStatus.CHECKED.value
            or ledger.eligible <= 0
            or ledger.completed != ledger.eligible
            or ledger.failed
            or ledger.pending
            or result.eligible_units != ledger.eligible
            or result.completed_units != ledger.completed
            or result.failed_units != ledger.failed
            or result.not_checked_units != ledger.not_checked
        ):
            return False
    return True


def _has_open_issue(run: QCRun) -> bool:
    return (
        Issue.objects.filter(frame_review__run=run).exclude(state__in=_CLOSED_ISSUE_STATES).exists()
    )


def unreviewed_new_candidates(origin_run: QCRun, final_run: QCRun) -> QuerySet[CandidateRecord]:
    """Final-run candidates absent from the origin run that have no closed human outcome.

    A candidate with the same dedup key existed when the origin scope was reviewed, so it is
    not "new". Anything else must be routed to the review queue and decided (issue rejected
    or resolved) before the final run can become the operational source.
    """

    known = CandidateRecord.objects.filter(run=origin_run).values("dedup_key")
    decided = Issue.objects.filter(candidate_id=OuterRef("pk"), state__in=_CLOSED_ISSUE_STATES)
    return (
        CandidateRecord.objects.filter(run=final_run)
        .exclude(dedup_key__in=known)
        .exclude(Exists(decided))
        .order_by("pk")
    )


def final_source_blockers(origin_run: QCRun, final_run: QCRun) -> list[str]:
    """Every reason one final attempt cannot be the source, in evaluation order (read-only).

    A non-Completed attempt has the single reason ``final_run_<status>``: its candidates,
    issues and ledger say nothing about the scope. A Completed one can be blocked by several
    independent reasons at once.
    """

    if final_run.status != QCRun.Status.COMPLETED:
        return [f"final_run_{final_run.status}"]
    reasons = []
    if _has_open_issue(final_run):
        reasons.append("open_issue_in_final_run")
    if unreviewed_new_candidates(origin_run, final_run).exists():
        reasons.append("new_candidate_unreviewed")
    if not has_complete_required_coverage(final_run):
        reasons.append("coverage_incomplete")
    return reasons


def final_source_status(origin_run: QCRun, final_run: QCRun) -> tuple[bool, str]:
    """Return ``(selectable, reason)`` for one final attempt; never mutates anything.

    ``reason`` is the first blocker (the evaluation order decides the source); the full list
    is ``final_source_blockers``.
    """

    blockers = final_source_blockers(origin_run, final_run)
    return (False, blockers[0]) if blockers else (True, "selected")


def evaluate_operational_source(
    origin_run: QCRun,
) -> tuple[QCRun, str, list[dict[str, object]], dict[int, list[str]]]:
    """Pick the safe source (read-only) and keep every attempt's full blocker list.

    Each attempt is evaluated once; ``blockers`` maps its run id to all its reasons, while the
    attempt's own ``reason`` stays the first blocker (the evaluation order decides the source).
    """

    attempts: list[dict[str, object]] = []
    blockers: dict[int, list[str]] = {}
    if _has_open_issue(origin_run):
        return origin_run, "origin_has_open_issue", attempts, blockers
    selected: QCRun | None = None
    for candidate in QCRun.objects.filter(origin_run=origin_run, is_final=True).order_by(
        "-finished_at", "-pk"
    ):
        found = final_source_blockers(origin_run, candidate)
        blockers[candidate.pk] = found
        reason = found[0] if found else "selected"
        attempts.append({"run_id": candidate.pk, "status": candidate.status, "reason": reason})
        if not found and selected is None:
            selected = candidate
    if selected is None:
        return origin_run, "no_valid_final", attempts, blockers
    return selected, "selected_final", attempts, blockers


def select_operational_source(origin_run: QCRun) -> tuple[QCRun, str, list[dict[str, object]]]:
    """Pick the safe source and explain each final attempt (read-only).

    A final Partial/Failed/Cancelled run, incomplete ledger, new unreviewed candidate or a
    newly opened issue leaves the original run authoritative.
    """

    source, reason, attempts, _blockers = evaluate_operational_source(origin_run)
    return source, reason, attempts


def operational_run(origin_run: QCRun) -> QCRun:
    """Resolve the safe source for operational history/report consumers."""

    return select_operational_source(origin_run)[0]


def route_new_candidates(origin_run: QCRun, final_run: QCRun) -> int:
    """Send new final-run candidates to the review queue as pending issues (idempotent).

    Each candidate is attached to the final run's FrameReview for its snapshot frame; a frame
    that was already finished goes back to UNREVIEWED so the queue can claim it. Returns the
    number of issues created by this call; a repeat call creates none.
    """

    routed = 0
    for candidate in unreviewed_new_candidates(origin_run, final_run):
        snapshot_frame = SnapshotFrame.objects.filter(
            snapshot_job__snapshot_id=final_run.snapshot_id,
            snapshot_job__cvat_task_id=candidate.cvat_task_id,
            frame_index=candidate.frame_number,
        ).first()
        if snapshot_frame is None:
            continue
        frame, _ = FrameReview.objects.select_for_update().get_or_create(
            run=final_run, snapshot_frame=snapshot_frame
        )
        _issue, created = decision_source.materialize_candidate_issue(frame, candidate)
        if not created:
            continue
        routed += 1
        if frame.state in (
            FrameReview.State.COMPLETED,
            FrameReview.State.REVIEWED,
            FrameReview.State.AWAITING_FOLLOWUP,
        ):
            frame.state = FrameReview.State.UNREVIEWED
            frame.save(update_fields=["state"])
    return routed


def _frame_may_complete(frame: FrameReview) -> bool:
    """A frame completes only when every issue on it is closed and every rework resolved."""

    if frame.issues.exclude(state__in=_CLOSED_ISSUE_STATES).exists():
        return False
    return (
        not ReworkRequest.objects.filter(issue__frame_review=frame)
        .exclude(status=ReworkRequest.Status.RESOLVED)
        .exists()
    )


@transaction.atomic
def complete_scope_frames(origin_run_id: int) -> int:
    """Finalize scope frames once a valid final source is selected (idempotent).

    Verify-pass alone never completes a frame: this runs only after the final run is
    Completed with full coverage and no unreviewed new candidate. Returns frames changed.
    """

    origin_run = QCRun.objects.select_for_update().get(pk=origin_run_id)
    if origin_run.is_final or origin_run.origin_run_id is not None:
        return 0
    for attempt in QCRun.objects.select_for_update().filter(
        origin_run=origin_run, is_final=True, status=QCRun.Status.COMPLETED
    ):
        if has_complete_required_coverage(attempt):
            route_new_candidates(origin_run, attempt)
    source, _reason, _attempts = select_operational_source(origin_run)
    if source.pk == origin_run.pk:
        return 0
    changed = 0
    frames = (
        FrameReview.objects.select_for_update()
        .filter(run=origin_run, state=FrameReview.State.AWAITING_FOLLOWUP)
        .order_by("pk")
    )
    for frame in frames:
        if _frame_may_complete(frame):
            frame.state = FrameReview.State.COMPLETED
            frame.save(update_fields=["state"])
            changed += 1
    return changed
