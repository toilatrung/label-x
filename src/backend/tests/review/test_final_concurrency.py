"""M03-R07 AC: concurrent triggers have one valid effect; final states keep the source safe.

Real PostgreSQL threads and synthetic DB rows (no CVAT); not real-data evidence.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from django.db import connections, transaction
from django.utils import timezone

from orchestration.models import LedgerUnit
from review import finalization_service
from review.finalization_service import (
    complete_scope_frames,
    operational_run,
    route_new_candidates,
)
from review.lineage import run_lineage_fields
from review.models import FrameReview, Issue
from review.tasks import complete_scope_frames_sweep
from runs.models import EngineResult, QCRun
from runs.services import InvalidTransitionError, cancel_qc_run
from tests.review.test_final_source_guard import _candidate, _complete_final

pytest_plugins = ["tests.review.test_queue_lease", "tests.review.test_final_source_guard"]

THREADS = 4
GATE_TIMEOUT = 2.0


@pytest.fixture
def widen_race_window(monkeypatch):
    """Hold every completer between its read of the frame and its write (0.4 s).

    Only used by tests whose racers are all completers: without the pause the critical
    section is microseconds long and unlocked code can pass by luck.
    """
    real = finalization_service._frame_may_complete

    def slow(frame):
        result = real(frame)
        time.sleep(0.4)
        return result

    monkeypatch.setattr(finalization_service, "_frame_may_complete", slow)


@pytest.fixture
def completer_gate(monkeypatch):
    """Force the dangerous order: a writer may act AFTER the completer passed its check.

    The completer pauses right after ``_frame_may_complete`` returns (it already decided the
    frame may complete) until the writer reports it is done, or GATE_TIMEOUT elapses. With
    correct row locks the writer is blocked behind the completer, so the wait simply times out
    and completion happens first; without locks the writer commits inside the pause.
    """
    gate = type("Gate", (), {"passed_check": Event(), "writer_done": Event()})()
    real = finalization_service._frame_may_complete

    def gated(frame):
        result = real(frame)
        gate.passed_check.set()
        gate.writer_done.wait(timeout=GATE_TIMEOUT)
        return result

    monkeypatch.setattr(finalization_service, "_frame_may_complete", gated)
    return gate


def _race(fn, n: int = THREADS) -> list:
    """Run ``fn(index)`` in ``n`` threads released together; re-raise any worker error."""
    barrier = Barrier(n)

    def worker(index: int):
        connections.close_all()
        try:
            barrier.wait(timeout=20)
            return fn(index)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=n) as pool:
        return [future.result(timeout=60) for future in [pool.submit(worker, i) for i in range(n)]]


def _awaiting(final_world) -> FrameReview:
    frame = final_world["issue"].frame_review
    frame.state = FrameReview.State.AWAITING_FOLLOWUP
    frame.save(update_fields=["state"])
    return frame


@pytest.mark.django_db(transaction=True)
def test_parallel_complete_scope_frames_has_one_effect(final_world, widen_race_window):
    origin_id = final_world["run"].pk
    frame = _awaiting(final_world)
    _complete_final(final_world["final"])

    changed = _race(lambda _i: complete_scope_frames(origin_id))

    assert sum(changed) == 1  # exactly one thread changed the frame
    frame.refresh_from_db()
    assert frame.state == FrameReview.State.COMPLETED
    assert complete_scope_frames(origin_id) == 0


@pytest.mark.django_db(transaction=True)
def test_parallel_sweeper_routes_one_issue_without_error(final_world, widen_race_window):
    origin = final_world["run"]
    final = final_world["final"]
    frame = _awaiting(final_world)
    _complete_final(final)
    new = _candidate(final, "sweeper-race")

    _race(lambda _i: complete_scope_frames_sweep())

    assert Issue.objects.filter(candidate=new).count() == 1
    assert FrameReview.objects.filter(run=final).count() == 1
    assert operational_run(origin).pk == origin.pk  # routed, undecided: source not final
    frame.refresh_from_db()
    assert frame.state == FrameReview.State.AWAITING_FOLLOWUP


@pytest.mark.django_db(transaction=True)
def test_parallel_route_new_candidates_is_idempotent_under_row_locks(final_world):
    """Direct callers must wrap the call in a transaction, as the sweeper path does."""
    origin, final = final_world["run"], final_world["final"]
    _complete_final(final)
    new = _candidate(final, "direct-race")

    def route(_i: int) -> int:
        with transaction.atomic():
            return route_new_candidates(origin, final)

    created = _race(route)
    assert sum(created) == 1  # unique(candidate) + get_or_create: one winner, no 500
    assert Issue.objects.filter(candidate=new).count() == 1


def _open_issue(frame: FrameReview) -> None:
    Issue.objects.create(
        frame_review=frame,
        family=Issue.Family.E2,
        origin=Issue.Origin.REVIEWER,
        state=Issue.State.PENDING_REVIEW,
        anchor={"kind": "manual_region", "objects": []},
    )


def _race_writer_against_completion(final_world, completer_gate, lock_in_writer):
    """Run one completer and one issue writer; return (final frame state, state writer saw).

    ``lock_in_writer(frame_id, origin_id)`` is the lock the writer takes before it looks at
    the frame, i.e. the lock protocol under test. The writer starts only after the completer
    has passed ``_frame_may_complete``.
    """
    origin_id = final_world["run"].pk
    frame = _awaiting(final_world)
    _complete_final(final_world["final"])
    seen: dict[str, str] = {}

    def completer_or_writer(index: int):
        if index == 0:
            return complete_scope_frames(origin_id)
        assert completer_gate.passed_check.wait(timeout=20)
        with transaction.atomic():
            lock_in_writer(frame.pk, origin_id)
            current = FrameReview.objects.get(pk=frame.pk)
            seen["state"] = current.state
            _open_issue(current)
        completer_gate.writer_done.set()
        return None

    _race(completer_or_writer, n=2)
    frame.refresh_from_db()
    return frame.state, seen["state"]


def _lock_run_only(_frame_id: int, origin_id: int) -> None:
    QCRun.objects.select_for_update().get(pk=origin_id)  # the issue writers' lock protocol


def _lock_frame_only(frame_id: int, _origin_id: int) -> None:
    FrameReview.objects.select_for_update().get(pk=frame_id)  # a writer that skips the run lock


@pytest.mark.django_db(transaction=True)
def test_issue_writer_taking_the_run_lock_cannot_slip_in_after_the_completion_check(
    final_world, completer_gate
):
    """Needs the ORIGIN RUN lock in complete_scope_frames (a frame-only lock does not stop it)."""
    state, writer_saw = _race_writer_against_completion(final_world, completer_gate, _lock_run_only)
    # Never: the writer saw the frame still open (its issue committed after the completer's
    # check) and the frame was completed anyway.
    assert not (state == FrameReview.State.COMPLETED and writer_saw != FrameReview.State.COMPLETED)
    assert writer_saw == FrameReview.State.COMPLETED  # locks serialise: completion went first


@pytest.mark.django_db(transaction=True)
def test_issue_writer_taking_only_the_frame_lock_cannot_slip_in_after_the_check(
    final_world, completer_gate
):
    """Needs the FRAME row lock in complete_scope_frames (defence in depth: no production
    writer skips the run lock, but one that locks only the frame row must still be safe)."""
    state, writer_saw = _race_writer_against_completion(
        final_world, completer_gate, _lock_frame_only
    )
    assert not (state == FrameReview.State.COMPLETED and writer_saw != FrameReview.State.COMPLETED)
    assert writer_saw == FrameReview.State.COMPLETED


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("terminal", "reason"),
    [
        (QCRun.Status.PARTIAL, "final_run_partial"),
        (QCRun.Status.FAILED, "final_run_failed"),
        (QCRun.Status.CANCELLED, "final_run_cancelled"),
    ],
)
def test_non_completed_final_keeps_origin_and_does_not_route_or_complete(
    final_world, terminal, reason
):
    origin, final = final_world["run"], final_world["final"]
    frame = _awaiting(final_world)
    _complete_final(final)
    _candidate(final, "late-new-candidate")
    final.status = terminal
    final.save(update_fields=["status"])

    assert complete_scope_frames(origin.pk) == 0

    source = run_lineage_fields(origin)["operational_source"]
    assert source["run_id"] == origin.pk
    assert source["scope_complete"] is False
    assert source["blocked_reasons"] == [reason]
    assert not Issue.objects.filter(candidate__dedup_key="late-new-candidate").exists()
    frame.refresh_from_db()
    assert frame.state == FrameReview.State.AWAITING_FOLLOWUP


def _break_ledger(final: QCRun, gap: str) -> None:
    result = final.engine_results.get(engine="geometry")
    if gap == "failed_unit":
        result.failed_units, result.completed_units = 1, 0
        result.save(update_fields=["failed_units", "completed_units"])
    elif gap == "pending_ledger":
        LedgerUnit.objects.filter(run=final).update(outcome="pending")
    elif gap == "not_checked":
        result.status = "not_checked"
        result.save(update_fields=["status"])
    else:
        final.engine_results.all().delete()


LEDGER_GAPS = ["failed_unit", "pending_ledger", "not_checked", "no_engine_row"]


@pytest.mark.django_db
@pytest.mark.parametrize("gap", LEDGER_GAPS)
def test_incomplete_ledger_blocks_source_and_completion(final_world, gap):
    origin, final = final_world["run"], final_world["final"]
    frame = _awaiting(final_world)
    _complete_final(final)
    _break_ledger(final, gap)

    assert complete_scope_frames(origin.pk) == 0

    source = run_lineage_fields(origin)["operational_source"]
    assert source["run_id"] == origin.pk and source["scope_complete"] is False
    assert source["blocked_reasons"] == ["coverage_incomplete"]
    frame.refresh_from_db()
    assert frame.state == FrameReview.State.AWAITING_FOLLOWUP


@pytest.mark.django_db
@pytest.mark.parametrize("gap", LEDGER_GAPS)
def test_new_candidate_is_not_routed_from_an_incomplete_ledger(final_world, gap):
    """Invariants only. KNOWN LIMIT (awaiting PO decision): ``blocked_reasons`` reports a single
    reason per final attempt, so with both a new candidate and a ledger gap only one is listed;
    this test deliberately does not pin which one."""
    origin, final = final_world["run"], final_world["final"]
    frame = _awaiting(final_world)
    _complete_final(final)
    new = _candidate(final, f"gap-{gap}")
    _break_ledger(final, gap)

    assert complete_scope_frames(origin.pk) == 0

    assert not Issue.objects.filter(candidate=new).exists()
    source = run_lineage_fields(origin)["operational_source"]
    assert source["run_id"] == origin.pk and source["scope_complete"] is False
    assert source["blocked_reasons"]  # blocked, whatever the first reason is
    frame.refresh_from_db()
    assert frame.state == FrameReview.State.AWAITING_FOLLOWUP


@pytest.mark.django_db
def test_failed_attempt_then_valid_retry_selects_only_the_valid_final(final_world):
    origin, failed = final_world["run"], final_world["final"]
    _complete_final(failed)
    failed.status, failed.finished_at = QCRun.Status.FAILED, timezone.now()
    failed.save(update_fields=["status", "finished_at"])
    retry = QCRun.objects.create(
        snapshot=failed.snapshot,
        config_version=failed.config_version,
        seed=failed.seed,
        dataset_id=failed.dataset_id,
        scope_hash=failed.scope_hash,
        created_by=failed.created_by,
        origin_run=origin,
        is_final=True,
        idempotency_key=f"{failed.idempotency_key}-retry",
    )
    _complete_final(retry)

    source = run_lineage_fields(origin)["operational_source"]
    assert source["run_id"] == retry.pk and source["scope_complete"] is True
    assert {a["run_id"]: a["reason"] for a in source["final_attempts"]} == {
        failed.pk: "final_run_failed",
        retry.pk: "selected",
    }
    assert EngineResult.objects.filter(
        run=failed, status="checked"
    ).exists()  # original evidence intact


@pytest.mark.django_db
def test_completed_final_cannot_be_cancelled_and_sweep_still_completes(final_world):
    """Production rule (runs.services.cancel_qc_run): terminal runs reject cancellation."""
    origin, final = final_world["run"], final_world["final"]
    frame = _awaiting(final_world)
    _complete_final(final)

    with pytest.raises(InvalidTransitionError):
        cancel_qc_run(run_id=final.pk, actor=final_world["other"])

    final.refresh_from_db()
    assert final.status == QCRun.Status.COMPLETED
    assert complete_scope_frames(origin.pk) == 1
    frame.refresh_from_db()
    assert frame.state == FrameReview.State.COMPLETED
    assert operational_run(origin).pk == final.pk


@pytest.mark.django_db(transaction=True)
def test_cancelling_a_retry_attempt_while_sweeping_keeps_the_valid_final(
    final_world, widen_race_window
):
    """Attempt 1 is a valid Completed final; attempt 2 (retry) is running and gets cancelled
    through the real service while sweepers run. Source and frame outcome must be stable."""
    origin, valid = final_world["run"], final_world["final"]
    frame = _awaiting(final_world)
    _complete_final(valid)
    retry = QCRun.objects.create(
        snapshot=valid.snapshot,
        config_version=valid.config_version,
        seed=valid.seed,
        dataset_id=valid.dataset_id,
        scope_hash=valid.scope_hash,
        created_by=valid.created_by,
        origin_run=origin,
        is_final=True,
        status=QCRun.Status.RUNNING,
        idempotency_key=f"{valid.idempotency_key}-retry",
    )
    actor = final_world["other"]

    def cancel_or_sweep(index: int):
        if index == 0:
            return cancel_qc_run(run_id=retry.pk, actor=actor).status
        return complete_scope_frames(origin.pk)

    results = _race(cancel_or_sweep, n=3)

    assert results[0] == QCRun.Status.CANCELLED
    assert sorted(results[1:]) == [0, 1]  # exactly one sweeper completed the frame
    retry.refresh_from_db()
    frame.refresh_from_db()
    assert retry.status == QCRun.Status.CANCELLED
    assert frame.state == FrameReview.State.COMPLETED
    assert operational_run(origin).pk == valid.pk
