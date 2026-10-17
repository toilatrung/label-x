"""Issue #395: PostgreSQL review contracts; browser cases stay explicitly unbound."""

# ruff: noqa: F811 - imported pytest fixtures are intentionally injected by name
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
import redis
from django.db import connection, connections
from django.utils import timezone

from accounts.models import Role, RoleAssignment
from audit.models import AuditEvent
from guideline.models import GuidelineRule, GuidelineVersion
from review.models import (
    DecisionCase,
    FrameReview,
    GuidelineGap,
    Issue,
    Lease,
    ReviewDecision,
    ReworkRecheck,
    ReworkRequest,
    ReworkVerification,
)
from runs.models import QCRun
from snapshots.orchestration import compute_job_revision, create_snapshot_from_cvat
from tests.phase_mvp.test_p0_snapshot import DiskBlobStore
from tests.review.test_escalation_adjudication import adj_world  # noqa: F401
from tests.review.test_issues_decisions import claim, decide, manual
from tests.review.test_queue_lease import client, next_url, world  # noqa: F401
from tests.review.test_rework import confirmed, create_request  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def p3_policy(settings, snapshot_media_urls):
    settings.REVIEW_LEASE_TTL_SECONDS = 60
    settings.REVIEW_INCOMPLETE_RESERVATION_SECONDS = 120
    settings.CVAT_BASE_URL = "http://localhost:8080"


def _manual(user, lease_id, frame_id):
    response = client(user).post(
        "/api/issues/",
        {
            "frame_id": frame_id,
            "lease_id": lease_id,
            "family": "E1",
            "anchor": {
                "kind": "manual_region",
                "objects": [],
                "bbox": {"x1": 1, "y1": 1, "x2": 10, "y2": 10},
                "policy_version": "anchor-v1",
            },
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data["id"]


def test_rev02_parallel_postgresql_claim_owner_and_expired_decisions_without_redis(
    world, monkeypatch
):
    assert connection.vendor == "postgresql", "REV-02 requires real PostgreSQL transactions"

    def forbidden_redis(*args, **kwargs):
        raise AssertionError("Frame lease correctness must not depend on Redis")

    monkeypatch.setattr(redis, "from_url", forbidden_redis)
    monkeypatch.setattr(redis.Redis, "from_url", forbidden_redis)
    barrier = Barrier(2)

    def race(user):
        connections.close_all()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                backend_pid = cursor.fetchone()[0]
            barrier.wait(timeout=20)
            response = client(user).post(next_url(), {"run_id": world["run"].pk}, format="json")
            return user, backend_pid, response.status_code, response.data
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(race, (world["reviewer"], world["other"])))
    assert len({result[1] for result in results}) == 2
    assert sorted(result[2] for result in results) == [200, 204]
    winner, _, _, granted = next(result for result in results if result[2] == 200)
    loser = next(result[0] for result in results if result[2] == 204)
    lease_id, frame_id = granted["lease"]["id"], granted["frame"]["id"]
    assert Lease.objects.filter(closed_at__isnull=True).count() == 1
    assert Lease.objects.get(pk=lease_id).holder_id == winner.pk
    issue_id = _manual(winner, lease_id, frame_id)
    body = {
        "lease_id": lease_id,
        "action": "confirm",
        "family": "E1",
        "severity": "medium",
        "reason": "Reviewed synthetic region",
        "revision": world["run"].snapshot.revision_sha256,
    }
    wrong = client(loser).post(f"/api/issues/{issue_id}/decisions/", body, format="json")
    assert wrong.status_code == 409 and wrong.data["code"] == "LEASE_CONFLICT"
    Lease.objects.filter(pk=lease_id).update(expires_at=timezone.now() - timedelta(seconds=1))
    expired = client(winner).post(f"/api/issues/{issue_id}/decisions/", body, format="json")
    assert expired.status_code == 409 and expired.data["code"] == "LEASE_CONFLICT"
    assert not ReviewDecision.objects.filter(issue_id=issue_id).exists()
    assert Issue.objects.get(pk=issue_id).state == Issue.State.IN_REVIEW


def test_rev03_support_validation_audit_rollback_and_no_frame_completion(world, monkeypatch):
    lease_id, frame_id = claim(world)
    issue_id, _ = manual(world, lease_id, frame_id)
    api = client(world["reviewer"])
    common = {"lease_id": lease_id, "revision": world["run"].snapshot.revision_sha256}
    for fields in (
        {"action": "confirm", "family": "E1", "reason": "checked"},
        {"action": "reject", "reason": ""},
        {"action": "uncertain", "reason": ""},
    ):
        rejected = api.post(
            f"/api/issues/{issue_id}/decisions/", {**common, **fields}, format="json"
        )
        assert rejected.status_code == 400, rejected.data
    blocked = api.post(f"/api/frames/{frame_id}/complete/", {"lease_id": lease_id}, format="json")
    assert blocked.status_code == 422
    assert blocked.data["details"]["undecided_issue_ids"] == [issue_id]

    def fail_audit(**kwargs):
        raise RuntimeError("issue-395 injected audit failure")

    monkeypatch.setattr("review.decision_service.append_audit_event", fail_audit)
    with pytest.raises(RuntimeError, match="issue-395 injected"):
        decide(world, lease_id, issue_id, reason="Synthetic evidence reviewed")
    assert ReviewDecision.objects.filter(issue_id=issue_id).count() == 0
    assert not AuditEvent.objects.filter(action="issue.confirm", object_id=str(issue_id)).exists()
    assert Issue.objects.get(pk=issue_id).state == Issue.State.IN_REVIEW
    assert FrameReview.objects.get(pk=frame_id).state == FrameReview.State.IN_REVIEW
    assert Lease.objects.get(pk=lease_id).closed_at is None
    still_blocked = api.post(
        f"/api/frames/{frame_id}/complete/", {"lease_id": lease_id}, format="json"
    )
    assert still_blocked.status_code == 422
    assert not AuditEvent.objects.filter(action="frame.complete", object_id=str(frame_id)).exists()


def test_esc01_authorized_adjudication_preserves_history_and_guideline_gap(adj_world):
    issue = adj_world["issue"]
    evidence = [
        {
            "kind": "synthetic",
            "frame": 0,
            "source_revision": adj_world["run"].snapshot.revision_sha256,
        }
    ]
    issue.reviewer_evidence = evidence
    issue.save(update_fields=["reviewer_evidence"])
    original = ReviewDecision.objects.filter(pk=adj_world["escalator_decision"].pk).values().get()
    url = f"/api/issues/{issue.pk}/adjudications/"
    body = {"outcome": "confirm", "rule_id": "RULE-01", "reason": "Approved rule review"}
    forbidden = client(adj_world["other"]).post(url, body, format="json")
    assert forbidden.status_code == 403
    assert not DecisionCase.objects.filter(issue=issue).exists()

    changed = GuidelineVersion.objects.create(
        version_tag="p3-guide-v2", name="New policy", file_checksum="b" * 64
    )
    GuidelineRule.objects.create(
        version=changed, rule_id="NEW-ONLY", section="2", content="New scope"
    )
    invalid = client(adj_world["qa_lead"]).post(url, {**body, "rule_id": "NEW-ONLY"}, format="json")
    assert invalid.status_code == 422, invalid.data
    gap = client(adj_world["qa_lead"]).post(
        url,
        {
            **body,
            "outcome": "guideline_gap",
            "reason": "Current guideline cannot resolve this evidence",
        },
        format="json",
    )
    assert gap.status_code == 201, gap.data
    issue.refresh_from_db()
    assert issue.state == Issue.State.ESCALATED
    assert issue.reviewer_evidence == evidence
    recorded_gap = GuidelineGap.objects.get(issue=issue)
    assert recorded_gap.status == GuidelineGap.Status.OPEN
    assert recorded_gap.guideline_version == "guide"
    assert not ReworkRequest.objects.filter(issue=issue).exists()
    assert ReviewDecision.objects.filter(pk=original["id"]).values().get() == original
    assert DecisionCase.objects.get(issue=issue).review_decision_id is not None


class CvatR2:
    """CVAT R2 fixture; R1 is the original locked snapshot in world."""

    def __init__(self):
        self.annotation_reads = 0

    def get_project(self, project_id):
        return {"id": project_id}

    def get_task(self, task_id):
        return {"id": task_id, "project_id": 42}

    def get_job(self, job_id):
        assert job_id == 100
        return {
            "id": 100,
            "task_id": 200,
            "start_frame": 0,
            "updated_date": "2026-10-17T01:00:00Z",
            "assignee": {"id": 702},
        }

    def list_labels(self, *, project_id):
        return [{"id": 1, "name": "car"}]

    def get_job_annotations(self, job_id):
        self.annotation_reads += 1
        return {
            "shapes": [
                {"id": 91, "type": "rectangle", "frame": 0, "label_id": 1, "points": [2, 2, 11, 11]}
            ],
            "tracks": [],
        }

    def get_job_data_meta(self, job_id):
        return {"start_frame": 0, "frames": [{"name": "0.jpg", "width": 100, "height": 100}]}

    def get_job_frame(self, job_id, frame_index):
        assert (job_id, frame_index) == (100, 0)
        return b"frame-0", "image/jpeg"


def test_rwk01_new_cvat_revision_same_person_guard_and_failed_verify_preserve_r1(
    confirmed,
    world,
    monkeypatch,
    tmp_path,
):
    from review import rework_service

    original_snapshot = world["run"].snapshot
    original_payload = copy.deepcopy(original_snapshot.normalized_json)
    original_digest = original_snapshot.revision_sha256
    created = create_request(confirmed, world)
    assert created.status_code == 201, created.data
    rework = ReworkRequest.objects.get(pk=created.data["id"])
    url = f"/api/rework/{rework.pk}"
    unchanged = client(world["author"]).post(
        f"{url}/submitted/", {"cvat_revision": original_digest}, format="json"
    )
    assert unchanged.status_code == 409 and unchanged.data["code"] == "REVISION_UNCHANGED"
    assert not ReworkRecheck.objects.filter(rework=rework).exists()
    source = CvatR2()
    revision = compute_job_revision(
        dataset_id=42,
        cvat_job_id=100,
        client=source,
        guideline_version="guide",
        legacy_reference=True,
    )
    assert revision != original_digest

    def export(**kwargs):
        return create_snapshot_from_cvat(**kwargs, client=source, storage=DiskBlobStore(tmp_path))

    monkeypatch.setattr(rework_service, "create_snapshot_from_cvat", export)
    submitted = client(world["author"]).post(
        f"{url}/submitted/", {"cvat_revision": revision}, format="json"
    )
    assert submitted.status_code == 202, submitted.data
    rework.refresh_from_db()
    assert source.annotation_reads >= 3  # preview plus two authoritative export reads
    assert rework.submitted_revision == revision == rework.recheck_snapshot.revision_sha256
    assert rework.recheck_run.snapshot_id == rework.recheck_snapshot_id
    assert rework.recheck_run.origin_run_id == world["run"].pk
    assert ReworkRecheck.objects.get(rework=rework).revision == revision
    body = {"passed": True, "revision": revision}
    for failed_status in (QCRun.Status.PARTIAL, QCRun.Status.FAILED, QCRun.Status.CANCELLED):
        QCRun.objects.filter(pk=rework.recheck_run_id).update(status=failed_status)
        blocked = client(world["other"]).post(f"{url}/verify/", body, format="json")
        assert blocked.status_code == 409
        assert not ReworkVerification.objects.filter(rework=rework).exists()
    QCRun.objects.filter(pk=rework.recheck_run_id).update(status=QCRun.Status.COMPLETED)
    RoleAssignment.objects.create(user=world["author"], role=Role.REVIEWER, dataset_id=42)
    same = client(world["author"]).post(f"{url}/verify/", body, format="json")
    assert same.status_code == 403 and same.data["code"] == "SAME_REQUESTER_APPROVER"
    wrong = client(world["other"]).post(
        f"{url}/verify/", {**body, "revision": original_digest}, format="json"
    )
    assert wrong.status_code == 409
    failed = client(world["other"]).post(
        f"{url}/verify/",
        {
            "passed": False,
            "revision": revision,
            "reason": "Recheck geometry still violates guideline",
        },
        format="json",
    )
    assert failed.status_code == 200, failed.data
    rework.refresh_from_db()
    confirmed.refresh_from_db()
    original_snapshot.refresh_from_db()
    assert rework.status == ReworkRequest.Status.FIX_PENDING
    assert confirmed.state == Issue.State.FIX_PENDING
    assert ReworkVerification.objects.get(rework=rework).outcome == ReworkVerification.Outcome.FAIL
    assert original_snapshot.revision_sha256 == original_digest
    assert original_snapshot.normalized_json == original_payload
