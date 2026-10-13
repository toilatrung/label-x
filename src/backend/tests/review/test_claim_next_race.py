"""claim_next vs the previous holder's own writers (PostgreSQL threads, synthetic rows).

Another reviewer's claim takes a frame whose lease expired and records the previous holder on
the frame (FK to auth_user, deferred: PostgreSQL takes KEY SHARE on that user row at COMMIT).
The previous holder's own request meanwhile holds ITS user row (the per-user mutex) and waits
for the run lock the claimer holds. A mutex taken with FOR UPDATE conflicts with that KEY SHARE
-> deadlock (HTTP 500 / DeadlockDetected). The mutex must not conflict with FK checks.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event

import pytest
from django.db import connection, connections
from django.utils import timezone

from review import decision_source
from review.models import FrameReview, Lease
from tests.review.test_queue_lease import (
    client,
    next_url,
    persist_manual_decision,
)

pytest_plugins = ["tests.review.test_queue_lease"]
WAIT = 30
HOLDER_ACTIONS = ("claim", "complete", "renew")


@pytest.fixture(autouse=True)
def policy(settings):
    settings.REVIEW_LEASE_TTL_SECONDS = 60
    settings.REVIEW_INCOMPLETE_RESERVATION_SECONDS = 1  # the frame is open to others at once


@pytest.fixture
def expired_incomplete_frame(world):
    """Reviewer R holds a frame with a persisted decision; its lease is long expired."""

    first = client(world["reviewer"]).post(next_url(), {"run_id": world["run"].pk}, format="json")
    lease_id, frame_id = first.data["lease"]["id"], first.data["frame"]["id"]
    persist_manual_decision(world, lease_id)
    Lease.objects.filter(pk=lease_id).update(expires_at=timezone.now() - timedelta(seconds=30))
    return lease_id, frame_id


def _request(world, who, action, lease_id, frame_id):
    connections.close_all()
    try:
        api = client(world[who])
        if action == "claim":
            response = api.post(next_url(), {"run_id": world["run"].pk}, format="json")
        elif action == "complete":
            response = api.post(
                f"/api/frames/{frame_id}/complete/", {"lease_id": lease_id}, format="json"
            )
        else:
            response = api.post(f"/api/leases/{lease_id}/renew/", {}, format="json")
        return response.status_code
    except Exception as exc:  # an unhandled DB error surfaces as an exception in tests
        return f"{type(exc).__name__}"
    finally:
        connections.close_all()


def _waiters() -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = current_database() AND wait_event_type = 'Lock'"
        )
        return cursor.fetchone()[0]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("action", HOLDER_ACTIONS)
@pytest.mark.parametrize("repeat", range(5))
def test_claimer_commits_while_previous_holder_waits_on_the_run_lock(
    world,
    expired_incomplete_frame,
    monkeypatch,
    action,
    repeat,
):
    """Forced order: O (claimer) holds the run lock, paused after writing the frame; the
    previous holder R takes its user mutex and queues on the run lock; then O commits."""

    del repeat
    lease_id, frame_id = expired_incomplete_frame
    inside, release = Event(), Event()
    real = decision_source.claim_undecided_issues

    def paused(frame):
        real(frame)
        inside.set()
        assert release.wait(timeout=WAIT)

    monkeypatch.setattr(decision_source, "claim_undecided_issues", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claimer = pool.submit(_request, world, "other", "claim", lease_id, frame_id)
        assert inside.wait(timeout=WAIT), "claimer never reached its frame write"
        holder = pool.submit(_request, world, "reviewer", action, lease_id, frame_id)
        deadline = time.monotonic() + WAIT
        while _waiters() < 1:
            assert time.monotonic() < deadline, "holder never queued on the run lock"
            time.sleep(0.02)
        release.set()
        results = (claimer.result(timeout=WAIT), holder.result(timeout=WAIT))
    assert results[0] == 200, results  # the claimer committed
    assert not any(isinstance(r, str) or r == 500 for r in results), results  # no deadlock/500
    frame = FrameReview.objects.get(pk=frame_id)
    assert frame.state == FrameReview.State.IN_REVIEW
    assert Lease.objects.filter(frame_review=frame, closed_at__isnull=True).count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("repeat", range(5))
def test_four_claims_and_four_holder_requests_race_without_deadlock(
    world,
    expired_incomplete_frame,
    repeat,  # noqa: F811
):
    del repeat
    lease_id, frame_id = expired_incomplete_frame
    barrier = Barrier(8)

    def go(who, action):
        barrier.wait(timeout=WAIT)
        return _request(world, who, action, lease_id, frame_id)

    plan = [("other", "claim")] * 4 + [
        ("reviewer", "claim"),
        ("reviewer", "complete"),
        ("reviewer", "renew"),
        ("reviewer", "claim"),
    ]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = [f.result(timeout=WAIT * 2) for f in [pool.submit(go, *p) for p in plan]]
    assert not any(isinstance(r, str) or r == 500 for r in results), results
    assert (
        Lease.objects.filter(frame_review_id=frame_id, closed_at__isnull=True).count() <= 1
    )  # one winner, constraints intact
