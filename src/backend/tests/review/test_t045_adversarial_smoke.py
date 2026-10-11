"""T-045 manual/API adversarial smoke test harness.

Executes and records the 8 required adversarial scenarios on an isolated PostgreSQL test database:
1. Allowed request (claim lease, create manual issue, confirm decision)
2. Denied role (annotator denied from claiming review queue -> 403 FORBIDDEN)
3. Denied scope / IDOR (reviewer scoped to dataset 99 denied from run on dataset 42)
4. Self-review / same natural person (reviewer sharing EmployeeIdentity with author denied)
5. Idempotent retry with same key and payload -> 201 Created with identical ID
6. Key reuse with different payload -> 409 Conflict with IDEMPOTENCY_KEY_REUSED
7. Expired lease (attempt renew after TTL expires -> 409 Conflict with LEASE_CONFLICT)
8. Audit failure transaction rollback (failure in audit write rolls back decision + issue state)
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.core.files.storage import storages
from django.utils import timezone

from accounts.models import CvatIdentity, EmployeeIdentity, Role, RoleAssignment
from audit.models import AuditEvent
from review.models import Issue, Lease, ReviewDecision
from tests.review.test_queue_lease import client, next_url

pytest_plugins = ["tests.review.test_queue_lease"]


@pytest.fixture(autouse=True)
def policy(settings):
    settings.REVIEW_LEASE_TTL_SECONDS = 60
    settings.REVIEW_INCOMPLETE_RESERVATION_SECONDS = 120


@pytest.fixture(autouse=True)
def snapshot_storage_mock(monkeypatch):
    monkeypatch.setattr(
        storages["snapshots"],
        "url",
        lambda name: f"https://storage.test/{name}",
    )


def claim_frame(world, user="reviewer"):
    api = client(world[user])
    response = api.post(next_url(), {"run_id": world["run"].pk}, format="json")
    return response


@pytest.mark.django_db
def test_t045_smoke_01_allowed_request(world):
    """Scenario 1: Allowed reviewer claims lease, creates manual issue, confirms decision."""
    # 1. Claim lease
    claim_resp = claim_frame(world, "reviewer")
    assert claim_resp.status_code == 200, claim_resp.data
    lease_id = claim_resp.data["lease"]["id"]
    frame_id = claim_resp.data["frame"]["id"]

    # 2. Create manual issue
    api = client(world["reviewer"])
    idempotency_key = str(uuid4())
    issue_payload = {
        "frame_id": frame_id,
        "lease_id": lease_id,
        "family": "E1",
        "description": "Manual missing annotation issue",
        "anchor": {
            "kind": "manual_region",
            "objects": [],
            "bbox": {"x1": 5, "y1": 5, "x2": 50, "y2": 50},
            "policy_version": "anchor-v1",
        },
    }
    issue_resp = api.post(
        "/api/issues/", issue_payload, format="json", HTTP_IDEMPOTENCY_KEY=idempotency_key
    )
    assert issue_resp.status_code == 201, issue_resp.data
    issue_id = issue_resp.data["id"]

    # 3. Confirm decision
    decision_payload = {
        "lease_id": lease_id,
        "action": "confirm",
        "revision": world["run"].snapshot.revision_sha256,
        "family": "E1",
        "severity": "medium",
        "rule_ids": ["RULE-E1-01"],
    }
    decide_resp = api.post(f"/api/issues/{issue_id}/decisions/", decision_payload, format="json")
    assert decide_resp.status_code == 201, decide_resp.data

    # Post-check DB
    db_issue = Issue.objects.get(pk=issue_id)
    assert db_issue.state == Issue.State.CONFIRMED
    assert db_issue.severity == "medium"
    assert ReviewDecision.objects.filter(issue=db_issue).count() == 1
    decision = ReviewDecision.objects.get(issue=db_issue)
    assert decision.action == "confirm"
    assert decision.actor == world["reviewer"]
    assert AuditEvent.objects.filter(pk=decision.audit_event_id).exists()


@pytest.mark.django_db
def test_t045_smoke_02_denied_role(world):
    """Scenario 2: Denied role - Annotator cannot claim review lease."""
    api = client(world["author"])  # Role is ANNOTATOR
    resp = api.post(next_url(), {"run_id": world["run"].pk}, format="json")
    assert resp.status_code == 403
    assert resp.data["code"] == "FORBIDDEN"
    # Post-check DB: zero leases for author
    assert Lease.objects.filter(holder=world["author"]).count() == 0


@pytest.mark.django_db
def test_t045_smoke_03_denied_scope(world):
    """Scenario 3: Denied scope / IDOR - Reviewer assigned only to dataset 99."""
    admin = world["admin"]
    reviewer_other_dataset = User.objects.create_user("reviewer-scope99")
    RoleAssignment.objects.create(user=reviewer_other_dataset, role=Role.REVIEWER, dataset_id=99)
    emp = EmployeeIdentity.objects.create(
        employee_id="person-scope99", verified_at=timezone.now(), verified_by=admin
    )
    CvatIdentity.objects.create(user=reviewer_other_dataset, cvat_user_id=799, employee=emp)

    api = client(reviewer_other_dataset)
    resp = api.post(next_url(), {"run_id": world["run"].pk}, format="json")
    assert resp.status_code == 403
    assert resp.data["code"] == "OUT_OF_SCOPE"
    assert Lease.objects.filter(holder=reviewer_other_dataset).count() == 0


@pytest.mark.django_db
def test_t045_smoke_04_self_review_same_person(world):
    """Scenario 4: Self-review guard - Reviewer sharing EmployeeIdentity with annotator."""
    claim_resp = claim_frame(world, "reviewer")
    assert claim_resp.status_code == 200
    lease_id = claim_resp.data["lease"]["id"]
    frame_id = claim_resp.data["frame"]["id"]

    api = client(world["reviewer"])
    issue_resp = api.post(
        "/api/issues/",
        {
            "frame_id": frame_id,
            "lease_id": lease_id,
            "family": "E1",
            "description": "Region",
            "anchor": {
                "kind": "manual_region",
                "objects": [],
                "bbox": {"x1": 1, "y1": 1, "x2": 10, "y2": 10},
                "policy_version": "anchor-v1",
            },
        },
        format="json",
    )
    assert issue_resp.status_code == 201
    issue_id = issue_resp.data["id"]

    # Create alias reviewer account mapped to the same employee as author (person-author)
    author_alias = User.objects.create_user("author-reviewer-alias")
    RoleAssignment.objects.create(user=author_alias, role=Role.REVIEWER, dataset_id=42)
    CvatIdentity.objects.create(
        user=author_alias,
        cvat_user_id=1002,
        employee=CvatIdentity.objects.get(user=world["author"]).employee,
    )

    # Deliberately force holder to alias to test direct API defense-in-depth
    Lease.objects.filter(pk=lease_id).update(holder=author_alias)

    alias_api = client(author_alias)
    decide_resp = alias_api.post(
        f"/api/issues/{issue_id}/decisions/",
        {
            "lease_id": lease_id,
            "action": "confirm",
            "revision": world["run"].snapshot.revision_sha256,
            "family": "E1",
            "severity": "medium",
        },
        format="json",
    )
    assert decide_resp.status_code == 403
    assert decide_resp.data["code"] == "SELF_REVIEW_FORBIDDEN"
    assert ReviewDecision.objects.filter(issue_id=issue_id).count() == 0


@pytest.mark.django_db
def test_t045_smoke_05_idempotent_retry(world):
    """Scenario 5: Idempotent retry - Same Idempotency-Key and same payload."""
    claim_resp = claim_frame(world, "reviewer")
    lease_id = claim_resp.data["lease"]["id"]
    frame_id = claim_resp.data["frame"]["id"]

    api = client(world["reviewer"])
    key = str(uuid4())
    payload = {
        "frame_id": frame_id,
        "lease_id": lease_id,
        "family": "E1",
        "description": "Idempotency test issue",
        "anchor": {
            "kind": "manual_region",
            "objects": [],
            "bbox": {"x1": 1, "y1": 1, "x2": 20, "y2": 20},
            "policy_version": "anchor-v1",
        },
    }

    first = api.post("/api/issues/", payload, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert first.status_code == 201
    first_id = first.data["id"]

    # Replay same key and payload
    second = api.post("/api/issues/", payload, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert second.status_code == 201
    assert second.data["id"] == first_id

    # Post-check DB
    assert Issue.objects.filter(created_by=world["reviewer"], idempotency_key=key).count() == 1


@pytest.mark.django_db
def test_t045_smoke_06_idempotency_key_reuse_different_payload(world):
    """Scenario 6: Key conflict - Reusing Idempotency-Key with different payload."""
    claim_resp = claim_frame(world, "reviewer")
    lease_id = claim_resp.data["lease"]["id"]
    frame_id = claim_resp.data["frame"]["id"]

    api = client(world["reviewer"])
    key = str(uuid4())
    payload_a = {
        "frame_id": frame_id,
        "lease_id": lease_id,
        "family": "E1",
        "description": "Original payload A",
        "anchor": {
            "kind": "manual_region",
            "objects": [],
            "bbox": {"x1": 1, "y1": 1, "x2": 20, "y2": 20},
            "policy_version": "anchor-v1",
        },
    }
    first = api.post("/api/issues/", payload_a, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert first.status_code == 201

    payload_b = dict(payload_a)
    payload_b["description"] = "Altered payload B"
    second = api.post("/api/issues/", payload_b, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert second.status_code == 409
    assert second.data["code"] == "IDEMPOTENCY_KEY_REUSED"

    # Post-check DB: original payload retained
    issue = Issue.objects.get(created_by=world["reviewer"], idempotency_key=key)
    assert issue.description == "Original payload A"


@pytest.mark.django_db
def test_t045_smoke_07_expired_lease(world, monkeypatch):
    """Scenario 7: Expired lease - Attempting renew or decision after expiry returns 409."""
    clock = [timezone.now()]
    monkeypatch.setattr("review.services._now", lambda: clock[0])

    claim_resp = claim_frame(world, "reviewer")
    assert claim_resp.status_code == 200
    lease_id = claim_resp.data["lease"]["id"]

    # Fast-forward clock past lease TTL (60s)
    clock[0] = clock[0] + timedelta(seconds=75)

    api = client(world["reviewer"])
    renew_resp = api.post(f"/api/leases/{lease_id}/renew/", {}, format="json")
    assert renew_resp.status_code == 409
    assert renew_resp.data["code"] == "LEASE_CONFLICT"

    # Post-check DB: lease closed
    lease = Lease.objects.get(pk=lease_id)
    assert lease.closed_at is not None


@pytest.mark.django_db
def test_t045_smoke_08_audit_failure_rollback(world, monkeypatch):
    """Scenario 8: Audit failure transaction rollback - Audit write failure rolls back state."""
    claim_resp = claim_frame(world, "reviewer")
    lease_id = claim_resp.data["lease"]["id"]
    frame_id = claim_resp.data["frame"]["id"]

    api = client(world["reviewer"])
    issue_resp = api.post(
        "/api/issues/",
        {
            "frame_id": frame_id,
            "lease_id": lease_id,
            "family": "E1",
            "description": "Rollback test",
            "anchor": {
                "kind": "manual_region",
                "objects": [],
                "bbox": {"x1": 1, "y1": 1, "x2": 10, "y2": 10},
                "policy_version": "anchor-v1",
            },
        },
        format="json",
    )
    assert issue_resp.status_code == 201
    issue_id = issue_resp.data["id"]

    def fail_audit(**_kwargs):
        raise RuntimeError("Simulated audit service failure")

    monkeypatch.setattr("review.decision_service.append_audit_event", fail_audit)

    with pytest.raises(RuntimeError, match="Simulated audit service failure"):
        api.post(
            f"/api/issues/{issue_id}/decisions/",
            {
                "lease_id": lease_id,
                "action": "confirm",
                "revision": world["run"].snapshot.revision_sha256,
                "family": "E1",
                "severity": "medium",
            },
            format="json",
        )

    # Post-check DB: Zero decisions recorded, Issue state remains IN_REVIEW (not CONFIRMED)
    assert ReviewDecision.objects.filter(issue_id=issue_id).count() == 0
    issue = Issue.objects.get(pk=issue_id)
    assert issue.state == Issue.State.IN_REVIEW
