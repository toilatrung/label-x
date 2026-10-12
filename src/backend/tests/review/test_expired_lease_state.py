"""M03-R02/F1: lease expiry must not rewrite a frame that already left in_review."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from django.db import connection, connections, transaction
from django.utils import timezone

from review import rework_service, services
from review.finalization_service import complete_scope_frames
from review.models import FrameReview, Issue, Lease, ReworkRequest
from runs.models import QCRun
from tests.review.test_final_source_guard import _complete_final, final_world  # noqa: F401
from tests.review.test_issues_decisions import claim, decide, manual
from tests.review.test_queue_lease import client, next_url
from tests.review.test_rework import (  # noqa: F401
    _run_for,
    _submit,
    _verify,
    changed_snapshot,
    confirmed,
    create_request,
    cvat_base_url,
)

pytest_plugins = ["tests.review.test_queue_lease"]


@pytest.fixture(autouse=True)
def approved_test_policy(settings):
    settings.REVIEW_LEASE_TTL_SECONDS = 60
    settings.REVIEW_INCOMPLETE_RESERVATION_SECONDS = 120


def _expire(lease_id: int) -> None:
    Lease.objects.filter(pk=lease_id).update(expires_at=timezone.now() - timedelta(seconds=1))


def _claim_again(world):
    return client(world["reviewer"]).post(next_url(), {"run_id": world["run"].pk}, format="json")


@pytest.mark.django_db
def test_awaiting_followup_survives_expired_lease_and_scope_completes(final_world):  # noqa: F811
    """claim -> lease expires -> verify -> awaiting_followup -> new claim -> still awaiting."""

    world = final_world
    frame = world["issue"].frame_review
    frame.state = FrameReview.State.UNREVIEWED
    frame.save(update_fields=["state"])
    lease_id, frame_id = claim(world)
    assert frame_id == frame.pk
    _expire(lease_id)

    # rework verify_pass moves the frame on while the old lease is still open
    FrameReview.objects.filter(pk=frame.pk).update(state=FrameReview.State.AWAITING_FOLLOWUP)

    _claim_again(world)
    frame.refresh_from_db()
    assert frame.state == FrameReview.State.AWAITING_FOLLOWUP
    assert frame.previous_reviewer_id is None and frame.incomplete_since is None
    assert Lease.objects.get(pk=lease_id).closed_at is not None

    _complete_final(world["final"])
    assert complete_scope_frames(world["run"].pk) == 1
    frame.refresh_from_db()
    assert frame.state == FrameReview.State.COMPLETED


@pytest.mark.django_db
@pytest.mark.parametrize("state", [FrameReview.State.REVIEWED, FrameReview.State.COMPLETED])
def test_other_post_review_states_are_not_rewritten(world, state):
    lease_id, frame_id = claim(world)
    _expire(lease_id)
    FrameReview.objects.filter(pk=frame_id).update(state=state)
    _claim_again(world)
    assert FrameReview.objects.get(pk=frame_id).state == state
    assert Lease.objects.get(pk=lease_id).closed_at is not None


@pytest.mark.django_db
def test_in_review_expiry_without_decision_requeues_frame(world):
    lease_id, frame_id = claim(world)
    _expire(lease_id)
    response = _claim_again(world)
    assert response.status_code == 200 and response.data["frame"]["id"] == frame_id
    assert response.data["resumed"] is False
    assert Lease.objects.get(pk=lease_id).closed_at is not None


@pytest.mark.django_db
def test_in_review_expiry_with_saved_decision_is_incomplete_and_resumes(world):
    lease_id, frame_id = claim(world)
    issue_id, _ = manual(world, lease_id, frame_id)
    assert decide(world, lease_id, issue_id).status_code in (200, 201)
    _expire(lease_id)
    # materialization happens when another caller touches the run: it must read incomplete
    other = client(world["other"]).post(next_url(), {"run_id": world["run"].pk}, format="json")
    assert other.status_code == 204  # frame is reserved for the previous reviewer
    frame = FrameReview.objects.get(pk=frame_id)
    assert frame.state == FrameReview.State.INCOMPLETE
    assert frame.previous_reviewer_id == world["reviewer"].pk
    resumed = _claim_again(world)
    assert resumed.status_code == 200 and resumed.data["frame"]["id"] == frame_id
    assert resumed.data["resumed"] is True


@pytest.mark.django_db
def test_undecided_issue_is_requeued_when_frame_already_left_in_review(world):
    """R1: expiry closes the lease and requeues undecided issues without touching the frame."""

    lease_id, frame_id = claim(world)
    decided, _ = manual(world, lease_id, frame_id)
    undecided, _ = manual(world, lease_id, frame_id)
    assert decide(world, lease_id, decided).status_code in (200, 201)
    assert Issue.objects.get(pk=undecided).state == Issue.State.IN_REVIEW
    FrameReview.objects.filter(pk=frame_id).update(state=FrameReview.State.AWAITING_FOLLOWUP)
    _expire(lease_id)

    assert (
        client(world["other"])
        .post(next_url(), {"run_id": world["run"].pk}, format="json")
        .status_code
        == 204
    )
    assert Lease.objects.get(pk=lease_id).closed_at is not None
    assert Issue.objects.get(pk=decided).state == Issue.State.CONFIRMED
    assert Issue.objects.get(pk=undecided).state == Issue.State.PENDING_REVIEW
    assert FrameReview.objects.get(pk=frame_id).state == FrameReview.State.AWAITING_FOLLOWUP


@pytest.mark.django_db
def test_expiry_after_real_verify_rework_keeps_awaiting_followup(confirmed, world, monkeypatch):  # noqa: F811
    """Same F1 path, but the frame leaves in_review through the real verify_rework."""

    frame = confirmed.frame_review
    frame.state = FrameReview.State.IN_REVIEW
    frame.save(update_fields=["state"])
    lease = Lease.objects.create(
        frame_review=frame,
        holder=world["reviewer"],
        queue_source="risk",
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    rework = ReworkRequest.objects.get(pk=create_request(confirmed, world).data["id"])
    snapshot = changed_snapshot(world)
    run = _run_for(world, snapshot)
    monkeypatch.setattr(rework_service, "_build_recheck_artifacts", lambda **_kw: (snapshot, run))
    assert _submit(world, rework, snapshot).status_code == 202
    assert _verify(world, rework, snapshot, True).status_code == 200
    frame.refresh_from_db()
    assert frame.state == FrameReview.State.AWAITING_FOLLOWUP and lease.closed_at is None

    _claim_again(world)
    frame.refresh_from_db()
    lease.refresh_from_db()
    assert frame.state == FrameReview.State.AWAITING_FOLLOWUP
    assert lease.closed_at is not None
    assert frame.previous_reviewer_id is None and frame.incomplete_since is None


def _hold_run_lock_then_verify(run_id, frame_id, entered: Event, release: Event):
    connections.close_all()
    try:
        with transaction.atomic():
            QCRun.objects.select_for_update().get(pk=run_id)  # same lock as verify_rework
            entered.set()
            assert release.wait(timeout=15)
            FrameReview.objects.filter(pk=frame_id).update(
                state=FrameReview.State.AWAITING_FOLLOWUP
            )
    finally:
        connections.close_all()


def _claim_in_thread(world, run_id):
    connections.close_all()
    try:
        return client(world["reviewer"]).post(next_url(), {"run_id": run_id}, format="json")
    finally:
        connections.close_all()


@pytest.mark.django_db(transaction=True)
def test_postgres_verify_holds_run_lock_first_claim_then_sees_awaiting_followup(world):
    """Order 1 (forced): verify owns the run lock; the claim waits, then must not rewrite."""

    assert connection.vendor == "postgresql"
    lease_id, frame_id = claim(world)
    _expire(lease_id)
    run_id = world["run"].pk
    entered, release = Event(), Event()
    with ThreadPoolExecutor(max_workers=2) as pool:
        verifier = pool.submit(_hold_run_lock_then_verify, run_id, frame_id, entered, release)
        assert entered.wait(timeout=15)
        claimer = pool.submit(_claim_in_thread, world, run_id)
        claim_blocked = not claimer.done()
        release.set()
        verifier.result(timeout=30)
        response = claimer.result(timeout=30)
    assert claim_blocked  # the claim really queued behind the verify transaction
    assert response.status_code == 204
    assert FrameReview.objects.get(pk=frame_id).state == FrameReview.State.AWAITING_FOLLOWUP
    assert Lease.objects.get(pk=lease_id).closed_at is not None


@pytest.mark.django_db(transaction=True)
def test_postgres_claim_holds_run_lock_first_verify_then_wins(world, monkeypatch):
    """Order 2 (forced): the claim materializes expiry under the run lock; verify waits."""

    assert connection.vendor == "postgresql"
    lease_id, frame_id = claim(world)
    _expire(lease_id)
    run_id = world["run"].pk
    inside_claim, release = Event(), Event()
    real_close = services._close_expired

    def paused_close(lease, now):
        real_close(lease, now)
        inside_claim.set()
        assert release.wait(timeout=15)

    monkeypatch.setattr(services, "_close_expired", paused_close)
    verify_done = Event()

    def verify_side():
        connections.close_all()
        try:
            with transaction.atomic():
                QCRun.objects.select_for_update().get(pk=run_id)
                FrameReview.objects.filter(pk=frame_id).update(
                    state=FrameReview.State.AWAITING_FOLLOWUP
                )
            verify_done.set()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        claimer = pool.submit(_claim_in_thread, world, run_id)
        assert inside_claim.wait(timeout=15)
        verifier = pool.submit(verify_side)
        verify_blocked = not verify_done.wait(timeout=1.0)
        release.set()
        response = claimer.result(timeout=30)
        verifier.result(timeout=30)
    assert verify_blocked  # verify waited for the claim's run lock
    assert response.status_code == 200  # claim won: frame was in_review, now re-leased
    assert FrameReview.objects.get(pk=frame_id).state == FrameReview.State.AWAITING_FOLLOWUP
    assert Lease.objects.get(pk=lease_id).closed_at is not None


def _live_lease_on_moved_frame(world):
    """claim -> frame leaves in_review (verify) while the lease is still alive."""

    lease_id, frame_id = claim(world)
    decided, _ = manual(world, lease_id, frame_id)
    undecided, _ = manual(world, lease_id, frame_id)
    assert decide(world, lease_id, decided).status_code in (200, 201)
    FrameReview.objects.filter(pk=frame_id).update(state=FrameReview.State.AWAITING_FOLLOWUP)
    assert Lease.objects.get(pk=lease_id).closed_at is None
    return lease_id, frame_id, undecided


@pytest.mark.django_db
def test_live_lease_on_awaiting_followup_frame_is_not_resumed(world):
    lease_id, frame_id, undecided = _live_lease_on_moved_frame(world)

    response = _claim_again(world)

    assert response.status_code == 204  # no resumed grant for a frame that left in_review
    assert Lease.objects.get(pk=lease_id).closed_at is not None
    assert Issue.objects.get(pk=undecided).state == Issue.State.PENDING_REVIEW
    assert FrameReview.objects.get(pk=frame_id).state == FrameReview.State.AWAITING_FOLLOWUP


@pytest.mark.django_db
def test_other_reviewer_claim_closes_live_lease_on_moved_frame(world):
    lease_id, frame_id, undecided = _live_lease_on_moved_frame(world)

    response = client(world["other"]).post(next_url(), {"run_id": world["run"].pk}, format="json")

    assert response.status_code == 204
    assert Lease.objects.get(pk=lease_id).closed_at is not None
    assert Issue.objects.get(pk=undecided).state == Issue.State.PENDING_REVIEW
    assert FrameReview.objects.get(pk=frame_id).state == FrameReview.State.AWAITING_FOLLOWUP


@pytest.mark.django_db
def test_renew_on_awaiting_followup_frame_is_conflict_and_closes_lease(world):
    lease_id, frame_id, undecided = _live_lease_on_moved_frame(world)

    renewed = client(world["reviewer"]).post(f"/api/leases/{lease_id}/renew/", {}, format="json")

    assert renewed.status_code == 409 and renewed.data["code"] == "LEASE_CONFLICT"
    lease = Lease.objects.get(pk=lease_id)
    assert lease.closed_at is not None
    assert Issue.objects.get(pk=undecided).state == Issue.State.PENDING_REVIEW
    assert FrameReview.objects.get(pk=frame_id).state == FrameReview.State.AWAITING_FOLLOWUP


@pytest.mark.django_db
def test_live_lease_on_in_review_frame_still_renews_and_resumes(world):
    lease_id, frame_id = claim(world)
    renewed = client(world["reviewer"]).post(f"/api/leases/{lease_id}/renew/", {}, format="json")
    assert renewed.status_code == 200
    resumed = _claim_again(world)
    assert resumed.status_code == 200 and resumed.data["resumed"] is True
    assert resumed.data["lease"]["id"] == lease_id


def _verify_pass_with_lease(confirmed, world, monkeypatch, frame_state, *, undecided=False):  # noqa: F811
    frame = confirmed.frame_review
    frame.state = frame_state
    frame.save(update_fields=["state"])
    lease = Lease.objects.create(
        frame_review=frame,
        holder=world["reviewer"],
        queue_source="risk",
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    other_issue = None
    if undecided:
        other_issue = Issue.objects.create(
            frame_review=frame,
            family=Issue.Family.E2,
            origin=Issue.Origin.REVIEWER,
            state=Issue.State.IN_REVIEW,
            anchor={"kind": "manual_region", "objects": []},
        )
    rework = ReworkRequest.objects.get(pk=create_request(confirmed, world).data["id"])
    snapshot = changed_snapshot(world)
    run = _run_for(world, snapshot)
    monkeypatch.setattr(rework_service, "_build_recheck_artifacts", lambda **_kw: (snapshot, run))
    assert _submit(world, rework, snapshot).status_code == 202
    assert _verify(world, rework, snapshot, True).status_code == 200
    lease.refresh_from_db()
    frame.refresh_from_db()
    rework.refresh_from_db()
    if other_issue is not None:
        other_issue.refresh_from_db()
    return frame, lease, other_issue, rework


@pytest.mark.django_db
def test_verify_keeps_completed_frame_completed(confirmed, world, monkeypatch):  # noqa: F811
    frame, _lease, _other, _rework = _verify_pass_with_lease(
        confirmed, world, monkeypatch, FrameReview.State.COMPLETED
    )
    assert frame.state == FrameReview.State.COMPLETED


@pytest.mark.django_db
def test_verify_hands_in_review_frame_over_when_everything_is_decided(
    confirmed,  # noqa: F811
    world,
    monkeypatch,
):
    frame, lease, _other, rework = _verify_pass_with_lease(
        confirmed, world, monkeypatch, FrameReview.State.IN_REVIEW
    )
    assert rework.status == ReworkRequest.Status.RESOLVED
    assert frame.state == FrameReview.State.AWAITING_FOLLOWUP
    assert lease.closed_at is not None


@pytest.mark.django_db
def test_verify_leaves_frame_and_lease_alone_while_an_issue_is_undecided(
    confirmed,  # noqa: F811
    world,
    monkeypatch,
):
    frame, lease, other, rework = _verify_pass_with_lease(
        confirmed, world, monkeypatch, FrameReview.State.IN_REVIEW, undecided=True
    )
    assert rework.status == ReworkRequest.Status.RESOLVED  # the verification is still recorded
    assert frame.state == FrameReview.State.IN_REVIEW
    assert lease.closed_at is None
    assert other.state == Issue.State.IN_REVIEW


@pytest.mark.django_db
@pytest.mark.parametrize(
    "state",
    [
        FrameReview.State.UNREVIEWED,
        FrameReview.State.INCOMPLETE,
        FrameReview.State.REVIEWED,
        FrameReview.State.AWAITING_FOLLOWUP,
    ],
)
def test_verify_keeps_existing_behaviour_for_other_states(confirmed, world, monkeypatch, state):  # noqa: F811
    frame, lease, _other, _rework = _verify_pass_with_lease(confirmed, world, monkeypatch, state)
    assert frame.state == FrameReview.State.AWAITING_FOLLOWUP
    assert lease.closed_at is None  # only an in_review frame hands its lease over


@pytest.mark.django_db
@pytest.mark.parametrize("state", [FrameReview.State.UNREVIEWED, FrameReview.State.INCOMPLETE])
def test_verify_does_not_hide_a_claimable_frame_with_undecided_issue(
    confirmed,  # noqa: F811
    world,
    monkeypatch,
    state,
):
    frame, _lease, _other, _rework = _verify_pass_with_lease(
        confirmed, world, monkeypatch, state, undecided=True
    )
    assert frame.state == state


def _renew_in_thread(world, lease_id):
    connections.close_all()
    try:
        return client(world["reviewer"]).post(f"/api/leases/{lease_id}/renew/", {}, format="json")
    finally:
        connections.close_all()


@pytest.mark.django_db(transaction=True)
def test_postgres_verify_handover_holds_run_lock_first_renew_is_refused(world):
    assert connection.vendor == "postgresql"
    lease_id, frame_id = claim(world)
    run_id = world["run"].pk
    entered, release = Event(), Event()

    def handover():
        connections.close_all()
        try:
            with transaction.atomic():
                QCRun.objects.select_for_update().get(pk=run_id)  # lock verify_rework holds
                entered.set()
                assert release.wait(timeout=15)
                frame = FrameReview.objects.select_for_update().get(pk=frame_id)
                rework_service._move_frame_to_followup(frame)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        verifier = pool.submit(handover)
        assert entered.wait(timeout=15)
        renewer = pool.submit(_renew_in_thread, world, lease_id)
        renew_blocked = not renewer.done()
        release.set()
        verifier.result(timeout=30)
        response = renewer.result(timeout=30)
    assert renew_blocked
    assert response.status_code == 409 and response.data["code"] == "LEASE_CONFLICT"
    assert FrameReview.objects.get(pk=frame_id).state == FrameReview.State.AWAITING_FOLLOWUP
    assert Lease.objects.get(pk=lease_id).closed_at is not None


@pytest.mark.django_db(transaction=True)
def test_postgres_renew_holds_run_lock_first_then_handover_closes_lease(world, monkeypatch):
    assert connection.vendor == "postgresql"
    lease_id, frame_id = claim(world)
    run_id = world["run"].pk
    inside_renew, release = Event(), Event()
    real_scope = services.has_review_scope

    def paused_scope(**kwargs):
        inside_renew.set()  # renew already owns the run lock here
        assert release.wait(timeout=15)
        return real_scope(**kwargs)

    monkeypatch.setattr(services, "has_review_scope", paused_scope)
    handover_done = Event()

    def handover():
        connections.close_all()
        try:
            with transaction.atomic():
                QCRun.objects.select_for_update().get(pk=run_id)
                frame = FrameReview.objects.select_for_update().get(pk=frame_id)
                rework_service._move_frame_to_followup(frame)
            handover_done.set()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        renewer = pool.submit(_renew_in_thread, world, lease_id)
        assert inside_renew.wait(timeout=15)
        verifier = pool.submit(handover)
        handover_blocked = not handover_done.wait(timeout=1.0)
        release.set()
        response = renewer.result(timeout=30)
        verifier.result(timeout=30)
    assert handover_blocked
    assert response.status_code == 200  # renew ran while the frame was still in_review
    assert FrameReview.objects.get(pk=frame_id).state == FrameReview.State.AWAITING_FOLLOWUP
    assert Lease.objects.get(pk=lease_id).closed_at is not None
