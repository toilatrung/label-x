"""#238: a frame enters awaiting_followup only when nothing is left to decide.

Everything goes through the real API/services (claim, decide, rework, verify, complete).
Synthetic fixtures only: no CVAT export, not real-data E2E evidence.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from types import SimpleNamespace

import pytest
from django.core.files.storage import storages
from django.db import connection, connections
from django.utils import timezone

from audit.models import AuditEvent
from review import finalization_service, issue_service, rework_service
from review.finalization_service import build_final_run, complete_scope_frames
from review.models import FrameReview, Issue, Lease, ReworkRequest
from tests.review.test_final_source_guard import _complete_final
from tests.review.test_issues_decisions import claim, decide, manual
from tests.review.test_queue_lease import client, next_url
from tests.review.test_rework import (  # noqa: F401
    _run_for,
    _submit,
    _verify,
    changed_snapshot,
    create_request,
    cvat_base_url,
    second_snapshot,
)

pytest_plugins = ["tests.review.test_queue_lease"]


@pytest.fixture(autouse=True)
def storage_url(monkeypatch):
    monkeypatch.setattr(storages["snapshots"], "url", lambda name: f"https://storage.test/{name}")


@pytest.fixture(autouse=True)
def approved_test_policy(settings):
    settings.REVIEW_LEASE_TTL_SECONDS = 60
    settings.REVIEW_INCOMPLETE_RESERVATION_SECONDS = 120


def _complete(world, lease_id, frame_id):
    return client(world["reviewer"]).post(
        f"/api/frames/{frame_id}/complete/", {"lease_id": lease_id}, format="json"
    )


def _confirmed_issue(world, lease_id, frame_id):
    issue_id, _ = manual(world, lease_id, frame_id)
    assert decide(world, lease_id, issue_id).status_code in (200, 201)
    return issue_id


def _rework(world, issue_id):
    response = create_request(SimpleNamespace(pk=issue_id), world)
    assert response.status_code == 201, response.data
    return ReworkRequest.objects.get(pk=response.data["id"])


def _stub_recheck(monkeypatch, world, snapshots):
    """Each submit consumes the next (snapshot, completed run) pair."""

    pairs = [(snapshot, _run_for(world, snapshot)) for snapshot in snapshots]

    def build(**_kwargs):
        return pairs.pop(0)

    monkeypatch.setattr(rework_service, "_build_recheck_artifacts", build)


def _frame(frame_id):
    return FrameReview.objects.get(pk=frame_id)


def _verified(world, rework, snapshot):
    assert _submit(world, rework, snapshot).status_code == 202
    assert _verify(world, rework, snapshot, True).status_code == 200


@pytest.mark.django_db
def test_undecided_issue_flow_to_scope_completion(world, monkeypatch):
    """(a) verify arrives while B is undecided -> expiry -> resume -> decide B -> complete."""

    lease_id, frame_id = claim(world)
    issue_a = _confirmed_issue(world, lease_id, frame_id)
    rework = _rework(world, issue_a)
    issue_b, _ = manual(world, lease_id, frame_id)
    snapshot = changed_snapshot(world)
    _stub_recheck(monkeypatch, world, [snapshot])

    _verified(world, rework, snapshot)
    rework.refresh_from_db()
    assert rework.status == ReworkRequest.Status.RESOLVED
    assert _frame(frame_id).state == FrameReview.State.IN_REVIEW  # reviewer still has B
    assert Lease.objects.get(pk=lease_id).closed_at is None

    Lease.objects.filter(pk=lease_id).update(expires_at=timezone.now() - timedelta(seconds=1))
    resumed = client(world["reviewer"]).post(next_url(), {"run_id": world["run"].pk}, format="json")
    assert resumed.status_code == 200 and resumed.data["resumed"] is True
    new_lease = resumed.data["lease"]["id"]
    assert new_lease != lease_id
    assert Issue.objects.get(pk=issue_b).state == Issue.State.IN_REVIEW

    assert decide(world, new_lease, issue_b, action="reject").status_code in (200, 201)
    done = _complete(world, new_lease, frame_id)
    assert done.status_code == 200, done.data
    assert _frame(frame_id).state == FrameReview.State.AWAITING_FOLLOWUP

    monkeypatch.setattr(
        finalization_service, "create_snapshot_from_cvat", lambda **_kwargs: snapshot
    )
    final, _ = build_final_run(origin_run_id=world["run"].pk, actor=world["other"])
    _complete_final(final)
    assert complete_scope_frames(world["run"].pk) == 1
    assert _frame(frame_id).state == FrameReview.State.COMPLETED


@pytest.mark.django_db
def test_everything_decided_then_verify_hands_over_without_complete(world, monkeypatch):
    """(b) reviewer has not pressed complete, nothing undecided: verify hands the frame over."""

    lease_id, frame_id = claim(world)
    rework = _rework(world, _confirmed_issue(world, lease_id, frame_id))
    snapshot = changed_snapshot(world)
    _stub_recheck(monkeypatch, world, [snapshot])

    _verified(world, rework, snapshot)

    assert _frame(frame_id).state == FrameReview.State.AWAITING_FOLLOWUP
    assert Lease.objects.get(pk=lease_id).closed_at is not None


@pytest.mark.django_db
def test_complete_hands_over_only_when_every_rework_is_resolved(world, monkeypatch):
    """(d) two reworks: complete keeps REVIEWED until the last one is resolved."""

    lease_id, frame_id = claim(world)
    rework_a = _rework(world, _confirmed_issue(world, lease_id, frame_id))
    rework_c = _rework(world, _confirmed_issue(world, lease_id, frame_id))
    issue_d, _ = manual(world, lease_id, frame_id)
    first, second = changed_snapshot(world), second_snapshot(world)
    _stub_recheck(monkeypatch, world, [first, second])

    _verified(world, rework_a, first)  # D is still undecided: frame stays in_review
    assert _frame(frame_id).state == FrameReview.State.IN_REVIEW
    assert decide(world, lease_id, issue_d, action="reject").status_code in (200, 201)

    assert _complete(world, lease_id, frame_id).status_code == 200
    assert _frame(frame_id).state == FrameReview.State.REVIEWED  # rework_c still open

    _verified(world, rework_c, second)
    assert _frame(frame_id).state == FrameReview.State.AWAITING_FOLLOWUP


@pytest.mark.django_db
def test_repeated_complete_is_idempotent_after_handover(world, monkeypatch):
    """(f) frames/complete twice: second call is a no-op (no second audit, same state)."""

    lease_id, frame_id = claim(world)
    rework = _rework(world, _confirmed_issue(world, lease_id, frame_id))
    issue_b, _ = manual(world, lease_id, frame_id)
    snapshot = changed_snapshot(world)
    _stub_recheck(monkeypatch, world, [snapshot])
    _verified(world, rework, snapshot)
    assert decide(world, lease_id, issue_b, action="reject").status_code in (200, 201)

    first = _complete(world, lease_id, frame_id)
    assert first.status_code == 200
    assert _frame(frame_id).state == FrameReview.State.AWAITING_FOLLOWUP
    audits = AuditEvent.objects.filter(action="frame.complete", object_id=str(frame_id)).count()

    again = _complete(world, lease_id, frame_id)
    assert again.status_code == 200
    assert _frame(frame_id).state == FrameReview.State.AWAITING_FOLLOWUP
    assert audits == 1
    assert AuditEvent.objects.filter(action="frame.complete", object_id=str(frame_id)).count() == 1


@pytest.mark.django_db
def test_complete_without_rework_stays_reviewed(world):
    lease_id, frame_id = claim(world)
    _confirmed_issue(world, lease_id, frame_id)
    assert _complete(world, lease_id, frame_id).status_code == 200
    assert _frame(frame_id).state == FrameReview.State.REVIEWED
    assert _complete(world, lease_id, frame_id).status_code == 200  # idempotent as before


def _verify_in_thread(world, rework_id, snapshot):
    connections.close_all()
    try:
        return _verify(world, type("R", (), {"pk": rework_id}), snapshot, True)
    finally:
        connections.close_all()


def _complete_in_thread(world, lease_id, frame_id):
    connections.close_all()
    try:
        return _complete(world, lease_id, frame_id)
    finally:
        connections.close_all()


def _race_setup(world, monkeypatch):
    lease_id, frame_id = claim(world)
    rework = _rework(world, _confirmed_issue(world, lease_id, frame_id))
    snapshot = changed_snapshot(world)
    _stub_recheck(monkeypatch, world, [snapshot])
    assert _submit(world, rework, snapshot).status_code == 202
    return lease_id, frame_id, rework, snapshot


@pytest.mark.django_db(transaction=True)
def test_postgres_race_complete_holds_lock_first_then_verify(world, monkeypatch):
    """(e) order 1: frames/complete owns the run lock; verify waits and then wins the frame."""

    assert connection.vendor == "postgresql"
    lease_id, frame_id, rework, snapshot = _race_setup(world, monkeypatch)
    inside, release = Event(), Event()
    real_audit = issue_service.append_audit_event

    def paused_audit(**kwargs):
        event = real_audit(**kwargs)
        inside.set()
        assert release.wait(timeout=15)
        return event

    monkeypatch.setattr(issue_service, "append_audit_event", paused_audit)
    verify_done = Event()

    def verify_side():
        result = _verify_in_thread(world, rework.pk, snapshot)
        verify_done.set()
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        completer = pool.submit(_complete_in_thread, world, lease_id, frame_id)
        assert inside.wait(timeout=15)
        verifier = pool.submit(verify_side)
        verify_blocked = not verify_done.wait(timeout=1.0)
        release.set()
        completed = completer.result(timeout=30)
        verified = verifier.result(timeout=30)
    assert verify_blocked
    assert completed.status_code == 200 and verified.status_code == 200
    assert ReworkRequest.objects.get(pk=rework.pk).status == ReworkRequest.Status.RESOLVED
    assert _frame(frame_id).state == FrameReview.State.AWAITING_FOLLOWUP
    assert Lease.objects.get(pk=lease_id).closed_at is not None


@pytest.mark.django_db(transaction=True)
def test_postgres_race_verify_holds_lock_first_then_complete(world, monkeypatch):
    """(e) order 2: verify owns the run lock and hands the frame over; complete is refused."""

    assert connection.vendor == "postgresql"
    lease_id, frame_id, rework, snapshot = _race_setup(world, monkeypatch)
    inside, release = Event(), Event()
    real_audit = rework_service.append_audit_event
    first_call = []

    def paused_audit(**kwargs):
        event = real_audit(**kwargs)
        if not first_call:
            first_call.append(True)
            inside.set()
            assert release.wait(timeout=15)
        return event

    monkeypatch.setattr(rework_service, "append_audit_event", paused_audit)
    complete_done = Event()

    def complete_side():
        result = _complete_in_thread(world, lease_id, frame_id)
        complete_done.set()
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        verifier = pool.submit(_verify_in_thread, world, rework.pk, snapshot)
        assert inside.wait(timeout=15)
        completer = pool.submit(complete_side)
        complete_blocked = not complete_done.wait(timeout=1.0)
        release.set()
        verified = verifier.result(timeout=30)
        completed = completer.result(timeout=30)
    assert complete_blocked
    assert verified.status_code == 200
    assert completed.status_code == 409  # lease was closed by the hand-over
    assert ReworkRequest.objects.get(pk=rework.pk).status == ReworkRequest.Status.RESOLVED
    assert _frame(frame_id).state == FrameReview.State.AWAITING_FOLLOWUP
    assert Lease.objects.get(pk=lease_id).closed_at is not None


@pytest.mark.django_db
def test_escalated_issue_is_not_undecided_but_keeps_the_scope_open(world, monkeypatch):
    """Escalated issues wait for a case, not for the reviewer: they never block hand-over."""

    lease_id, frame_id = claim(world)
    rework = _rework(world, _confirmed_issue(world, lease_id, frame_id))
    escalated = Issue.objects.create(
        frame_review=_frame(frame_id),
        family=Issue.Family.E2,
        origin=Issue.Origin.REVIEWER,
        state=Issue.State.ESCALATED,
        anchor={"kind": "manual_region", "objects": []},
    )
    snapshot = changed_snapshot(world)
    _stub_recheck(monkeypatch, world, [snapshot])

    _verified(world, rework, snapshot)

    assert _frame(frame_id).state == FrameReview.State.AWAITING_FOLLOWUP
    assert Lease.objects.get(pk=lease_id).closed_at is not None
    escalated.refresh_from_db()
    assert escalated.state == Issue.State.ESCALATED
    # an escalated issue is still open: the scope does not complete around it
    monkeypatch.setattr(
        finalization_service, "create_snapshot_from_cvat", lambda **_kwargs: snapshot
    )
    with pytest.raises(finalization_service.FinalRunNotReady):
        build_final_run(origin_run_id=world["run"].pk, actor=world["other"])
    assert complete_scope_frames(world["run"].pk) == 0
    assert _frame(frame_id).state == FrameReview.State.AWAITING_FOLLOWUP


@pytest.mark.django_db
def test_complete_frame_with_escalated_issue_is_not_blocked(world):
    lease_id, frame_id = claim(world)
    _confirmed_issue(world, lease_id, frame_id)
    Issue.objects.create(
        frame_review=_frame(frame_id),
        family=Issue.Family.E2,
        origin=Issue.Origin.REVIEWER,
        state=Issue.State.ESCALATED,
        anchor={"kind": "manual_region", "objects": []},
    )
    done = _complete(world, lease_id, frame_id)
    assert done.status_code == 200, done.data  # not 422 undecided_issue_ids
    assert _frame(frame_id).state == FrameReview.State.REVIEWED
