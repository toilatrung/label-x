"""M03-R07/R08: final-source guard, frame completion and D05 lineage payloads.

Fixtures are synthetic DB rows (no CVAT export); they prove service behaviour only and are
not real-data E2E evidence.
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from orchestration.models import CandidateRecord, LedgerUnit, ShardCommit
from review.finalization_service import (
    build_final_run,
    complete_scope_frames,
    operational_run,
    select_operational_source,
    unreviewed_new_candidates,
)
from review.lineage import run_lineage_fields
from review.models import FrameReview, Issue, ReworkRequest
from review.tasks import sweep_ready_final_runs
from runs.models import EngineResult, QCRun
from tests.review.test_finalization import _resolved_scope
from tests.review.test_queue_lease import world  # noqa: F401

pytest_plugins = ["tests.review.test_queue_lease"]


def _candidate(run: QCRun, key: str) -> CandidateRecord:
    shard, _ = ShardCommit.objects.get_or_create(
        run=run,
        engine="geometry",
        shard_index=0,
        defaults={
            "idempotency_key": f"shard-{run.pk}",
            "snapshot_id": run.snapshot_id,
            "engine_version": "1",
            "output_sha256": "0" * 64,
        },
    )
    return CandidateRecord.objects.create(
        run=run,
        dedup_key=key,
        shard=shard,
        engine="geometry",
        engine_version="1",
        family="E1",
        cvat_task_id=200,
        frame_number=0,
        anchor={"kind": "manual_region", "objects": []},
        policy_version="p1",
        evidence={},
        evidence_sha256="1" * 64,
    )


def _complete_final(final: QCRun) -> None:
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


@pytest.fixture
def final_world(world, monkeypatch):  # noqa: F811
    issue, fixed, verification = _resolved_scope(world)
    monkeypatch.setattr(
        "review.finalization_service.create_snapshot_from_cvat", lambda **_kwargs: fixed
    )
    final, _ = build_final_run(origin_run_id=world["run"].pk, actor=world["other"])
    return {**world, "issue": issue, "final": final, "verification": verification}


@pytest.mark.django_db
def test_new_unreviewed_candidate_blocks_source_until_human_decision(final_world):
    origin, final = final_world["run"], final_world["final"]
    _complete_final(final)
    assert operational_run(origin).pk == final.pk

    new = _candidate(final, "new-candidate")
    assert list(unreviewed_new_candidates(origin, final)) == [new]
    source, reason, attempts = select_operational_source(origin)
    assert source.pk == origin.pk and reason == "no_valid_final"
    assert attempts == [
        {"run_id": final.pk, "status": "completed", "reason": "new_candidate_unreviewed"}
    ]

    routed = Issue.objects.create(
        frame_review=final_world["issue"].frame_review,
        candidate=new,
        family=Issue.Family.E1,
        origin=Issue.Origin.ENGINE,
        state=Issue.State.PENDING_REVIEW,
        anchor=new.anchor,
    )
    assert operational_run(origin).pk == origin.pk  # routed to queue, still undecided

    routed.state = Issue.State.REJECTED
    routed.save(update_fields=["state"])
    assert operational_run(origin).pk == final.pk  # decided -> final becomes valid
    assert not unreviewed_new_candidates(origin, final).exists()


@pytest.mark.django_db
def test_candidate_already_known_in_origin_is_not_new(final_world):
    origin, final = final_world["run"], final_world["final"]
    _candidate(origin, "same-key")
    _candidate(final, "same-key")
    _complete_final(final)
    assert not unreviewed_new_candidates(origin, final).exists()
    assert operational_run(origin).pk == final.pk


@pytest.mark.django_db
@pytest.mark.parametrize(
    "terminal", [QCRun.Status.PARTIAL, QCRun.Status.FAILED, QCRun.Status.CANCELLED]
)
def test_non_completed_final_never_changes_source(final_world, terminal):
    final = final_world["final"]
    _complete_final(final)
    final.status = terminal
    final.save(update_fields=["status"])
    source, reason, attempts = select_operational_source(final_world["run"])
    assert source.pk == final_world["run"].pk
    assert attempts[0]["reason"] == f"final_run_{terminal}"
    assert run_lineage_fields(final)["selected_final_sources"] == []


@pytest.mark.django_db
def test_verify_pass_frame_waits_for_final_completed(final_world):
    origin, final = final_world["run"], final_world["final"]
    frame = final_world["issue"].frame_review
    frame.state = FrameReview.State.AWAITING_FOLLOWUP
    frame.save(update_fields=["state"])

    assert complete_scope_frames(origin.pk) == 0  # final run still queued
    frame.refresh_from_db()
    assert frame.state == FrameReview.State.AWAITING_FOLLOWUP

    _complete_final(final)
    assert complete_scope_frames(origin.pk) == 1
    assert complete_scope_frames(origin.pk) == 0  # idempotent
    frame.refresh_from_db()
    assert frame.state == FrameReview.State.COMPLETED


@pytest.mark.django_db
def test_frame_stays_open_with_second_issue_or_rework(final_world):
    origin, final = final_world["run"], final_world["final"]
    frame = final_world["issue"].frame_review
    frame.state = FrameReview.State.AWAITING_FOLLOWUP
    frame.save(update_fields=["state"])
    _complete_final(final)

    other = Issue.objects.create(
        frame_review=frame,
        family=Issue.Family.E2,
        origin=Issue.Origin.REVIEWER,
        state=Issue.State.FIX_PENDING,
        anchor={"kind": "manual_region", "objects": []},
    )
    assert complete_scope_frames(origin.pk) == 0
    other.state = Issue.State.RESOLVED
    other.save(update_fields=["state"])
    ReworkRequest.objects.filter(pk=final_world["verification"].rework_id).update(
        status=ReworkRequest.Status.REOPENED
    )
    assert complete_scope_frames(origin.pk) == 0
    ReworkRequest.objects.filter(pk=final_world["verification"].rework_id).update(
        status=ReworkRequest.Status.RESOLVED
    )
    assert complete_scope_frames(origin.pk) == 1


@pytest.mark.django_db
def test_unreviewed_candidate_prevents_frame_completion(final_world):
    origin, final = final_world["run"], final_world["final"]
    frame = final_world["issue"].frame_review
    frame.state = FrameReview.State.AWAITING_FOLLOWUP
    frame.save(update_fields=["state"])
    _complete_final(final)
    _candidate(final, "late-candidate")
    assert complete_scope_frames(origin.pk) == 0
    frame.refresh_from_db()
    assert frame.state == FrameReview.State.AWAITING_FOLLOWUP


@pytest.mark.django_db
def test_sweeper_completes_frames_after_valid_final(final_world, settings):
    settings.FINAL_RUN_AUTO_DISPATCH = False
    frame = final_world["issue"].frame_review
    frame.state = FrameReview.State.AWAITING_FOLLOWUP
    frame.save(update_fields=["state"])
    _complete_final(final_world["final"])
    sweep_ready_final_runs()
    frame.refresh_from_db()
    assert frame.state == FrameReview.State.COMPLETED


@pytest.mark.django_db
def test_run_lineage_fields_for_origin_recheck_and_final(final_world):
    origin, final = final_world["run"], final_world["final"]
    verification = final_world["verification"]
    recheck = verification.recheck_run

    assert run_lineage_fields(origin)["verification_lineage"] == []
    assert run_lineage_fields(origin)["operational_source"]["run_id"] == origin.pk
    recheck_lineage = run_lineage_fields(recheck)["verification_lineage"]
    assert [row["verification_id"] for row in recheck_lineage] == [verification.pk]
    assert run_lineage_fields(recheck)["selected_final_sources"] == []

    before = run_lineage_fields(final)
    assert before["selected_final_sources"] == []  # final not Completed yet
    assert before["operational_source"]["reason"] == "no_valid_final"

    _complete_final(final)
    fields = run_lineage_fields(final)
    assert fields["verification_lineage"][0]["rework_id"] == verification.rework_id
    assert fields["selected_final_sources"] == [
        {
            "cvat_job_id": 100,
            "rework_id": verification.rework_id,
            "verification_id": verification.pk,
            "source_run_id": recheck.pk,
            "source_revision": verification.revision,
        }
    ]
    source = fields["operational_source"]
    assert source["run_id"] == final.pk and source["run_kind"] == "final"
    assert source["reason"] == "selected_final" and source["coverage"]["complete"] is True
