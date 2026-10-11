"""T-040 rework API, lineage, idempotency and transaction evidence."""

from uuid import uuid4

import pytest
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from audit.models import AuditEvent
from review import rework_service
from review.models import (
    FrameReview,
    Issue,
    ReviewDecision,
    ReworkRecheck,
    ReworkRequest,
    ReworkVerification,
)
from runs.models import QCRun
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot
from tests.review.test_queue_lease import client

pytest_plugins = ["tests.review.test_queue_lease"]


@pytest.fixture(autouse=True)
def cvat_base_url(settings):
    settings.CVAT_BASE_URL = "http://localhost:8080"


@pytest.fixture
def confirmed(world):
    frame_review = FrameReview.objects.create(
        run=world["run"], snapshot_frame=world["frame"], state=FrameReview.State.REVIEWED
    )
    issue = Issue.objects.create(
        frame_review=frame_review,
        family=Issue.Family.E1,
        origin=Issue.Origin.REVIEWER,
        state=Issue.State.CONFIRMED,
        anchor={"kind": "manual_region", "objects": []},
        severity=Issue.Severity.MEDIUM,
        created_by=world["reviewer"],
    )
    return issue


def create_body(confirmed, world):
    return {
        "issue_id": confirmed.pk,
        "instruction": "Correct the missing vehicle box",
        "annotator_user_id": world["author"].pk,
        "due_at": "2026-10-12T10:00:00Z",
        "severity": "medium",
        "cvat_deep_link": "http://localhost:8080/tasks/200/jobs/100?frame=0",
    }


def create_request(confirmed, world, *, key=None):
    kwargs = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
    return client(world["reviewer"]).post(
        "/api/rework/", create_body(confirmed, world), format="json", **kwargs
    )


def changed_snapshot(world):
    return create_locked_snapshot(
        dataset_id=42,
        created_by=world["author"],
        taxonomy_version="tax",
        guideline_version="guide",
        parent_snapshot=world["run"].snapshot,
        jobs=[
            JobExport(
                cvat_job_id=100,
                cvat_task_id=200,
                assignee_cvat_user_id=702,
                assignee_user_id=world["author"].pk,
                source_updated_at="2026-10-11T11:00:00Z",
                annotations={"shapes": [], "tracks": []},
                frames=[
                    FrameExport(
                        frame_index=0,
                        file_name="0.jpg",
                        width=100,
                        height=100,
                        media_bytes=b"frame-0",
                        media_storage_key="rework/0.jpg",
                    )
                ],
            )
        ],
    )


@pytest.mark.django_db
def test_create_rework_appends_decision_audit_and_replays(confirmed, world):
    key = str(uuid4())
    response = create_request(confirmed, world, key=key)
    assert response.status_code == 201, response.data
    rework = ReworkRequest.objects.get(pk=response.data["id"])
    confirmed.refresh_from_db()
    assert confirmed.state == Issue.State.FIX_PENDING
    assert rework.original_revision == world["run"].snapshot.revision_sha256
    decision = ReviewDecision.objects.get(issue=confirmed, action=ReviewDecision.Action.REQUEST_FIX)
    assert decision.actor == world["reviewer"]
    assert AuditEvent.objects.filter(
        pk=decision.audit_event_id, action="issue.request_fix"
    ).exists()

    replay = create_request(confirmed, world, key=key)
    assert replay.status_code == 201 and replay.data["id"] == response.data["id"]
    assert ReworkRequest.objects.count() == 1
    assert ReviewDecision.objects.filter(action=ReviewDecision.Action.REQUEST_FIX).count() == 1

    changed = create_body(confirmed, world)
    changed["instruction"] = "Different"
    conflict = client(world["reviewer"]).post(
        "/api/rework/", changed, format="json", HTTP_IDEMPOTENCY_KEY=key
    )
    assert conflict.status_code == 409
    assert conflict.data["code"] == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.django_db
def test_create_rework_rejects_wrong_frame_link_and_rolls_back_audit_failure(
    confirmed, world, monkeypatch
):
    body = create_body(confirmed, world)
    body["cvat_deep_link"] = "http://localhost:8080/tasks/200/jobs/999?frame=0"
    wrong = client(world["reviewer"]).post("/api/rework/", body, format="json")
    assert wrong.status_code == 409
    confirmed.refresh_from_db()
    assert confirmed.state == Issue.State.CONFIRMED

    monkeypatch.setattr(
        rework_service,
        "append_audit_event",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError()),
    )
    with pytest.raises(RuntimeError):
        create_request(confirmed, world)
    confirmed.refresh_from_db()
    assert confirmed.state == Issue.State.CONFIRMED
    assert not ReworkRequest.objects.exists()


@pytest.mark.django_db
def test_submission_requires_new_revision_and_is_idempotent(confirmed, world, monkeypatch):
    created = create_request(confirmed, world)
    rework = ReworkRequest.objects.get(pk=created.data["id"])
    unchanged = client(world["author"]).post(
        f"/api/rework/{rework.pk}/submitted/",
        {"cvat_revision": rework.original_revision},
        format="json",
    )
    assert unchanged.status_code == 409 and unchanged.data["code"] == "REVISION_UNCHANGED"

    snapshot = changed_snapshot(world)
    run = QCRun.objects.create(
        snapshot=snapshot,
        config_version=world["run"].config_version,
        seed=world["run"].seed,
        status=QCRun.Status.QUEUED,
        origin_run=world["run"],
        dataset_id=42,
        scope_hash=snapshot.revision_sha256,
        created_by=world["author"],
    )
    monkeypatch.setattr(
        rework_service, "_build_recheck_artifacts", lambda **_kwargs: (snapshot, run)
    )
    key = str(uuid4())
    submitted = client(world["author"]).post(
        f"/api/rework/{rework.pk}/submitted/",
        {"cvat_revision": snapshot.revision_sha256},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert submitted.status_code == 202, submitted.data
    assert submitted.data["status"] == "recheck_pending"
    assert submitted.data["recheck_run_id"] == run.pk
    assert ReworkRecheck.objects.filter(
        rework=rework, snapshot=snapshot, run=run, revision=snapshot.revision_sha256
    ).exists()
    assert Issue.objects.get(pk=confirmed.pk).state == Issue.State.RECHECK_PENDING

    replay = client(world["author"]).post(
        f"/api/rework/{rework.pk}/submitted/",
        {"cvat_revision": snapshot.revision_sha256},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert replay.status_code == 202 and replay.data["recheck_run_id"] == run.pk
    assert ReworkRecheck.objects.count() == 1


@pytest.mark.django_db
def test_verify_requires_completed_recheck_and_separate_person(confirmed, world, monkeypatch):
    created = create_request(confirmed, world)
    rework = ReworkRequest.objects.get(pk=created.data["id"])
    snapshot = changed_snapshot(world)
    run = QCRun.objects.create(
        snapshot=snapshot,
        config_version=world["run"].config_version,
        seed=1,
        status=QCRun.Status.QUEUED,
        origin_run=world["run"],
        dataset_id=42,
        scope_hash=snapshot.revision_sha256,
        created_by=world["author"],
    )
    monkeypatch.setattr(
        rework_service, "_build_recheck_artifacts", lambda **_kwargs: (snapshot, run)
    )
    client(world["author"]).post(
        f"/api/rework/{rework.pk}/submitted/",
        {"cvat_revision": snapshot.revision_sha256},
        format="json",
    )
    body = {"passed": True, "revision": snapshot.revision_sha256}
    early = client(world["other"]).post(f"/api/rework/{rework.pk}/verify/", body, format="json")
    assert early.status_code == 409

    run.status = QCRun.Status.COMPLETED
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "finished_at"])
    same_person = client(world["author"]).post(
        f"/api/rework/{rework.pk}/verify/", body, format="json"
    )
    assert same_person.status_code == 403

    key = str(uuid4())
    verified = client(world["other"]).post(
        f"/api/rework/{rework.pk}/verify/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert verified.status_code == 200, verified.data
    assert verified.data["status"] == "resolved"
    assert Issue.objects.get(pk=confirmed.pk).state == Issue.State.RESOLVED
    verification = ReworkVerification.objects.get(rework=rework)
    assert verification.outcome == ReworkVerification.Outcome.PASS
    assert verification.recheck_run == run
    assert AuditEvent.objects.filter(pk=verification.audit_event_id).exists()

    replay = client(world["other"]).post(
        f"/api/rework/{rework.pk}/verify/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert replay.status_code == 200
    assert ReworkVerification.objects.count() == 1

    with pytest.raises(ValueError, match="append-only"):
        verification.save()
    assert connection.vendor == "postgresql"
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE rework_verification SET reason = %s WHERE id = %s",
                ["tamper", verification.pk],
            )


@pytest.mark.django_db
def test_verify_fail_reopens_issue(confirmed, world, monkeypatch):
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
    client(world["author"]).post(
        f"/api/rework/{rework.pk}/submitted/",
        {"cvat_revision": snapshot.revision_sha256},
        format="json",
    )
    failed = client(world["other"]).post(
        f"/api/rework/{rework.pk}/verify/",
        {"passed": False, "revision": snapshot.revision_sha256, "reason": "Still wrong"},
        format="json",
    )
    assert failed.status_code == 200, failed.data
    assert failed.data["status"] == "reopened"
    assert Issue.objects.get(pk=confirmed.pk).state == Issue.State.REOPENED
    assert ReworkVerification.objects.get(rework=rework).outcome == "fail"
