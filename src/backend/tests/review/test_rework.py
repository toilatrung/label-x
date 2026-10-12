"""T-040 rework API, lineage, idempotency and transaction evidence."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import DatabaseError, connection, connections, transaction
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

    changed_replay = client(world["author"]).post(
        f"/api/rework/{rework.pk}/submitted/",
        {"cvat_revision": snapshot.revision_sha256, "retry_context": "changed"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert changed_replay.status_code == 409
    assert changed_replay.data["code"] == "IDEMPOTENCY_KEY_REUSED"


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
    assert FrameReview.objects.get(pk=confirmed.frame_review_id).state == (
        FrameReview.State.AWAITING_FOLLOWUP
    )
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
    assert failed.data["status"] == "fix_pending"
    assert Issue.objects.get(pk=confirmed.pk).state == Issue.State.FIX_PENDING
    assert ReworkVerification.objects.get(rework=rework).outcome == "fail"
    actions = list(
        AuditEvent.objects.filter(object_type="rework", object_id=str(rework.pk)).values_list(
            "action", flat=True
        )
    )
    assert "rework.verify_fail" in actions
    assert AuditEvent.objects.filter(
        action="issue.reopen_fix", object_id=str(confirmed.pk), reason="Still wrong"
    ).exists()


def second_snapshot(world):
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
                source_updated_at="2026-10-11T12:00:00Z",
                annotations={
                    "shapes": [
                        {
                            "id": 92,
                            "type": "rectangle",
                            "frame": 0,
                            "label_id": 1,
                            "points": [2, 2, 20, 20],
                        }
                    ],
                    "tracks": [],
                },
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


def _run_for(world, snapshot):
    return QCRun.objects.create(
        snapshot=snapshot,
        config_version=world["run"].config_version,
        seed=1,
        status=QCRun.Status.COMPLETED,
        origin_run=world["run"],
        dataset_id=42,
        scope_hash=snapshot.revision_sha256,
        created_by=world["author"],
    )


def _submit(world, rework, snapshot, **extra):
    return client(world["author"]).post(
        f"/api/rework/{rework.pk}/submitted/",
        {"cvat_revision": snapshot.revision_sha256},
        format="json",
        **extra,
    )


def _verify(world, rework, snapshot, passed, **extra):
    body = {"passed": passed, "revision": snapshot.revision_sha256}
    if not passed:
        body["reason"] = "Still wrong"
    return client(world["other"]).post(
        f"/api/rework/{rework.pk}/verify/", body, format="json", **extra
    )


@pytest.mark.django_db
def test_verify_failure_can_be_submitted_again(confirmed, world, monkeypatch):
    """Two rounds: unchanged revision 409, fail -> fix again -> pass, append-only lineage."""

    created = create_request(confirmed, world)
    rework = ReworkRequest.objects.get(pk=created.data["id"])
    first, second = changed_snapshot(world), second_snapshot(world)
    assert first.revision_sha256 != second.revision_sha256
    runs = {first.pk: _run_for(world, first), second.pk: _run_for(world, second)}
    current = {"snapshot": first}
    monkeypatch.setattr(
        rework_service,
        "_build_recheck_artifacts",
        lambda **_kwargs: (current["snapshot"], runs[current["snapshot"].pk]),
    )

    assert _submit(world, rework, first).status_code == 202
    failed = _verify(world, rework, first, False)
    assert failed.status_code == 200 and failed.data["status"] == "fix_pending"

    # the failed revision (and the original one) are not a new fix
    again = _submit(world, rework, first)
    assert again.status_code == 409 and again.data["code"] == "REVISION_UNCHANGED"
    again = _submit(world, rework, world["run"].snapshot)
    assert again.status_code == 409 and again.data["code"] == "REVISION_UNCHANGED"

    current["snapshot"] = second
    submitted = _submit(world, rework, second)
    assert submitted.status_code == 202, submitted.data
    assert submitted.data["status"] == "recheck_pending"
    assert submitted.data["recheck_run_id"] == runs[second.pk].pk
    assert Issue.objects.get(pk=confirmed.pk).state == Issue.State.RECHECK_PENDING

    passed = _verify(world, rework, second, True)
    assert passed.status_code == 200 and passed.data["status"] == "resolved"
    assert Issue.objects.get(pk=confirmed.pk).state == Issue.State.RESOLVED

    rechecks = list(rework.rechecks.order_by("round"))
    assert [(r.round, r.revision) for r in rechecks] == [
        (1, first.revision_sha256),
        (2, second.revision_sha256),
    ]
    outcomes = list(rework.verifications.order_by("pk").values_list("outcome", "revision"))
    assert outcomes == [("fail", first.revision_sha256), ("pass", second.revision_sha256)]
    assert (
        AuditEvent.objects.filter(action="rework.submitted", object_id=str(rework.pk)).count() == 2
    )
    assert AuditEvent.objects.filter(action="issue.reopen_fix").count() == 1


@pytest.mark.django_db
def test_multi_round_replays_do_not_duplicate_results(confirmed, world, monkeypatch):
    created = create_request(confirmed, world)
    rework = ReworkRequest.objects.get(pk=created.data["id"])
    first, second = changed_snapshot(world), second_snapshot(world)
    runs = {first.pk: _run_for(world, first), second.pk: _run_for(world, second)}
    current = {"snapshot": first}
    monkeypatch.setattr(
        rework_service,
        "_build_recheck_artifacts",
        lambda **_kwargs: (current["snapshot"], runs[current["snapshot"].pk]),
    )
    submit_key, verify_key = str(uuid4()), str(uuid4())
    assert _submit(world, rework, first, HTTP_IDEMPOTENCY_KEY=submit_key).status_code == 202
    assert _verify(world, rework, first, False, HTTP_IDEMPOTENCY_KEY=verify_key).status_code == 200

    # retry of round 1 submit/verify after the issue is already back to fix_pending
    replay = _submit(world, rework, first, HTTP_IDEMPOTENCY_KEY=submit_key)
    assert replay.status_code == 202
    replay = _verify(world, rework, first, False, HTTP_IDEMPOTENCY_KEY=verify_key)
    assert replay.status_code == 200
    assert rework.rechecks.count() == 1 and rework.verifications.count() == 1

    # same key for a different revision is key reuse, not a new round
    current["snapshot"] = second
    reused = _submit(world, rework, second, HTTP_IDEMPOTENCY_KEY=submit_key)
    assert reused.status_code == 409 and reused.data["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert rework.rechecks.count() == 1

    new_key = str(uuid4())
    assert _submit(world, rework, second, HTTP_IDEMPOTENCY_KEY=new_key).status_code == 202
    assert _submit(world, rework, second, HTTP_IDEMPOTENCY_KEY=new_key).status_code == 202
    assert rework.rechecks.count() == 2
    # a second verifier request with a fresh key cannot double-record the same round
    assert _verify(world, rework, second, True).status_code == 200
    late = _verify(world, rework, second, True)
    assert late.status_code == 409
    assert rework.verifications.count() == 2


@pytest.mark.django_db
def test_failed_round_blocks_verify_by_annotator_and_wrong_actor(confirmed, world, monkeypatch):
    created = create_request(confirmed, world)
    rework = ReworkRequest.objects.get(pk=created.data["id"])
    first = changed_snapshot(world)
    run = _run_for(world, first)
    monkeypatch.setattr(rework_service, "_build_recheck_artifacts", lambda **_kw: (first, run))
    assert _submit(world, rework, first).status_code == 202
    assert _verify(world, rework, first, False).status_code == 200
    # nothing to verify until a new revision is submitted
    pending = _verify(world, rework, first, True)
    assert pending.status_code == 409
    stranger = client(world["reviewer"]).post(
        f"/api/rework/{rework.pk}/submitted/",
        {"cvat_revision": "f" * 64},
        format="json",
    )
    assert stranger.status_code == 403


def _thread_post(barrier, user, path, body):
    connections.close_all()
    try:
        barrier.wait(timeout=15)
        response = client(user).post(path, body, format="json")
        return response.status_code
    finally:
        connections.close_all()


@pytest.mark.django_db(transaction=True)
def test_concurrent_verify_records_single_result(confirmed, world, monkeypatch):
    created = create_request(confirmed, world)
    rework = ReworkRequest.objects.get(pk=created.data["id"])
    first = changed_snapshot(world)
    run = _run_for(world, first)
    monkeypatch.setattr(rework_service, "_build_recheck_artifacts", lambda **_kw: (first, run))
    assert _submit(world, rework, first).status_code == 202

    barrier = Barrier(2)
    body = {"passed": False, "revision": first.revision_sha256, "reason": "Still wrong"}
    path = f"/api/rework/{rework.pk}/verify/"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_thread_post, barrier, world["other"], path, body) for _ in "ab"]
        codes = sorted(future.result() for future in futures)
    assert codes == [200, 409]
    assert rework.verifications.count() == 1
    assert AuditEvent.objects.filter(action="issue.reopen_fix").count() == 1
    assert Issue.objects.get(pk=confirmed.pk).state == Issue.State.FIX_PENDING


def _first_round_failed(confirmed, world, monkeypatch):
    created = create_request(confirmed, world)
    rework = ReworkRequest.objects.get(pk=created.data["id"])
    first, second = changed_snapshot(world), second_snapshot(world)
    run = _run_for(world, first)
    monkeypatch.setattr(rework_service, "_build_recheck_artifacts", lambda **_kw: (first, run))
    assert _submit(world, rework, first).status_code == 202
    assert _verify(world, rework, first, False).status_code == 200
    return rework, first, second, run


def _state(rework, confirmed):
    return (
        ReworkRequest.objects.get(pk=rework.pk).status,
        ReworkRequest.objects.get(pk=rework.pk).submitted_revision,
        Issue.objects.get(pk=confirmed.pk).state,
        ReworkRecheck.objects.filter(rework=rework).count(),
        AuditEvent.objects.filter(action="rework.submitted").count(),
    )


@pytest.mark.django_db
def test_recheck_reusing_same_snapshot_is_409_without_db_change(confirmed, world, monkeypatch):
    rework, first, second, run = _first_round_failed(confirmed, world, monkeypatch)
    before = _state(rework, confirmed)
    # CVAT handed back the snapshot of round 1 again although a new revision was claimed
    reused = _submit(world, rework, second)
    assert reused.status_code == 409, reused.data
    assert reused.data["code"] == "REVISION_UNCHANGED"
    assert reused.data["details"] == {"rework_id": rework.pk, "snapshot_id": first.pk}
    assert (
        _state(rework, confirmed)
        == before
        == ("fix_pending", first.revision_sha256, "fix_pending", 1, 1)
    )


@pytest.mark.django_db
def test_recheck_snapshot_race_integrity_error_becomes_409(confirmed, world, monkeypatch):
    rework, first, second, run = _first_round_failed(confirmed, world, monkeypatch)
    before = _state(rework, confirmed)
    real_create = ReworkRecheck.objects.create

    def lose_race(**kwargs):
        # a concurrent request committed the same snapshot after our pre-check
        real_create(**{**kwargs, "round": 99, "idempotency_key": None})
        return real_create(**kwargs)

    monkeypatch.setattr(ReworkRecheck.objects, "create", lose_race)
    raced = _submit(world, rework, second)
    assert raced.status_code == 409, raced.data
    assert raced.data["code"] == "REVISION_UNCHANGED"
    monkeypatch.undo()
    assert _state(rework, confirmed) == before
