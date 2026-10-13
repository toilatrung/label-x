"""QA-D: the verify audit events must carry the real before/after (not just exist)."""

from __future__ import annotations

import pytest

from audit.models import AuditEvent
from review import rework_service
from review.models import ReworkRequest
from runs.models import QCRun
from tests.review.test_queue_lease import client
from tests.review.test_rework import (  # noqa: F401 - fixtures
    changed_snapshot,
    confirmed,
    create_request,
    cvat_base_url,
)

pytest_plugins = ["tests.review.test_queue_lease"]


def _submitted(confirmed, world, monkeypatch):  # noqa: F811
    created = create_request(confirmed, world)
    rework = ReworkRequest.objects.get(pk=created.data["id"])
    snapshot = changed_snapshot(world)
    run = QCRun.objects.create(
        snapshot=snapshot,
        config_version=world["run"].config_version,
        seed=1,
        status=QCRun.Status.COMPLETED,
        origin_run=world["run"],
        dataset_id=42,
        scope_hash=snapshot.revision_sha256,
        created_by=world["author"],
    )
    monkeypatch.setattr(
        rework_service, "_build_recheck_artifacts", lambda **_kwargs: (snapshot, run)
    )
    submitted = client(world["author"]).post(
        f"/api/rework/{rework.pk}/submitted/",
        {"cvat_revision": snapshot.revision_sha256},
        format="json",
    )
    assert submitted.status_code == 202, submitted.data
    return rework, snapshot


def _verify(world, rework, snapshot, passed):
    body = {"passed": passed, "revision": snapshot.revision_sha256}
    if not passed:
        body["reason"] = "Still wrong"
    response = client(world["other"]).post(f"/api/rework/{rework.pk}/verify/", body, format="json")
    assert response.status_code == 200, response.data
    return response


def _event(action, object_id):
    return AuditEvent.objects.get(action=action, object_id=str(object_id))


@pytest.mark.django_db
def test_verify_fail_audit_records_the_real_transition(confirmed, world, monkeypatch):  # noqa: F811
    rework, snapshot = _submitted(confirmed, world, monkeypatch)
    before_state = {"status": "recheck_pending", "issue_state": "recheck_pending"}
    _verify(world, rework, snapshot, passed=False)

    verify = _event("rework.verify_fail", rework.pk)
    assert verify.before == before_state
    assert verify.after == {
        "status": "reopened",
        "issue_state": "reopened",
        "actor_role": "reviewer",
    }
    assert verify.revision == snapshot.revision_sha256 and verify.reason == "Still wrong"
    assert verify.actor_id == world["other"].pk

    reopen = _event("issue.reopen_fix", confirmed.pk)
    assert reopen.before == {"status": "reopened", "issue_state": "reopened"}
    assert reopen.after == {"status": "fix_pending", "issue_state": "fix_pending"}
    assert reopen.revision == snapshot.revision_sha256 and reopen.reason == "Still wrong"


@pytest.mark.django_db
def test_verify_pass_audit_records_the_real_transition(confirmed, world, monkeypatch):  # noqa: F811
    rework, snapshot = _submitted(confirmed, world, monkeypatch)
    _verify(world, rework, snapshot, passed=True)

    verify = _event("rework.verify_pass", rework.pk)
    assert verify.before == {"status": "recheck_pending", "issue_state": "recheck_pending"}
    assert verify.after == {
        "status": "resolved",
        "issue_state": "resolved",
        "actor_role": "reviewer",
    }
    assert verify.revision == snapshot.revision_sha256
    assert not AuditEvent.objects.filter(action="issue.reopen_fix").exists()
