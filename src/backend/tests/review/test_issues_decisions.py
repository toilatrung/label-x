"""T-035 API and PostgreSQL decision-writer/lease integration evidence."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, local
from time import sleep
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.core.files.storage import storages
from django.db import DatabaseError, connection, connections, transaction
from django.utils import timezone

from accounts.models import CvatIdentity, Role, RoleAssignment
from audit.models import AuditEvent
from guideline.models import GuidelineRule, GuidelineVersion
from orchestration.models import CandidateRecord, LedgerUnit, ShardCommit
from review import decision_service
from review.models import FrameReview, Issue, Lease, ReviewDecision
from runs.models import EngineResult, RunRankingEntry
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


def claim(world, user="reviewer"):
    response = client(world[user]).post(next_url(), {"run_id": world["run"].pk}, format="json")
    assert response.status_code == 200, response.data
    return response.data["lease"]["id"], response.data["frame"]["id"]


def manual(world, lease_id, frame_id, *, key=None):
    request_key = key or str(uuid4())
    response = client(world["reviewer"]).post(
        "/api/issues/",
        {
            "frame_id": frame_id,
            "lease_id": lease_id,
            "family": "E1",
            "description": "Missing object in this region",
            "anchor": {
                "kind": "manual_region",
                "objects": [],
                "bbox": {"x1": 1, "y1": 1, "x2": 10, "y2": 10},
                "policy_version": "anchor-v1",
            },
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=request_key,
    )
    assert response.status_code == 201, response.data
    return response.data["id"], request_key


def decide(world, lease_id, issue_id, *, action="confirm", key=None, user="reviewer", **extra):
    body = {
        "lease_id": lease_id,
        "action": action,
        "revision": world["run"].snapshot.revision_sha256,
        **extra,
    }
    if action == "confirm":
        body.setdefault("family", "E1")
        body.setdefault("severity", "medium")
    elif action in {"reject", "uncertain", "escalate"}:
        body.setdefault("reason", "Human review reason")
    kwargs = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
    return client(world[user]).post(
        f"/api/issues/{issue_id}/decisions/", body, format="json", **kwargs
    )


@pytest.mark.django_db
def test_manual_confirm_append_only_audit_idempotency_and_lineage(world):
    lease_id, frame_id = claim(world)
    issue_id, manual_key = manual(world, lease_id, frame_id)
    assert Issue.objects.get(pk=issue_id).candidate_id is None
    assert Issue.objects.get(pk=issue_id).anchor["objects"][0]["namespace"] == "reviewer_region"
    same_manual = client(world["reviewer"]).post(
        "/api/issues/",
        {
            "frame_id": frame_id,
            "lease_id": lease_id,
            "family": "E1",
            "description": "Missing object in this region",
            "anchor": {
                "kind": "manual_region",
                "objects": [],
                "bbox": {"x1": 1, "y1": 1, "x2": 10, "y2": 10},
                "policy_version": "anchor-v1",
            },
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=manual_key,
    )
    assert same_manual.status_code == 201 and same_manual.data["id"] == issue_id
    key = str(uuid4())
    first = decide(world, lease_id, issue_id, key=key)
    assert first.status_code == 201, first.data
    repeat = decide(world, lease_id, issue_id, key=key)
    assert repeat.status_code == 201 and repeat.data["id"] == first.data["id"]
    assert ReviewDecision.objects.filter(issue_id=issue_id).count() == 1
    saved = ReviewDecision.objects.get(issue_id=issue_id)
    assert saved.actor_id == world["reviewer"].pk
    assert saved.actor_role == Role.REVIEWER
    assert saved.reference_version is None
    assert saved.reference_match_status == "not_evaluated"
    assert saved.reference_error_ids == []
    assert saved.audit_event_id == first.data["audit_event_id"]
    assert AuditEvent.objects.filter(pk=saved.audit_event_id, action="issue.confirm").exists()
    assert Issue.objects.get(pk=issue_id).state == Issue.State.CONFIRMED
    with pytest.raises(ValueError, match="append-only"):
        saved.save()
    with pytest.raises(ValueError, match="append-only"):
        ReviewDecision.objects.filter(pk=saved.pk).update(reason="tamper")
    assert connection.vendor == "postgresql"
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE review_decision SET reason = %s WHERE id = %s", ["tamper", saved.pk]
            )
    saved.refresh_from_db()
    assert saved.reason == ""
    conflict = decide(world, lease_id, issue_id, key=key, severity="critical")
    assert conflict.status_code == 409 and conflict.data["code"] == "IDEMPOTENCY_KEY_REUSED"
    detail = client(world["reviewer"]).get(f"/api/issues/{issue_id}/")
    assert detail.status_code == 200
    assert detail.data["review_decisions"][0]["id"] == saved.pk


@pytest.mark.django_db
def test_manual_object_uses_cvat_shape_id_without_job_prefix(world):
    lease_id, frame_id = claim(world)
    api = client(world["reviewer"])
    body = {
        "frame_id": frame_id,
        "lease_id": lease_id,
        "family": "E2",
        "anchor": {
            "kind": "manual_object",
            "objects": [{"namespace": "cvat_shape", "id": "91"}],
            "policy_version": "anchor-v1",
        },
    }
    created = api.post("/api/issues/", body, format="json")
    assert created.status_code == 201, created.data
    assert created.data["anchor"]["objects"] == [{"namespace": "cvat_shape", "id": "91"}]
    assert Issue.objects.get(pk=created.data["id"]).origin == Issue.Origin.REVIEWER
    duplicate = api.post("/api/issues/", body, format="json")
    assert duplicate.status_code == 409 and duplicate.data["code"] == "ISSUE_EXISTS"
    body["anchor"]["objects"] = [{"namespace": "cvat_shape", "id": "100:91"}]
    wrong = api.post("/api/issues/", body, format="json")
    assert wrong.status_code == 400 and wrong.data["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_decision_persists_snapshot_revision_rule_and_reason(world):
    version = GuidelineVersion.objects.create(
        version_tag="guide", name="Review guideline", file_checksum="d" * 64
    )
    GuidelineRule.objects.create(
        version=version, rule_id="R-01", section="1", content="Check region"
    )
    lease_id, frame_id = claim(world)
    issue_id, _ = manual(world, lease_id, frame_id)
    wrong_revision = decide(world, lease_id, issue_id, revision="old", rule_id="R-01")
    assert wrong_revision.status_code == 409
    unknown_rule = decide(world, lease_id, issue_id, rule_id="R-OTHER")
    assert unknown_rule.status_code == 422
    result = decide(world, lease_id, issue_id, rule_id="R-01", reason="Confirmed by reviewer")
    assert result.status_code == 201, result.data
    saved = ReviewDecision.objects.get(issue_id=issue_id)
    assert saved.actor_id == world["reviewer"].pk
    assert saved.revision == world["run"].snapshot.revision_sha256
    assert saved.rule_ids == ["R-01"]
    assert saved.reason == "Confirmed by reviewer"
    audit = AuditEvent.objects.get(pk=saved.audit_event_id)
    assert audit.after["rule_ids"] == ["R-01"]
    assert audit.reason == "Confirmed by reviewer"


@pytest.mark.django_db
def test_engine_candidate_materializes_one_issue_without_mutating_candidate(world):
    run = world["run"]
    shard = ShardCommit.objects.create(
        idempotency_key="t035-shard",
        run=run,
        snapshot_id=run.snapshot_id,
        engine="detector",
        engine_version="v1",
        shard_index=0,
        output_sha256="a" * 64,
    )
    evidence = {
        "engine": "detector",
        "rule_id": None,
        "expected": "person",
        "actual": None,
        "prediction_bbox": {"x1": 1, "y1": 1, "x2": 10, "y2": 10},
        "prediction_class": "person",
        "confidence": 0.9,
        "iou": None,
    }
    candidate = CandidateRecord.objects.create(
        run=run,
        dedup_key="b" * 64,
        shard=shard,
        engine="detector",
        engine_version="v1",
        family="E1",
        cvat_task_id=200,
        frame_number=0,
        anchor={
            "kind": "prediction_region",
            "objects": [{"namespace": "detector", "id": "1:0"}],
            "rule_id": None,
            "bbox": {"x1": 1, "y1": 1, "x2": 10, "y2": 10},
            "policy_version": "anchor-v1",
        },
        policy_version="anchor-v1",
        evidence=evidence,
        evidence_sha256="c" * 64,
    )
    LedgerUnit.objects.create(
        run=run,
        engine="detector",
        kind="frame",
        cvat_task_id=200,
        frame_number=0,
        outcome="failed",
    )
    EngineResult.objects.create(run=run, engine="detector", status="failed")
    RunRankingEntry.objects.filter(ranking__run=run).update(missing_evidence=True)
    lease_id, frame_id = claim(world)
    assert lease_id > 0
    assert Issue.objects.filter(candidate=candidate, frame_review_id=frame_id).count() == 1
    read = client(world["reviewer"]).get(f"/api/frames/{frame_id}/issues/")
    assert read.status_code == 200, read.data
    assert read.data["frame"]["image_url"] == "https://storage.test/0.jpg"
    assert read.data["issues"][0]["evidence"] == [evidence]
    assert read.data["issues"][0]["state"] == Issue.State.IN_REVIEW
    assert read.data["frame"]["frame_key"] == {"cvat_task_id": 200, "frame_number": 0}
    assert read.data["frame"]["missing_evidence"] is True
    assert read.data["engines"][0]["status"] == "failed"
    client(world["reviewer"]).post(next_url(), {"run_id": run.pk}, format="json")
    assert Issue.objects.filter(candidate=candidate).count() == 1
    candidate.refresh_from_db()
    assert candidate.evidence == evidence


@pytest.mark.django_db
@pytest.mark.parametrize("action", ["reject", "uncertain", "escalate"])
def test_reason_actions_and_invalid_reason(world, action):
    lease_id, frame_id = claim(world)
    issue_id, _ = manual(world, lease_id, frame_id)
    missing = decide(world, lease_id, issue_id, action=action, reason="")
    assert missing.status_code == 400
    response = decide(world, lease_id, issue_id, action=action)
    assert response.status_code == 201, response.data
    expected = Issue.State.REJECTED if action == "reject" else Issue.State.ESCALATED
    assert Issue.objects.get(pk=issue_id).state == expected
    again = decide(world, lease_id, issue_id, action=action)
    assert again.status_code == 409 and again.data["code"] == "INVALID_TRANSITION"


@pytest.mark.django_db
def test_complete_undecided_then_idempotent_and_request_fix_not_accepted(world):
    lease_id, frame_id = claim(world)
    issue_id, manual_key = manual(world, lease_id, frame_id)
    api = client(world["reviewer"])
    denied = api.post(f"/api/frames/{frame_id}/complete/", {"lease_id": lease_id}, format="json")
    assert denied.status_code == 422
    assert denied.data["details"]["undecided_issue_ids"] == [issue_id]
    decision_key = str(uuid4())
    decided = decide(world, lease_id, issue_id, key=decision_key)
    assert decided.status_code == 201
    blocked = decide(world, lease_id, issue_id, action="request_fix")
    assert blocked.status_code == 400 and blocked.data["code"] == "VALIDATION_ERROR"
    assert Issue.objects.get(pk=issue_id).state == Issue.State.CONFIRMED
    assert ReviewDecision.objects.filter(issue_id=issue_id).count() == 1
    first = api.post(f"/api/frames/{frame_id}/complete/", {"lease_id": lease_id}, format="json")
    assert first.status_code == 200, first.data
    assert first.data["image_url"] == "https://storage.test/0.jpg"
    retry = api.post(f"/api/frames/{frame_id}/complete/", {"lease_id": lease_id}, format="json")
    assert retry.status_code == 200
    assert retry.data["image_url"] == "https://storage.test/0.jpg"
    assert Lease.objects.get(pk=lease_id).closed_at is not None
    assert FrameReview.objects.get(pk=frame_id).state == FrameReview.State.REVIEWED
    assert AuditEvent.objects.filter(action="frame.complete", object_id=str(frame_id)).count() == 1
    # A lost response can be retried after complete closed the lease. The
    # server rechecks role/scope/identity but returns the original effects.
    assert manual(world, lease_id, frame_id, key=manual_key)[0] == issue_id
    replay = decide(world, lease_id, issue_id, key=decision_key)
    assert replay.status_code == 201 and replay.data["id"] == decided.data["id"]
    assert Issue.objects.filter(frame_review_id=frame_id).count() == 1
    assert ReviewDecision.objects.filter(issue_id=issue_id).count() == 1
    assert AuditEvent.objects.filter(action="issue.confirm", object_id=str(issue_id)).count() == 1
    RoleAssignment.objects.filter(user=world["reviewer"], dataset_id=42).delete()
    denied_replay = decide(world, lease_id, issue_id, key=decision_key)
    assert denied_replay.status_code == 403 and denied_replay.data["code"] == "FORBIDDEN"


@pytest.mark.django_db
def test_lease_identity_scope_self_review_and_audit(world):
    lease_id, frame_id = claim(world)
    issue_id, _ = manual(world, lease_id, frame_id)
    other = decide(world, lease_id, issue_id, user="other")
    assert other.status_code == 409 and other.data["code"] == "LEASE_CONFLICT"
    missing = User.objects.create_user("t035-no-identity")
    RoleAssignment.objects.create(user=missing, role=Role.REVIEWER, dataset_id=42)
    missing_response = decide(world, lease_id, issue_id, user="reviewer")
    assert missing_response.status_code == 201
    # A direct API call from the unmapped account cannot bypass the identity guard.
    denied = client(missing).post(
        f"/api/issues/{issue_id}/decisions/",
        {"lease_id": lease_id, "action": "reject", "reason": "test", "revision": "x"},
        format="json",
    )
    assert denied.status_code == 403 and denied.data["code"] == "IDENTITY_MAPPING_MISSING"
    assert AuditEvent.objects.filter(action="issues.decide.rejected", actor=missing).exists()
    outside = User.objects.create_user("t035-outside")
    RoleAssignment.objects.create(user=outside, role=Role.REVIEWER, dataset_id=99)
    CvatIdentity.objects.create(
        user=outside,
        cvat_user_id=999,
        employee=CvatIdentity.objects.get(user=world["other"]).employee,
    )
    outside_response = client(outside).get(f"/api/issues/{issue_id}/")
    assert outside_response.status_code == 403 and outside_response.data["code"] == "OUT_OF_SCOPE"
    author_alias = User.objects.create_user("t035-author-alias")
    RoleAssignment.objects.create(user=author_alias, role=Role.REVIEWER, dataset_id=42)
    CvatIdentity.objects.create(
        user=author_alias,
        cvat_user_id=1001,
        employee=CvatIdentity.objects.get(user=world["author"]).employee,
    )
    self_response = client(author_alias).get(f"/api/issues/{issue_id}/")
    assert self_response.status_code == 403
    assert self_response.data["code"] == "SELF_REVIEW_FORBIDDEN"
    assert AuditEvent.objects.filter(action="issues.detail.rejected", actor=author_alias).exists()


@pytest.mark.django_db
def test_direct_decision_api_rechecks_snapshot_assignee_even_with_lease(world):
    lease_id, frame_id = claim(world)
    issue_id, _ = manual(world, lease_id, frame_id)
    author_alias = User.objects.create_user("t035-direct-alias")
    RoleAssignment.objects.create(user=author_alias, role=Role.REVIEWER, dataset_id=42)
    CvatIdentity.objects.create(
        user=author_alias,
        cvat_user_id=1201,
        employee=CvatIdentity.objects.get(user=world["author"]).employee,
    )
    # Deliberately seed a holder that claim_next would never grant. The write
    # endpoint must still reject the same natural person as snapshot assignee.
    Lease.objects.filter(pk=lease_id).update(holder=author_alias)
    response = client(author_alias).post(
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
    assert response.status_code == 403 and response.data["code"] == "SELF_REVIEW_FORBIDDEN"
    assert ReviewDecision.objects.filter(issue_id=issue_id).count() == 0
    assert AuditEvent.objects.filter(action="issues.decide.rejected", actor=author_alias).exists()


@pytest.mark.django_db
def test_audit_failure_rolls_back_decision_and_issue_state(world, monkeypatch):
    lease_id, frame_id = claim(world)
    issue_id, _ = manual(world, lease_id, frame_id)

    def fail_audit(**_kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr("review.decision_service.append_audit_event", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        decide(world, lease_id, issue_id)
    assert ReviewDecision.objects.filter(issue_id=issue_id).count() == 0
    assert Issue.objects.get(pk=issue_id).state == Issue.State.IN_REVIEW
    assert AuditEvent.objects.filter(action="issue.confirm", object_id=str(issue_id)).count() == 0


@pytest.mark.django_db
def test_committed_decision_survives_expiry_and_resumes(world):
    lease_id, frame_id = claim(world)
    issue_id, _ = manual(world, lease_id, frame_id)
    assert decide(world, lease_id, issue_id).status_code == 201
    Lease.objects.filter(pk=lease_id).update(expires_at=timezone.now() - timedelta(seconds=1))
    expired = client(world["reviewer"]).post(f"/api/leases/{lease_id}/renew/", {})
    assert expired.status_code == 409
    frame = FrameReview.objects.get(pk=frame_id)
    assert frame.state == FrameReview.State.INCOMPLETE
    assert frame.previous_reviewer_id == world["reviewer"].pk
    assert Issue.objects.get(pk=issue_id).state == Issue.State.CONFIRMED
    assert ReviewDecision.objects.filter(issue_id=issue_id).count() == 1
    resumed = client(world["reviewer"]).post(next_url(), {"run_id": world["run"].pk})
    assert resumed.status_code == 200 and resumed.data["resumed"] is True


def _thread_call(barrier, user, path, body):
    connections.close_all()
    try:
        barrier.wait(timeout=15)
        response = client(user).post(path, body, format="json")
        return response.status_code, response.data
    finally:
        connections.close_all()


@pytest.mark.django_db(transaction=True)
def test_postgres_barrier_decision_writer_vs_expiry(world):
    assert connection.vendor == "postgresql"
    lease_id, frame_id = claim(world)
    issue_id, _ = manual(world, lease_id, frame_id)
    Lease.objects.filter(pk=lease_id).update(expires_at=timezone.now() - timedelta(seconds=1))
    barrier = Barrier(2)
    decision_body = {
        "lease_id": lease_id,
        "action": "confirm",
        "revision": world["run"].snapshot.revision_sha256,
        "family": "E1",
        "severity": "medium",
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(
            _thread_call,
            barrier,
            world["reviewer"],
            f"/api/issues/{issue_id}/decisions/",
            decision_body,
        )
        expirer = pool.submit(
            _thread_call, barrier, world["reviewer"], f"/api/leases/{lease_id}/renew/", {}
        )
        writer_result, expiry_result = writer.result(), expirer.result()
    assert writer_result[0] == 409 and expiry_result[0] == 409
    assert ReviewDecision.objects.filter(issue_id=issue_id).count() == 0
    assert Issue.objects.get(pk=issue_id).state == Issue.State.PENDING_REVIEW
    assert FrameReview.objects.get(pk=frame_id).state == FrameReview.State.UNREVIEWED
    assert Lease.objects.get(pk=lease_id).closed_at is not None


@pytest.mark.django_db(transaction=True)
def test_postgres_writer_commits_while_expiry_waits_for_run_lock(world, monkeypatch):
    assert connection.vendor == "postgresql"
    lease_id, frame_id = claim(world)
    issue_id, _ = manual(world, lease_id, frame_id)
    before_expiry = timezone.now()
    after_expiry = before_expiry + timedelta(seconds=2)
    Lease.objects.filter(pk=lease_id).update(expires_at=before_expiry + timedelta(seconds=1))
    clock_role = local()

    def clock():
        return after_expiry if getattr(clock_role, "value", None) == "expirer" else before_expiry

    monkeypatch.setattr("review.decision_service._now", clock)
    monkeypatch.setattr("review.services._now", clock)
    append_audit = decision_service.append_audit_event
    overlap = Barrier(2)

    def pause_writer_at_audit(**kwargs):
        # Writer already owns the User/QCRun locks; expiry now contends for them.
        overlap.wait(timeout=15)
        sleep(0.05)
        return append_audit(**kwargs)

    monkeypatch.setattr("review.decision_service.append_audit_event", pause_writer_at_audit)
    body = {
        "lease_id": lease_id,
        "action": "confirm",
        "revision": world["run"].snapshot.revision_sha256,
        "family": "E1",
        "severity": "medium",
    }

    def writer():
        clock_role.value = "writer"
        connections.close_all()
        try:
            response = client(world["reviewer"]).post(
                f"/api/issues/{issue_id}/decisions/", body, format="json"
            )
            return response.status_code
        finally:
            connections.close_all()

    def expirer():
        clock_role.value = "expirer"
        connections.close_all()
        try:
            overlap.wait(timeout=15)
            response = client(world["reviewer"]).post(
                f"/api/leases/{lease_id}/renew/", {}, format="json"
            )
            return response.status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer_result = pool.submit(writer)
        expiry_result = pool.submit(expirer)
        assert writer_result.result() == 201
        assert expiry_result.result() == 409
    assert ReviewDecision.objects.filter(issue_id=issue_id, action="confirm").count() == 1
    assert Issue.objects.get(pk=issue_id).state == Issue.State.CONFIRMED
    frame = FrameReview.objects.get(pk=frame_id)
    assert frame.state == FrameReview.State.INCOMPLETE
    assert frame.previous_reviewer_id == world["reviewer"].pk
    lease = Lease.objects.get(pk=lease_id)
    assert lease.holder_id == world["reviewer"].pk and lease.closed_at is not None


@pytest.mark.django_db(transaction=True)
def test_postgres_barrier_decision_writer_vs_renew(world):
    assert connection.vendor == "postgresql"
    lease_id, frame_id = claim(world)
    issue_id, _ = manual(world, lease_id, frame_id)
    barrier = Barrier(2)
    decision_body = {
        "lease_id": lease_id,
        "action": "confirm",
        "revision": world["run"].snapshot.revision_sha256,
        "family": "E1",
        "severity": "medium",
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(
            _thread_call,
            barrier,
            world["reviewer"],
            f"/api/issues/{issue_id}/decisions/",
            decision_body,
        )
        renewer = pool.submit(
            _thread_call, barrier, world["reviewer"], f"/api/leases/{lease_id}/renew/", {}
        )
        writer_result, renew_result = writer.result(), renewer.result()
    assert writer_result[0] == 201 and renew_result[0] == 200
    assert ReviewDecision.objects.filter(issue_id=issue_id).count() == 1
    assert Issue.objects.get(pk=issue_id).state == Issue.State.CONFIRMED
    assert FrameReview.objects.get(pk=frame_id).state == FrameReview.State.IN_REVIEW
    lease = Lease.objects.get(pk=lease_id)
    assert lease.closed_at is None and lease.holder_id == world["reviewer"].pk


@pytest.mark.django_db(transaction=True)
def test_postgres_barrier_decision_writer_vs_other_reviewer_claim(world):
    assert connection.vendor == "postgresql"
    lease_id, frame_id = claim(world)
    issue_id, _ = manual(world, lease_id, frame_id)
    barrier = Barrier(2)
    decision_body = {
        "lease_id": lease_id,
        "action": "confirm",
        "revision": world["run"].snapshot.revision_sha256,
        "family": "E1",
        "severity": "medium",
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(
            _thread_call,
            barrier,
            world["reviewer"],
            f"/api/issues/{issue_id}/decisions/",
            decision_body,
        )
        claimer = pool.submit(
            _thread_call,
            barrier,
            world["other"],
            next_url(),
            {"run_id": world["run"].pk},
        )
        writer_result, claim_result = writer.result(), claimer.result()
    assert writer_result[0] == 201 and claim_result[0] == 204
    assert ReviewDecision.objects.filter(issue_id=issue_id).count() == 1
    assert Issue.objects.get(pk=issue_id).state == Issue.State.CONFIRMED
    assert FrameReview.objects.get(pk=frame_id).state == FrameReview.State.IN_REVIEW
    lease = Lease.objects.get(pk=lease_id)
    assert lease.closed_at is None and lease.holder_id == world["reviewer"].pk
