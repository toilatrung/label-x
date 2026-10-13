"""create_rework vs submitted: one lock order (User -> QCRun -> ...) on PostgreSQL.

create_rework used to take the annotator's user row AFTER the run lock, while `submitted`
(by that annotator) takes its user row BEFORE the run lock: a lock-order inversion on the same
auth_user row. Synthetic rows, real threads; no CVAT.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from types import SimpleNamespace

import pytest
from django.db import connection, connections
from django.test.utils import CaptureQueriesContext

from accounts.models import Role, RoleAssignment
from review import rework_service
from review.models import Issue, ReworkRequest
from tests.review.test_frame_followup_flow import (  # noqa: F401
    _confirmed_issue,
    _rework,
    approved_test_policy,
    storage_url,
)
from tests.review.test_issues_decisions import claim
from tests.review.test_queue_lease import client
from tests.review.test_rework import (  # noqa: F401
    _run_for,
    changed_snapshot,
    create_body,
    cvat_base_url,
)

pytest_plugins = ["tests.review.test_queue_lease"]
WAIT = 30


@pytest.fixture
def scene(world, monkeypatch):  # noqa: F811
    """Issue A has a fix_pending rework (annotator submits it); issue B is confirmed and the
    reviewer is about to create its rework for the SAME annotator."""

    lease_id, frame_id = claim(world)
    issue_a = _confirmed_issue(world, lease_id, frame_id)
    rework_a = _rework(world, issue_a)
    issue_b = _confirmed_issue(world, lease_id, frame_id)
    snapshot = changed_snapshot(world)
    pair = (snapshot, _run_for(world, snapshot))
    monkeypatch.setattr(rework_service, "_build_recheck_artifacts", lambda **_kw: pair)
    return SimpleNamespace(world=world, rework_a=rework_a, issue_b=issue_b, snapshot=snapshot)


def _create(sc):
    connections.close_all()
    try:
        body = create_body(SimpleNamespace(pk=sc.issue_b), sc.world)
        return client(sc.world["reviewer"]).post("/api/rework/", body, format="json")
    except Exception as exc:
        return exc
    finally:
        connections.close_all()


def _submit(sc):
    connections.close_all()
    try:
        return client(sc.world["author"]).post(
            f"/api/rework/{sc.rework_a.pk}/submitted/",
            {"cvat_revision": sc.snapshot.revision_sha256},
            format="json",
        )
    except Exception as exc:
        return exc
    finally:
        connections.close_all()


def _codes(*results):
    return [r if isinstance(r, Exception) else r.status_code for r in results]


def _waiters() -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = current_database() AND wait_event_type = 'Lock'"
        )
        return cursor.fetchone()[0]


def _wait_waiters(n: int) -> None:
    deadline = time.monotonic() + WAIT
    while _waiters() < n:
        assert time.monotonic() < deadline, f"expected {n} lock waiters"
        time.sleep(0.02)


def _assert_both_committed(sc, results):
    codes = _codes(*results)
    assert codes == [201, 202], codes
    assert ReworkRequest.objects.get(pk=sc.rework_a.pk).status == "recheck_pending"
    assert Issue.objects.get(pk=sc.issue_b).state == Issue.State.FIX_PENDING


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("repeat", range(5))
def test_create_holds_run_lock_then_annotator_submits(scene, monkeypatch, repeat):
    """Order 1: create owns the run lock; the annotator's submit takes its user row and queues
    on the run; create then needs the annotator row (the inverted lock)."""

    del repeat
    inside, release = Event(), Event()
    real = rework_service._reviewer_identity

    def paused(request, **kw):
        result = real(request, **kw)
        if kw.get("action") == "rework.create":
            inside.set()
            assert release.wait(timeout=WAIT)
        return result

    monkeypatch.setattr(rework_service, "_reviewer_identity", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        creator = pool.submit(_create, scene)
        assert inside.wait(timeout=WAIT)
        submitter = pool.submit(_submit, scene)
        _wait_waiters(1)  # the annotator holds its user row and waits for the run lock
        release.set()
        results = (creator.result(timeout=WAIT), submitter.result(timeout=WAIT))
    _assert_both_committed(scene, results)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("repeat", range(5))
def test_annotator_submits_holding_run_lock_then_create(scene, monkeypatch, repeat):
    """Order 2: submit owns user row + run lock; create queues behind it and goes second."""

    del repeat
    inside, release = Event(), Event()
    real = rework_service._existing_submission
    calls: list[int] = []

    def paused(**kw):
        result = real(**kw)
        calls.append(1)
        if len(calls) == 2:  # the re-check made inside the locked transaction
            inside.set()
            assert release.wait(timeout=WAIT)
        return result

    monkeypatch.setattr(rework_service, "_existing_submission", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        submitter = pool.submit(_submit, scene)
        assert inside.wait(timeout=WAIT)
        creator = pool.submit(_create, scene)
        _wait_waiters(1)
        release.set()
        results = (creator.result(timeout=WAIT), submitter.result(timeout=WAIT))
    _assert_both_committed(scene, results)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("repeat", range(5))
def test_four_creates_and_four_submits_race_without_deadlock(scene, repeat):
    del repeat
    barrier = Barrier(8)

    def go(fn):
        barrier.wait(timeout=WAIT)
        return fn(scene)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(go, fn) for fn in [_create] * 4 + [_submit] * 4]
        results = [f.result(timeout=WAIT * 2) for f in futures]
    codes = _codes(*results)
    assert not any(isinstance(c, Exception) or c >= 500 for c in codes), codes
    assert codes.count(201) == 1 and codes.count(202) >= 1, codes  # one winner each side


def _create_as(world, actor, annotator, issue_id):
    connections.close_all()
    try:
        body = {
            **create_body(SimpleNamespace(pk=issue_id), world),
            "annotator_user_id": annotator.pk,
        }
        return client(actor).post("/api/rework/", body, format="json")
    except Exception as exc:
        return exc
    finally:
        connections.close_all()


@pytest.fixture
def two_way_users(world):  # noqa: F811
    """Both reviewers can also be annotators, so each may be the other's rework annotator."""

    for user in (world["reviewer"], world["other"]):
        RoleAssignment.objects.create(user=user, role=Role.ANNOTATOR, dataset_id=42)
    return world["reviewer"], world["other"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("repeat", range(5))
def test_crossed_actor_annotator_pairs_do_not_deadlock(world, two_way_users, repeat):  # noqa: F811
    """(A creates for B) and (B creates for A) at once: user rows must be taken in one global
    order (pk), whoever is the actor."""

    del repeat
    first, second = two_way_users
    lease_id, frame_id = claim(world)
    issue_one = _confirmed_issue(world, lease_id, frame_id)
    issue_two = _confirmed_issue(world, lease_id, frame_id)
    barrier = Barrier(2)

    def go(actor, annotator, issue_id):
        barrier.wait(timeout=WAIT)
        return _create_as(world, actor, annotator, issue_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(go, first, second, issue_one),
            pool.submit(go, second, first, issue_two),
        ]
        results = [f.result(timeout=WAIT) for f in futures]
    assert _codes(*results) == [201, 201], _codes(*results)


def _lock_statements(world, issue_id):
    body = create_body(SimpleNamespace(pk=issue_id), world)
    with CaptureQueriesContext(connection) as queries:
        response = client(world["reviewer"]).post("/api/rework/", body, format="json")
    assert response.status_code == 201, response.data
    return [
        q["sql"] for q in queries if "FOR UPDATE" in q["sql"] or "FOR NO KEY UPDATE" in q["sql"]
    ]


@pytest.mark.django_db
def test_create_rework_locks_users_by_ascending_pk_then_run_then_issue(scene):
    """Structural guard for the lock protocol (equivalent to the mutants a thread race cannot
    see: descending order is still consistent, and an unordered scan merely happens to match).
    One statement locks the actor AND the annotator rows ``ORDER BY id ASC``; only then the run;
    only then the issue."""

    statements = _lock_statements(scene.world, scene.issue_b)
    tables = [
        '"auth_user"'
        if 'FROM "auth_user"' in sql
        else '"qc_run"'
        if 'FROM "qc_run"' in sql
        else '"review_issue"'
        if 'FROM "review_issue"' in sql
        else "other"
        for sql in statements
    ]
    assert tables[:3] == ['"auth_user"', '"qc_run"', '"review_issue"'], tables
    users = statements[0]
    assert "ORDER BY" in users and '"auth_user"."id" ASC' in users, users
    actor, annotator = scene.world["reviewer"].pk, scene.world["author"].pk
    assert f'"auth_user"."id" IN ({min(actor, annotator)}, {max(actor, annotator)})' in users or (
        f'"auth_user"."id" IN ({actor}, {annotator})' in users
        or f'"auth_user"."id" IN ({annotator}, {actor})' in users
    ), users
    assert sum('FROM "auth_user"' in sql for sql in statements) == 1  # annotator not re-locked
