"""submit_rework's user mutex must not conflict with a concurrent claim's FK KEY SHARE.

R is both an annotator (owner of a fix_pending rework) and a reviewer whose lease expired.
Reviewer O claims R's frame: its COMMIT takes KEY SHARE on R's user row (frame.previous_reviewer).
R's `submitted` holds R's user row (the per-user mutex) and waits for the run lock O holds.
With FOR UPDATE that is a deadlock; FOR NO KEY UPDATE is not (same class as claim_next).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from django.db import connection, connections
from django.utils import timezone

from accounts.models import Role, RoleAssignment
from review import decision_source, rework_service
from review.models import FrameReview, Lease, ReworkRequest
from tests.review.test_create_rework_lock_order import _create_as
from tests.review.test_frame_followup_flow import (  # noqa: F401
    _confirmed_issue,
    approved_test_policy,
    storage_url,
)
from tests.review.test_issues_decisions import claim
from tests.review.test_queue_lease import client, next_url
from tests.review.test_rework import (  # noqa: F401
    _run_for,
    changed_snapshot,
    cvat_base_url,
)

pytest_plugins = ["tests.review.test_queue_lease"]
WAIT = 30


def _waiters() -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = current_database() AND wait_event_type = 'Lock'"
        )
        return cursor.fetchone()[0]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("repeat", range(5))
def test_annotator_submit_vs_other_reviewers_claim_of_their_expired_frame(
    world,
    monkeypatch,
    settings,
    repeat,  # noqa: F811
):
    del repeat
    settings.REVIEW_INCOMPLETE_RESERVATION_SECONDS = 1
    holder, claimer = world["reviewer"], world["other"]
    RoleAssignment.objects.create(user=holder, role=Role.ANNOTATOR, dataset_id=42)
    lease_id, frame_id = claim(world)
    issue_id = _confirmed_issue(world, lease_id, frame_id)
    created = _create_as(world, claimer, holder, issue_id)  # `other` asks R to fix it
    assert created.status_code == 201, created.data
    rework = ReworkRequest.objects.get(pk=created.data["id"])
    Lease.objects.filter(pk=lease_id).update(expires_at=timezone.now() - timedelta(seconds=30))
    snapshot = changed_snapshot(world)
    pair = (snapshot, _run_for(world, snapshot))
    monkeypatch.setattr(rework_service, "_build_recheck_artifacts", lambda **_kw: pair)

    inside, release = Event(), Event()
    real = decision_source.claim_undecided_issues

    def paused(frame):
        real(frame)
        inside.set()
        assert release.wait(timeout=WAIT)

    monkeypatch.setattr(decision_source, "claim_undecided_issues", paused)

    def claim_as_other():
        connections.close_all()
        try:
            return client(claimer).post(next_url(), {"run_id": world["run"].pk}, format="json")
        except Exception as exc:
            return exc
        finally:
            connections.close_all()

    def submit_as_holder():
        connections.close_all()
        try:
            return client(holder).post(
                f"/api/rework/{rework.pk}/submitted/",
                {"cvat_revision": snapshot.revision_sha256},
                format="json",
            )
        except Exception as exc:
            return exc
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        claimer_future = pool.submit(claim_as_other)
        assert inside.wait(timeout=WAIT), "claimer never reached its frame write"
        submit_future = pool.submit(submit_as_holder)
        deadline = time.monotonic() + WAIT
        while _waiters() < 1:
            assert time.monotonic() < deadline, "submit never queued on the run lock"
            time.sleep(0.02)
        release.set()
        results = (claimer_future.result(timeout=WAIT), submit_future.result(timeout=WAIT))
    codes = [r if isinstance(r, Exception) else r.status_code for r in results]
    assert codes == [200, 202], codes
    assert FrameReview.objects.get(pk=frame_id).state == FrameReview.State.IN_REVIEW
    assert ReworkRequest.objects.get(pk=rework.pk).status == "recheck_pending"
