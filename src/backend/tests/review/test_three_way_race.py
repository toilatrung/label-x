"""Three-way race: frames/complete vs rework verify vs complete_scope_frames (#238/#243 limit).

Real PostgreSQL threads over synthetic DB rows (no CVAT, no Celery); not real-data evidence.

Scenario: a Completed final run exists and a reviewer re-opens a frame under a live lease,
is routed back to the queue, a reviewer claims the frame, confirms the new issue and sends a
rework that the annotator has submitted. Three writers can now meet on the same frame while the
origin QCRun row lock serialises them: ``complete_frame`` (reviewer), ``verify_rework``
(verifier) and ``complete_scope_frames`` (sweeper / final-scope path).

Invariants asserted for every arrival order and under repeated 4+4+4 racing:
  * a frame is never COMPLETED while an issue is undecided or a rework is unresolved;
  * no audit event is lost or duplicated (one verify audit, one verification row, at most one
    ``frame.complete`` audit);
  * nobody deadlocks (every wait has a timeout) and the end state is consistent.
"""

from __future__ import annotations

import itertools
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event, Lock
from types import SimpleNamespace

import pytest
from django.db import connection, connections, transaction
from django.utils import timezone

from audit.models import AuditEvent
from audit.services import append_audit_event
from review import finalization_service, issue_service, rework_service
from review.finalization_service import complete_scope_frames
from review.models import FrameReview, Issue, Lease, ReviewDecision, ReworkRequest, ReworkVerification
from tests.review.test_final_source_guard import _complete_final, final_world  # noqa: F401
from tests.review.test_frame_followup_flow import (  # noqa: F401
    _complete,
    _completion_audits,
    _frame,
    _rework,
    _stub_recheck,
    approved_test_policy,
    storage_url,
)
from tests.review.test_issues_decisions import decide, manual
from tests.review.test_rework import _submit, _verify, changed_snapshot, second_snapshot  # noqa: F401

pytest_plugins = ["tests.review.test_queue_lease", "tests.review.test_final_source_guard"]

WAIT = 30
KINDS = ("complete", "verify", "sweep")
ORDERS = list(itertools.permutations(KINDS))


@pytest.fixture(autouse=True)
def no_auto_dispatch(settings):
    settings.FINAL_RUN_AUTO_DISPATCH = False  # a passing verify must not publish to a broker


def _record_decision(issue, actor):
    """The scope fixture resolves its issue directly; give it the committed human decision."""

    with transaction.atomic():
        audit = append_audit_event(
            actor=actor,
            action="issue.decide",
            object_type="issue",
            object_id=issue.pk,
            before=None,
            after={"state": issue.state},
            revision="r" * 64,
            reason="fixture decision",
        )
        ReviewDecision.objects.create(
            issue=issue,
            actor=actor,
            actor_role="reviewer",
            action=ReviewDecision.Action.CONFIRM,
            revision="r" * 64,
            audit_event=audit,
        )


@pytest.fixture
def race_world(final_world, monkeypatch):  # noqa: F811
    """Reopened frame: lease held, new issue confirmed, rework submitted, awaiting verify."""

    world = final_world
    origin, final = world["run"], world["final"]
    _complete_final(final)
    # The reviewer re-opens the frame after the final run completed (frame held under a live
    # lease, as for a sibling frame that was still in review when the final run was built).
    frame = world["issue"].frame_review
    frame.state = FrameReview.State.IN_REVIEW
    frame.save(update_fields=["state"])
    lease = Lease.objects.create(
        frame_review=frame,
        holder=world["reviewer"],
        queue_source="risk",
        expires_at=timezone.now() + timedelta(hours=1),
    )
    lease_id, frame_id = lease.pk, frame.pk
    _record_decision(world["issue"], world["reviewer"])  # the fixture's issue is resolved
    new_issue_id, _ = manual(world, lease_id, frame_id)
    assert decide(world, lease_id, new_issue_id).status_code in (200, 201)
    rework = _rework(world, new_issue_id)
    snapshot = second_snapshot(world)
    _stub_recheck(monkeypatch, world, [snapshot])
    assert _submit(world, rework, snapshot).status_code == 202
    return SimpleNamespace(
        world=world,
        origin_id=origin.pk,
        lease_id=lease_id,
        frame_id=frame_id,
        rework=rework,
        snapshot=snapshot,
    )


# ---------------------------------------------------------------- racers (one DB connection each)


def _thread(fn):
    connections.close_all()
    try:
        return fn()
    finally:
        connections.close_all()


def _do_complete(rw):
    return _thread(lambda: _complete(rw.world, rw.lease_id, rw.frame_id).status_code)


def _do_verify(rw, passed):
    return _thread(lambda: _verify(rw.world, rw.rework, rw.snapshot, passed).status_code)


def _do_sweep(rw):
    return _thread(lambda: complete_scope_frames(rw.origin_id))


def _racer(rw, kind, passed):
    return {
        "complete": lambda: _do_complete(rw),
        "verify": lambda: _do_verify(rw, passed),
        "sweep": lambda: _do_sweep(rw),
    }[kind]


def _lock_waiters() -> int:
    """Backends of this database currently blocked on a lock (the queue behind the holder)."""

    with connections["default"].cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = current_database() AND wait_event_type = 'Lock'"
        )
        return cursor.fetchone()[0]


def _wait_for_waiters(count: int) -> None:
    deadline = time.monotonic() + WAIT
    while _lock_waiters() < count:
        assert time.monotonic() < deadline, f"timeout: expected {count} lock waiters"
        time.sleep(0.02)


@pytest.fixture
def holder_pause(monkeypatch):
    """Pause whichever racer is told to be first, right after it took the origin run lock.

    complete -> after its first audit write; verify -> after its first audit write;
    sweep -> after select_operational_source. Only the armed kind pauses (once).
    """

    state = SimpleNamespace(kind=None, inside=Event(), release=Event(), fired=False)

    def pause(kind):
        if state.kind == kind and not state.fired:
            state.fired = True
            state.inside.set()
            assert state.release.wait(timeout=WAIT)

    real_issue_audit = issue_service.append_audit_event
    real_rework_audit = rework_service.append_audit_event
    real_select = finalization_service.select_operational_source

    def issue_audit(**kwargs):
        event = real_issue_audit(**kwargs)
        if kwargs.get("action") == "frame.complete":
            pause("complete")
        return event

    def rework_audit(**kwargs):
        event = real_rework_audit(**kwargs)
        if str(kwargs.get("action", "")).startswith("rework.verify_"):
            pause("verify")
        return event

    def select(origin_run):
        result = real_select(origin_run)
        pause("sweep")
        return result

    monkeypatch.setattr(issue_service, "append_audit_event", issue_audit)
    monkeypatch.setattr(rework_service, "append_audit_event", rework_audit)
    monkeypatch.setattr(finalization_service, "select_operational_source", select)
    return state


# ---------------------------------------------------------------- invariant checks


def _assert_invariants(rw, results, *, passed):
    frame = _frame(rw.frame_id)
    rework = ReworkRequest.objects.get(pk=rw.rework.pk)
    issue = Issue.objects.get(pk=rework.issue_id)
    # 1. never COMPLETED while an issue/rework is unresolved
    if frame.state == FrameReview.State.COMPLETED:
        assert rework.status == ReworkRequest.Status.RESOLVED
        assert not frame.issues.exclude(
            state__in=(Issue.State.REJECTED, Issue.State.RESOLVED)
        ).exists()
        assert passed
    if not passed:
        assert frame.state != FrameReview.State.COMPLETED
        assert issue.state == Issue.State.FIX_PENDING
    else:
        assert rework.status == ReworkRequest.Status.RESOLVED
        assert issue.state == Issue.State.RESOLVED
    # 2. audit / verification rows: exactly one verify, no duplicated completion
    outcome = "pass" if passed else "fail"
    assert AuditEvent.objects.filter(
        action=f"rework.verify_{outcome}", object_id=str(rework.pk)
    ).count() == 1
    assert ReworkVerification.objects.filter(rework=rework).count() == 1
    assert _completion_audits(rw.frame_id) <= 1
    if results["complete"] == 200:
        assert _completion_audits(rw.frame_id) == 1
    assert results["verify"] == 200
    # 3. consistent end state: a settling sweep never contradicts the invariants
    complete_scope_frames(rw.origin_id)
    after = _frame(rw.frame_id)
    if passed and after.state == FrameReview.State.AWAITING_FOLLOWUP:
        pytest.fail("a passed scope with a valid final must settle to COMPLETED after one sweep")
    assert complete_scope_frames(rw.origin_id) == 0  # idempotent


# ---------------------------------------------------------------- (1) forced arrival orders


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("passed", [True, False], ids=["verify-pass", "verify-fail"])
@pytest.mark.parametrize("order", ORDERS, ids=["-".join(o) for o in ORDERS])
def test_forced_arrival_order(race_world, holder_pause, order, passed):
    """The first racer holds the origin run lock; the other two queue behind it in the given
    order (queue depth is observed in pg_stat_activity, not assumed); then the holder goes."""

    assert connection.vendor == "postgresql"
    rw = race_world
    finished: list[str] = []
    guard = Lock()

    def run(kind):
        result = _racer(rw, kind, passed)()
        with guard:
            finished.append(kind)
        return result

    holder_pause.kind = order[0]
    results: dict[str, object] = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {order[0]: pool.submit(run, order[0])}
        assert holder_pause.inside.wait(timeout=WAIT), "first racer never took the lock"
        futures[order[1]] = pool.submit(run, order[1])
        _wait_for_waiters(1)
        futures[order[2]] = pool.submit(run, order[2])
        _wait_for_waiters(2)
        assert finished == []  # both followers are really blocked behind the holder
        holder_pause.release.set()
        for kind, future in futures.items():
            results[kind] = future.result(timeout=WAIT)  # timeout == deadlock detector
    assert finished == list(order), "lock hand-over did not follow the forced arrival order"
    _assert_invariants(rw, results, passed=passed)


# ---------------------------------------------------------------- (2) repeated 4+4+4 race

REPEATS = 6


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("passed", [True, False], ids=["verify-pass", "verify-fail"])
@pytest.mark.parametrize("repeat", range(REPEATS))
def test_repeated_four_of_each_kind(race_world, repeat, passed):
    del repeat
    rw = race_world
    barrier = Barrier(12)

    def worker(kind):
        def go():
            barrier.wait(timeout=WAIT)
            return _racer(rw, kind, passed)()

        return go

    kinds = [k for k in KINDS for _ in range(4)]
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [(k, pool.submit(worker(k))) for k in kinds]
        outcomes = [(k, f.result(timeout=WAIT * 2)) for k, f in futures]

    verify_codes = sorted(code for k, code in outcomes if k == "verify")
    assert verify_codes == [200, 409, 409, 409]  # one winner, losers are clean 409s
    complete_codes = {code for k, code in outcomes if k == "complete"}
    assert complete_codes <= {200, 409, 422}  # never a 500
    assert sum(changed for k, changed in outcomes if k == "sweep") <= 1
    results = {"complete": 200 if 200 in complete_codes else 409, "verify": 200}
    _assert_invariants(rw, results, passed=passed)
