"""M03-R02/F1: lease expiry must not rewrite a frame that already left in_review."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.db import connection, connections, transaction
from django.utils import timezone

from review.finalization_service import complete_scope_frames
from review.models import FrameReview, Lease
from runs.models import QCRun
from tests.review.test_final_source_guard import _complete_final, final_world  # noqa: F401
from tests.review.test_issues_decisions import claim, decide, manual
from tests.review.test_queue_lease import client, next_url

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
    assert other.status_code in (200, 204, 404)
    frame = FrameReview.objects.get(pk=frame_id)
    assert frame.state in (FrameReview.State.INCOMPLETE, FrameReview.State.IN_REVIEW)
    resumed = _claim_again(world)
    assert resumed.status_code == 200 and resumed.data["frame"]["id"] == frame_id
    assert resumed.data["resumed"] is True


@pytest.mark.django_db(transaction=True)
def test_postgres_race_verify_vs_claim_keeps_awaiting_followup(world):
    assert connection.vendor == "postgresql"
    lease_id, frame_id = claim(world)
    _expire(lease_id)
    run_id = world["run"].pk
    barrier = Barrier(2)

    def verify_side() -> None:
        connections.close_all()
        try:
            barrier.wait(timeout=15)
            with transaction.atomic():
                QCRun.objects.select_for_update().get(pk=run_id)  # same lock as verify_rework
                FrameReview.objects.filter(pk=frame_id).update(
                    state=FrameReview.State.AWAITING_FOLLOWUP
                )
        finally:
            connections.close_all()

    def claim_side() -> int:
        connections.close_all()
        try:
            barrier.wait(timeout=15)
            return (
                client(world["reviewer"])
                .post(next_url(), {"run_id": run_id}, format="json")
                .status_code
            )
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        verifier, claimer = pool.submit(verify_side), pool.submit(claim_side)
        verifier.result()
        claim_status = claimer.result()
    assert claim_status in (200, 204)
    frame = FrameReview.objects.get(pk=frame_id)
    # Either order must end awaiting_followup, or (claim first) a fresh in_review lease that
    # verify then overwrote; never a lost update to incomplete/unreviewed.
    assert frame.state == FrameReview.State.AWAITING_FOLLOWUP
    assert Lease.objects.get(pk=lease_id).closed_at is not None
