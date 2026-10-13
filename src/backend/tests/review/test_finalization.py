"""T-041 full-scope final run, lineage, retry and source-selection evidence."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from django.contrib.auth.models import User
from django.db import close_old_connections
from django.utils import timezone

from audit.models import AuditEvent
from orchestration.models import LedgerUnit
from review.finalization_service import (
    FinalRunNotReady,
    build_final_run,
    operational_run,
)
from review.models import (
    FinalRunVerification,
    FrameReview,
    Issue,
    ReworkRequest,
    ReworkVerification,
)
from runs.models import EngineResult, QCRun
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot

pytest_plugins = ["tests.review.test_queue_lease"]


def _fixed_snapshot(world):
    return create_locked_snapshot(
        dataset_id=42,
        created_by=world["author"],
        taxonomy_version="tax",
        guideline_version="guide",
        parent_snapshot=world["run"].snapshot,
        jobs=[
            JobExport(
                cvat_job_id=100,
                cvat_task_id=200,
                assignee_cvat_user_id=702,
                assignee_user_id=world["author"].pk,
                source_updated_at="2026-10-11T11:00:00Z",
                annotations={"shapes": [], "tracks": []},
                frames=[
                    FrameExport(
                        frame_index=0,
                        file_name="0.jpg",
                        width=100,
                        height=100,
                        media_bytes=b"fixed-frame-0",
                        media_storage_key="final/0.jpg",
                    )
                ],
            )
        ],
    )


def _resolved_scope(world):
    frame = FrameReview.objects.create(
        run=world["run"], snapshot_frame=world["frame"], state=FrameReview.State.COMPLETED
    )
    issue = Issue.objects.create(
        frame_review=frame,
        family=Issue.Family.E1,
        origin=Issue.Origin.REVIEWER,
        state=Issue.State.RESOLVED,
        anchor={"kind": "manual_region", "objects": []},
        created_by=world["reviewer"],
    )
    fixed = _fixed_snapshot(world)
    recheck = QCRun.objects.create(
        snapshot=fixed,
        config_version=world["run"].config_version,
        seed=world["run"].seed,
        status=QCRun.Status.COMPLETED,
        origin_run=world["run"],
        dataset_id=42,
        scope_hash=fixed.revision_sha256,
        created_by=world["author"],
    )
    rework = ReworkRequest.objects.create(
        issue=issue,
        annotator=world["author"],
        created_by=world["reviewer"],
        status=ReworkRequest.Status.RESOLVED,
        instruction="Fix the box",
        severity=Issue.Severity.MEDIUM,
        cvat_deep_link="http://localhost:8080/tasks/200/jobs/100?frame=0",
        original_revision=world["run"].snapshot.revision_sha256,
        submitted_revision=fixed.revision_sha256,
        recheck_snapshot=fixed,
        recheck_run=recheck,
        due_at=timezone.now(),
        submitted_at=timezone.now(),
        resolved_at=timezone.now(),
    )
    audit = AuditEvent.objects.create(
        actor=world["other"],
        action="rework.verify_pass",
        object_type="rework",
        object_id=str(rework.pk),
        before={},
        after={},
        revision=fixed.revision_sha256,
    )
    verification = ReworkVerification.objects.create(
        rework=rework,
        verifier=world["other"],
        recheck_run=recheck,
        outcome=ReworkVerification.Outcome.PASS,
        revision=fixed.revision_sha256,
        audit_event=audit,
    )
    return issue, fixed, verification


@pytest.mark.django_db
def test_build_final_run_is_idempotent_and_links_verification(world, monkeypatch):
    _issue, fixed, verification = _resolved_scope(world)
    monkeypatch.setattr(
        "review.finalization_service.create_snapshot_from_cvat", lambda **_kwargs: fixed
    )

    final, created = build_final_run(origin_run_id=world["run"].pk, actor=world["other"])
    replay, replay_created = build_final_run(origin_run_id=world["run"].pk, actor=world["other"])

    assert created is True and replay_created is False
    assert replay.pk == final.pk
    assert final.is_final is True and final.origin_run_id == world["run"].pk
    assert final.snapshot_id == fixed.pk
    assert (
        FinalRunVerification.objects.filter(final_run=final, verification=verification).count() == 1
    )
    world["run"].refresh_from_db()
    assert world["run"].is_final is False and world["run"].status == QCRun.Status.COMPLETED


@pytest.mark.django_db(transaction=True)
def test_concurrent_final_triggers_have_one_effect(world, monkeypatch):
    _issue, fixed, _verification = _resolved_scope(world)
    monkeypatch.setattr(
        "review.finalization_service.create_snapshot_from_cvat", lambda **_kwargs: fixed
    )
    origin_id = world["run"].pk
    actor_id = world["other"].pk

    def trigger() -> tuple[int, bool]:
        close_old_connections()
        try:
            run, created = build_final_run(
                origin_run_id=origin_id, actor=User.objects.get(pk=actor_id)
            )
            return run.pk, created
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: trigger(), range(2)))

    assert len({run_id for run_id, _created in results}) == 1
    assert sorted(created for _run_id, created in results) == [False, True]
    assert QCRun.objects.filter(origin_run_id=origin_id, is_final=True).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "terminal_status",
    [QCRun.Status.PARTIAL, QCRun.Status.FAILED, QCRun.Status.CANCELLED],
)
def test_terminal_attempt_can_retry_without_two_active_effects(world, monkeypatch, terminal_status):
    _issue, fixed, _verification = _resolved_scope(world)
    monkeypatch.setattr(
        "review.finalization_service.create_snapshot_from_cvat", lambda **_kwargs: fixed
    )
    first, _ = build_final_run(origin_run_id=world["run"].pk, actor=world["other"])
    first.status = terminal_status
    first.finished_at = timezone.now()
    first.save(update_fields=["status", "finished_at"])

    second, created = build_final_run(origin_run_id=world["run"].pk, actor=world["other"])
    assert created is True and second.pk != first.pk
    assert (
        QCRun.objects.filter(
            origin_run=world["run"],
            is_final=True,
            status__in=[QCRun.Status.QUEUED, QCRun.Status.RUNNING],
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_open_issue_blocks_finalization(world, monkeypatch):
    issue, fixed, _verification = _resolved_scope(world)
    issue.state = Issue.State.REOPENED
    issue.save(update_fields=["state"])
    monkeypatch.setattr(
        "review.finalization_service.create_snapshot_from_cvat", lambda **_kwargs: fixed
    )
    with pytest.raises(FinalRunNotReady, match="issue"):
        build_final_run(origin_run_id=world["run"].pk, actor=world["other"])
    assert not QCRun.objects.filter(is_final=True).exists()


@pytest.mark.django_db
def test_operational_source_changes_only_after_complete_required_ledger(world, monkeypatch):
    issue, fixed, _verification = _resolved_scope(world)
    monkeypatch.setattr(
        "review.finalization_service.create_snapshot_from_cvat", lambda **_kwargs: fixed
    )
    final, _ = build_final_run(origin_run_id=world["run"].pk, actor=world["other"])
    assert operational_run(world["run"]).pk == world["run"].pk

    final.engine_results.all().delete()
    result = EngineResult.objects.create(
        run=final,
        engine="geometry",
        status="checked",
        eligible_units=1,
        completed_units=1,
        failed_units=0,
        not_checked_units=0,
        required=True,
    )
    LedgerUnit.objects.create(
        run=final,
        engine=result.engine,
        kind="frame",
        cvat_task_id=200,
        frame_number=0,
        outcome="completed",
    )
    final.status = QCRun.Status.COMPLETED
    final.finished_at = timezone.now()
    final.save(update_fields=["status", "finished_at"])
    assert operational_run(world["run"]).pk == final.pk

    Issue.objects.create(
        frame_review=issue.frame_review,
        family=Issue.Family.E2,
        origin=Issue.Origin.REVIEWER,
        state=Issue.State.PENDING_REVIEW,
        anchor={"kind": "manual_region", "objects": []},
    )
    assert operational_run(world["run"]).pk == world["run"].pk
