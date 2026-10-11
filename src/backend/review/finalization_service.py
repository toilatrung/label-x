"""Build and select the full-scope final QC run (FR-RWK-06/08)."""

from __future__ import annotations

import hashlib
import json

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import QuerySet

from engines.interface import EngineStatus
from orchestration.services import ledger_counts
from review.models import FinalRunVerification, Issue, ReworkRequest, ReworkVerification
from runs.models import QCRun
from runs.services import ScopeBusyError, create_qc_run
from snapshots.models import Snapshot
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
    if Issue.objects.filter(frame_review__run=origin_run).exclude(
        state__in=_CLOSED_ISSUE_STATES
    ).exists():
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
        QCRun.objects.select_for_update().filter(
            origin_run=origin_run,
            is_final=True,
            idempotency_key__startswith=run_key_base,
        ).order_by("pk")
    )
    existing = next(
        (
            run
            for run in reversed(previous_attempts)
            if run.status
            in (QCRun.Status.QUEUED, QCRun.Status.RUNNING, QCRun.Status.COMPLETED)
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


def operational_run(origin_run: QCRun) -> QCRun:
    """Resolve the safe source for operational history/report consumers.

    This function does not mutate the origin pointer. A final Partial/Failed/
    Cancelled run, incomplete ledger, or newly opened issue therefore leaves the
    original run authoritative.
    """

    if Issue.objects.filter(frame_review__run=origin_run).exclude(
        state__in=_CLOSED_ISSUE_STATES
    ).exists():
        return origin_run
    candidates = QCRun.objects.filter(
        origin_run=origin_run, is_final=True, status=QCRun.Status.COMPLETED
    ).order_by("-finished_at", "-pk")
    for candidate in candidates:
        if Issue.objects.filter(frame_review__run=candidate).exclude(
            state__in=_CLOSED_ISSUE_STATES
        ).exists():
            continue
        if has_complete_required_coverage(candidate):
            return candidate
    return origin_run
