"""M03-R07 AC: concurrent triggers have one valid effect; final states keep the source safe.

Real PostgreSQL threads and synthetic DB rows (no CVAT); not real-data evidence.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections, transaction
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
from tests.review.test_final_source_guard import _candidate, _complete_final

pytest_plugins = ["tests.review.test_queue_lease", "tests.review.test_final_source_guard"]

THREADS = 4


@pytest.fixture
def widen_race_window(monkeypatch):
    """Hold each thread between its read of the scope and its write so overlap is certain.

    Without this the critical section is microseconds long and unlocked code can pass by luck.
    """
    real = finalization_service.select_operational_source

    def slow(origin_run):
        result = real(origin_run)
        time.sleep(0.4)
        return result

    monkeypatch.setattr(finalization_service, "select_operational_source", slow)


def _race(fn, n: int = THREADS) -> list:
    """Run ``fn(index)`` in ``n`` threads released together; re-raise any worker error."""
    barrier = Barrier(n)

    def worker(index: int):
        close_old_connections()
        try:
            barrier.wait(timeout=20)
            return fn(index)
        finally:
            close_old_connections()

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


@pytest.mark.django_db(transaction=True)
def test_new_issue_racing_completion_never_completes_over_an_open_issue(
    final_world, widen_race_window
):
    """A writer that takes the run lock first must keep the frame from completing."""
    origin_id = final_world["run"].pk
    frame = _awaiting(final_world)
    _complete_final(final_world["final"])
    saw_completed_before_issue: list[bool] = []

    def writer_or_completer(index: int):
        if index == 0:
            return complete_scope_frames(origin_id)
        with transaction.atomic():
            QCRun.objects.select_for_update().get(
                pk=origin_id
            )  # same lock protocol as issue writers
            current = FrameReview.objects.get(pk=frame.pk)
            saw_completed_before_issue.append(current.state == FrameReview.State.COMPLETED)
            Issue.objects.create(
                frame_review=current,
                family=Issue.Family.E2,
                origin=Issue.Origin.REVIEWER,
                state=Issue.State.PENDING_REVIEW,
                anchor={"kind": "manual_region", "objects": []},
            )
        return None

    _race(writer_or_completer, n=2)

    frame.refresh_from_db()
    if saw_completed_before_issue == [False]:
        # Issue was committed first, so completion must have seen it and stayed out.
        assert frame.state == FrameReview.State.AWAITING_FOLLOWUP
    else:
        assert frame.state == FrameReview.State.COMPLETED  # completion legitimately ran first
    assert complete_scope_frames(origin_id) == 0  # open issue now blocks any later completion


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
    origin, final = final_world["run"], final_world["final"]
    _awaiting(final_world)
    _complete_final(final)
    new = _candidate(final, f"gap-{gap}")
    _break_ledger(final, gap)

    assert complete_scope_frames(origin.pk) == 0

    assert not Issue.objects.filter(candidate=new).exists()
    source = run_lineage_fields(origin)["operational_source"]
    assert source["run_id"] == origin.pk and source["scope_complete"] is False
    # Only the first blocking reason per attempt is reported (new candidate is checked first).
    assert source["blocked_reasons"] == ["new_candidate_unreviewed"]


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


@pytest.mark.django_db(transaction=True)
def test_cancel_racing_the_sweeper_leaves_a_consistent_source(final_world):
    origin_id, final = final_world["run"].pk, final_world["final"]
    frame = _awaiting(final_world)
    _complete_final(final)

    def cancel_or_sweep(index: int):
        if index == 0:
            QCRun.objects.filter(pk=final.pk).update(status=QCRun.Status.CANCELLED)
            return None
        return complete_scope_frames(origin_id)

    _race(cancel_or_sweep, n=2)

    frame.refresh_from_db()
    final.refresh_from_db()
    assert final.status == QCRun.Status.CANCELLED
    if frame.state == FrameReview.State.COMPLETED:
        pass  # sweep won the race while the final was still Completed: legitimate order
    else:
        assert frame.state == FrameReview.State.AWAITING_FOLLOWUP
    # whatever the order, once cancelled the origin run must be the source again
    assert operational_run(QCRun.objects.get(pk=origin_id)).pk == origin_id
