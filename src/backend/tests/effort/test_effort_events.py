from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.files.storage import storages
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import CvatIdentity, Role, RoleAssignment
from effort.models import EffortEvent
from review.models import FrameReview, ReviewDecision
from runs.models import ConfigVersion, QCRun
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot

pytestmark = pytest.mark.django_db(transaction=True)
pytest_plugins = ["tests.review.test_queue_lease"]


@pytest.fixture(autouse=True)
def snapshot_storage_mock(monkeypatch):
    monkeypatch.setattr(
        storages["snapshots"],
        "url",
        lambda name: f"https://storage.test/{name}",
    )


def _user(username: str, role: Role, dataset_id: int | None, *, identity: bool = True):
    user = get_user_model().objects.create_user(username=username)
    RoleAssignment.objects.create(user=user, role=role, dataset_id=dataset_id)
    if identity:
        CvatIdentity.objects.create(
            user=user,
            cvat_user_id=abs(hash(username)) % 1_000_000 + 1,
            cvat_username=username,
        )
    return user


def _frame(creator, dataset_id: int = 42):
    snapshot = create_locked_snapshot(
        dataset_id=dataset_id,
        created_by=creator,
        taxonomy_version="taxonomy-v1",
        guideline_version="guideline-v1",
        jobs=[
            JobExport(
                cvat_job_id=17 + dataset_id,
                cvat_task_id=9 + dataset_id,
                source_updated_at="2026-10-11T02:00:00Z",
                annotations={"shapes": [], "tracks": []},
                frames=[
                    FrameExport(
                        frame_index=0,
                        file_name="frame.jpg",
                        width=1280,
                        height=720,
                        media_bytes=b"frame",
                        media_storage_key=f"sha256/{dataset_id}/frame",
                    )
                ],
            )
        ],
    )
    snapshot_frame = snapshot.jobs.get().frames.get()
    config = ConfigVersion.objects.create(
        name=f"effort-{dataset_id}-{uuid.uuid4()}",
        status=ConfigVersion.Status.PUBLISHED,
        payload={},
        created_by=creator,
    )
    run = QCRun.objects.create(
        snapshot=snapshot,
        config_version=config,
        seed=1,
        status=QCRun.Status.COMPLETED,
        dataset_id=dataset_id,
        scope_hash=uuid.uuid4().hex * 2,
        created_by=creator,
    )
    return FrameReview.objects.create(run=run, snapshot_frame=snapshot_frame)


def _payload(frame_id: int, event_id: uuid.UUID | None = None, **changes):
    event = {
        "client_event_id": str(event_id or uuid.uuid4()),
        "frame_id": frame_id,
        "activity": "review_issue",
        "started_at": "2026-10-11T02:00:00Z",
        "ended_at": "2026-10-11T02:02:00Z",
    }
    event.update(changes)
    return {"events": [event]}


def _client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


@override_settings(
    EFFORT_IDLE_POLICY={
        "source": "product-owner/decision/TBD-11-v1",
        "decision_status": "approved",
        "t_idle_seconds": 45,
    }
)
def test_accepts_event_and_resend_is_idempotent_with_policy_provenance() -> None:
    reviewer = _user("reviewer", Role.REVIEWER, 42)
    frame = _frame(reviewer)
    client = _client(reviewer)
    payload = _payload(frame.pk)

    first = client.post("/api/effort-events/", payload, format="json")
    second = client.post("/api/effort-events/", payload, format="json")

    assert first.status_code == 202
    assert first.data == {"accepted": 1, "duplicates": 0}
    assert second.status_code == 202
    assert second.data == {"accepted": 0, "duplicates": 1}
    stored = EffortEvent.objects.get()
    assert stored.actor == reviewer
    assert stored.frame == frame
    assert stored.dataset_id == 42
    assert stored.active_ms == 120_000
    assert stored.t_idle_seconds == 45
    assert stored.config_source == "product-owner/decision/TBD-11-v1"
    assert stored.config_snapshot["decision_status"] == "approved"


def test_real_lease_decision_effort_and_complete_flow(world) -> None:
    """T-033/T-035 integration: contract frame_id is FrameReview, not SnapshotFrame."""
    api = _client(world["reviewer"])
    claim = api.post("/api/queues/risk/next/", {"run_id": world["run"].pk}, format="json")
    assert claim.status_code == 200, claim.data
    lease_id = claim.data["lease"]["id"]
    frame_id = claim.data["frame"]["id"]

    issue = api.post(
        "/api/issues/",
        {
            "frame_id": frame_id,
            "lease_id": lease_id,
            "family": "E1",
            "description": "Effort integration issue",
            "anchor": {
                "kind": "manual_region",
                "objects": [],
                "bbox": {"x1": 1, "y1": 1, "x2": 10, "y2": 10},
                "policy_version": "anchor-v1",
            },
        },
        format="json",
    )
    assert issue.status_code == 201, issue.data
    decision = api.post(
        f"/api/issues/{issue.data['id']}/decisions/",
        {
            "lease_id": lease_id,
            "action": "confirm",
            "revision": world["run"].snapshot.revision_sha256,
            "family": "E1",
            "severity": "medium",
        },
        format="json",
    )
    assert decision.status_code == 201, decision.data
    assert ReviewDecision.objects.filter(pk=decision.data["id"]).exists()

    payload = _payload(frame_id)
    effort = api.post("/api/effort-events/", payload, format="json")
    assert effort.status_code == 202, effort.data
    stored = EffortEvent.objects.get()
    assert stored.frame_id == frame_id
    assert stored.frame.snapshot_frame_id == world["frame"].pk

    completed = api.post(f"/api/frames/{frame_id}/complete/", {"lease_id": lease_id}, format="json")
    assert completed.status_code == 200, completed.data
    retry = api.post("/api/effort-events/", payload, format="json")
    assert retry.status_code == 202
    assert retry.data == {"accepted": 0, "duplicates": 1}


def test_duplicate_inside_one_batch_is_counted_once() -> None:
    reviewer = _user("same-batch", Role.REVIEWER, 42)
    frame = _frame(reviewer)
    event = _payload(frame.pk)["events"][0]
    response = _client(reviewer).post(
        "/api/effort-events/", {"events": [event, event]}, format="json"
    )
    assert response.status_code == 202
    assert response.data == {"accepted": 1, "duplicates": 1}
    assert EffortEvent.objects.count() == 1


def test_reused_event_id_with_different_body_is_conflict() -> None:
    reviewer = _user("conflict", Role.REVIEWER, 42)
    frame = _frame(reviewer)
    client = _client(reviewer)
    event_id = uuid.uuid4()
    first = client.post("/api/effort-events/", _payload(frame.pk, event_id), format="json")
    assert first.status_code == 202

    conflict = client.post(
        "/api/effort-events/",
        _payload(frame.pk, event_id, activity="view_frame"),
        format="json",
    )
    assert conflict.status_code == 409
    assert conflict.data["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert EffortEvent.objects.count() == 1


def test_role_scope_and_identity_are_fail_closed() -> None:
    creator = _user("creator", Role.QA_LEAD, 42)
    frame = _frame(creator)

    wrong_role = _user("annotator", Role.ANNOTATOR, 42)
    denied_role = _client(wrong_role).post("/api/effort-events/", _payload(frame.pk), format="json")
    assert denied_role.status_code == 403
    assert denied_role.data["code"] == "FORBIDDEN"

    outsider = _user("outsider", Role.REVIEWER, 99)
    denied_scope = _client(outsider).post("/api/effort-events/", _payload(frame.pk), format="json")
    assert denied_scope.status_code == 403
    assert denied_scope.data["code"] == "OUT_OF_SCOPE"

    unmapped = _user("unmapped", Role.REVIEWER, 42, identity=False)
    denied_identity = _client(unmapped).post(
        "/api/effort-events/", _payload(frame.pk), format="json"
    )
    assert denied_identity.status_code == 403
    assert denied_identity.data["code"] == "IDENTITY_MAPPING_MISSING"
    assert EffortEvent.objects.count() == 0


def test_invalid_timeline_missing_frame_and_mixed_dataset_batch_are_rejected() -> None:
    reviewer = _user("validation", Role.REVIEWER, 42)
    frame = _frame(reviewer, 42)
    other_frame = _frame(reviewer, 99)
    client = _client(reviewer)

    invalid_time = client.post(
        "/api/effort-events/",
        _payload(frame.pk, ended_at="2026-10-11T01:59:59Z"),
        format="json",
    )
    assert invalid_time.status_code == 400
    assert invalid_time.data["code"] == "VALIDATION_ERROR"

    missing = client.post("/api/effort-events/", _payload(999_999), format="json")
    assert missing.status_code == 404
    assert missing.data["code"] == "NOT_FOUND"

    first = _payload(frame.pk)["events"][0]
    second = _payload(other_frame.pk)["events"][0]
    mixed = client.post("/api/effort-events/", {"events": [first, second]}, format="json")
    assert mixed.status_code == 400
    assert mixed.data["code"] == "VALIDATION_ERROR"
    assert EffortEvent.objects.count() == 0
