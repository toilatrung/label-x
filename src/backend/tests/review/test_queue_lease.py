"""T-033 API and real PostgreSQL locking evidence."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.contrib.auth.models import User
from django.core.files.storage import storages
from django.db import connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import CvatIdentity, EmployeeIdentity, Role, RoleAssignment
from audit.models import AuditEvent
from review.models import FrameReview, Lease
from runs.models import ConfigVersion, QCRun, RunRanking, RunRankingEntry
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot


@pytest.fixture
def approved_test_policy(settings):
    """Short TTLs for the T-033 lock tests only; every other module sees the pilot defaults."""

    settings.REVIEW_LEASE_TTL_SECONDS = 60
    settings.REVIEW_INCOMPLETE_RESERVATION_SECONDS = 120


pytestmark = pytest.mark.usefixtures("approved_test_policy")


@pytest.fixture
def world(db):
    admin = User.objects.create_user("admin-t033")

    def actor(name, cvat_id, employee_name, role=Role.REVIEWER, dataset_id=42):
        user = User.objects.create_user(name)
        RoleAssignment.objects.create(user=user, role=role, dataset_id=dataset_id)
        if cvat_id is not None:
            employee = EmployeeIdentity.objects.create(
                employee_id=employee_name, verified_at=timezone.now(), verified_by=admin
            )
            CvatIdentity.objects.create(user=user, cvat_user_id=cvat_id, employee=employee)
        return user

    reviewer = actor("reviewer-t033", 701, "person-reviewer")
    other = actor("other-t033", 703, "person-other")
    author = actor("author-t033", 702, "person-author", Role.ANNOTATOR)
    snapshot = create_locked_snapshot(
        dataset_id=42,
        created_by=admin,
        taxonomy_version="tax",
        guideline_version="guide",
        jobs=[
            JobExport(
                cvat_job_id=100,
                cvat_task_id=200,
                assignee_cvat_user_id=702,
                assignee_user_id=author.pk,
                source_updated_at="2026-10-11T00:00:00Z",
                annotations={
                    "shapes": [
                        {
                            "id": 91,
                            "type": "rectangle",
                            "frame": 0,
                            "label_id": 1,
                            "points": [1, 1, 10, 10],
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
                        media_storage_key="0.jpg",
                    )
                ],
            )
        ],
    )
    frame = snapshot.jobs.get().frames.get()
    config = ConfigVersion.objects.create(
        name="t033", status=ConfigVersion.Status.PUBLISHED, payload={}, created_by=admin
    )
    run = QCRun.objects.create(
        snapshot=snapshot,
        config_version=config,
        seed=1,
        status=QCRun.Status.COMPLETED,
        dataset_id=42,
        scope_hash="d" * 64,
        created_by=admin,
    )
    risk = RunRanking.objects.create(
        run=run,
        source=RunRanking.Source.RISK,
        seed=1,
        score_version="v0",
        content_hash="e" * 64,
        ranking_hash="f" * 64,
    )
    random = RunRanking.objects.create(
        run=run,
        source=RunRanking.Source.RANDOM_AUDIT,
        seed=2,
        score_version="v0",
        content_hash="e" * 64,
        ranking_hash="a" * 64,
    )
    for ranking in (risk, random):
        RunRankingEntry.objects.create(
            ranking=ranking,
            snapshot_frame=frame,
            rank=1,
            score=1,
            baseline_score=1,
            tie_break_hash="a" * 64,
        )
    return {
        "reviewer": reviewer,
        "other": other,
        "author": author,
        "admin": admin,
        "run": run,
        "frame": frame,
    }


def client(user):
    api = APIClient()
    api.force_authenticate(user=user)
    return api


def next_url(queue="risk"):
    return f"/api/queues/{queue}/next/"


def persist_manual_decision(world, lease_id):
    """Real API writer: no mocked persisted-decision projection."""
    api = client(world["reviewer"])
    frame_id = Lease.objects.get(pk=lease_id).frame_review_id
    created = api.post(
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
    assert created.status_code == 201, created.data
    decided = api.post(
        f"/api/issues/{created.data['id']}/decisions/",
        {
            "lease_id": lease_id,
            "action": "confirm",
            "revision": world["run"].snapshot.revision_sha256,
            "family": "E1",
            "severity": "medium",
        },
        format="json",
    )
    assert decided.status_code == 201, decided.data
    return created.data["id"]


@pytest.mark.django_db
def test_claim_two_tab_renew_expiry_resume_and_204(world):
    user = world["reviewer"]
    run_id = world["run"].pk
    api = client(user)
    first = api.post(next_url(), {"run_id": run_id}, format="json")
    assert first.status_code == 200
    assert set(first.data) == {"lease", "frame", "resumed"}
    assert set(first.data["lease"]) == {"id", "frame_id", "holder_user_id", "expires_at"}
    assert {"id", "run_id", "frame_key", "review_state", "missing_evidence"} <= set(
        first.data["frame"]
    )
    lease_id = first.data["lease"]["id"]
    assert first.data["frame"]["frame_key"] == {"cvat_task_id": 200, "frame_number": 0}
    second = api.post(next_url("random"), {"run_id": run_id}, format="json")
    assert second.status_code == 200
    assert second.data["lease"]["id"] == lease_id
    assert second.data["resumed"] is True
    renewed = api.post(f"/api/leases/{lease_id}/renew/", {}, format="json")
    assert renewed.status_code == 200
    assert set(renewed.data) == {"id", "frame_id", "holder_user_id", "expires_at"}
    assert client(world["other"]).post(f"/api/leases/{lease_id}/renew/", {}).status_code == 409
    assert AuditEvent.objects.filter(
        action="leases.renew.rejected", object_id=str(lease_id)
    ).exists()

    persist_manual_decision(world, lease_id)
    Lease.objects.filter(pk=lease_id).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert api.post(f"/api/leases/{lease_id}/renew/", {}).status_code == 409
    resumed = api.post(next_url(), {"run_id": run_id}, format="json")
    assert resumed.status_code == 200
    assert resumed.data["resumed"] is True
    assert resumed.data["lease"]["id"] != lease_id
    assert Lease.objects.filter(holder=user, closed_at__isnull=True).count() == 1
    # A fresh reviewer cannot take a frame with an active lease.
    assert (
        client(world["other"]).post(next_url(), {"run_id": run_id}, format="json").status_code
        == 204
    )


@pytest.mark.django_db
def test_queue_summary_and_specific_frame_claim(world):
    api = client(world["reviewer"])
    summary = api.get(f"/api/queues/risk/?run_id={world['run'].pk}")
    assert summary.status_code == 200, summary.data
    assert summary.data["total"] == 1
    assert summary.data["counts"][FrameReview.State.UNREVIEWED] == 1

    claimed = api.post(
        next_url(),
        {"run_id": world["run"].pk, "frame_id": world["frame"].pk},
        format="json",
    )
    assert claimed.status_code == 200, claimed.data
    assert claimed.data["frame"]["frame_key"] == {
        "cvat_task_id": 200,
        "frame_number": 0,
    }
    after = api.get(f"/api/queues/risk/?run_id={world['run'].pk}")
    assert after.data["counts"][FrameReview.State.IN_REVIEW] == 1

    wrong = client(world["other"]).post(
        next_url(),
        {"run_id": world["run"].pk, "frame_id": world["frame"].pk + 999},
        format="json",
    )
    assert wrong.status_code == 409
    assert wrong.data["code"] == "LEASE_CONFLICT"


@pytest.mark.django_db
def test_identity_alias_scope_role_and_client_dataset_bypass(world):
    run_id = world["run"].pk
    assert (
        client(world["author"]).post(next_url(), {"run_id": run_id}, format="json").status_code
        == 403
    )
    missing = User.objects.create_user("missing-t033")
    RoleAssignment.objects.create(user=missing, role=Role.REVIEWER, dataset_id=42)
    response = client(missing).post(next_url(), {"run_id": run_id}, format="json")
    assert response.status_code == 403 and response.data["code"] == "IDENTITY_MAPPING_MISSING"
    alias = User.objects.create_user("alias-t033")
    RoleAssignment.objects.create(user=alias, role=Role.REVIEWER, dataset_id=42)
    author_identity = CvatIdentity.objects.get(user=world["author"])
    CvatIdentity.objects.create(user=alias, cvat_user_id=704, employee=author_identity.employee)
    assert client(alias).post(next_url(), {"run_id": run_id}, format="json").status_code == 204
    outside = User.objects.create_user("outside-t033")
    RoleAssignment.objects.create(user=outside, role=Role.REVIEWER, dataset_id=99)
    CvatIdentity.objects.create(
        user=outside,
        cvat_user_id=705,
        employee=CvatIdentity.objects.get(user=world["other"]).employee,
    )
    response = client(outside).post(next_url(), {"run_id": run_id, "dataset_id": 99}, format="json")
    assert response.status_code == 400  # client cannot override the run's dataset
    response = client(outside).post(next_url(), {"run_id": run_id}, format="json")
    assert response.status_code == 403 and response.data["code"] == "OUT_OF_SCOPE"

    super_admin = User.objects.create_user("super-t033")
    RoleAssignment.objects.create(user=super_admin, role=Role.SUPER_ADMIN, dataset_id=None)
    CvatIdentity.objects.create(
        user=super_admin, cvat_user_id=706, employee=author_identity.employee
    )
    assert (
        client(super_admin).post(next_url(), {"run_id": run_id}, format="json").status_code == 204
    )


@pytest.mark.django_db
def test_queue_source_isolation_and_missing_resources(world):
    run_id = world["run"].pk
    api = client(world["reviewer"])
    assert api.post(next_url(), {"run_id": run_id + 9999}, format="json").status_code == 404
    RunRankingEntry.objects.filter(
        ranking__run_id=run_id, ranking__source=RunRanking.Source.RISK
    ).delete()
    assert api.post(next_url("risk"), {"run_id": run_id}, format="json").status_code == 204
    result = api.post(next_url("random"), {"run_id": run_id}, format="json")
    assert result.status_code == 200
    assert Lease.objects.get(pk=result.data["lease"]["id"]).queue_source == "random"


@pytest.mark.django_db
def test_exact_expiry_materializes_and_reservation_boundary(world, monkeypatch):
    clock = [timezone.now()]
    monkeypatch.setattr("review.services._now", lambda: clock[0])
    reviewer_api = client(world["reviewer"])
    other_api = client(world["other"])
    run_id = world["run"].pk
    claim = reviewer_api.post(next_url(), {"run_id": run_id}, format="json")
    assert claim.status_code == 200
    lease = Lease.objects.get(pk=claim.data["lease"]["id"])
    clock[0] = lease.expires_at  # exact equality is expired
    persist_manual_decision(world, lease.pk)
    response = reviewer_api.post(f"/api/leases/{lease.pk}/renew/", {}, format="json")
    assert response.status_code == 409 and response.data["code"] == "LEASE_CONFLICT"
    lease.refresh_from_db()
    frame = lease.frame_review
    frame.refresh_from_db()
    assert lease.closed_at is not None
    assert frame.state == FrameReview.State.INCOMPLETE
    assert frame.incomplete_since == lease.expires_at
    assert frame.previous_reviewer_id == world["reviewer"].pk
    first_closed_at = lease.closed_at
    assert reviewer_api.post(f"/api/leases/{lease.pk}/renew/", {}).status_code == 409
    lease.refresh_from_db()
    assert lease.closed_at == first_closed_at  # expiry materialization is idempotent
    assert other_api.post(next_url(), {"run_id": run_id}, format="json").status_code == 204
    clock[0] = lease.expires_at + timedelta(seconds=120)
    takeover = other_api.post(next_url(), {"run_id": run_id}, format="json")
    assert takeover.status_code == 200
    assert takeover.data["resumed"] is False


@pytest.mark.django_db
def test_expiry_without_decisions_requeues_and_old_reviewer_resumes_incomplete(world, monkeypatch):
    clock = [timezone.now()]
    monkeypatch.setattr("review.services._now", lambda: clock[0])
    api = client(world["reviewer"])
    run_id = world["run"].pk
    first = api.post(next_url(), {"run_id": run_id}, format="json")
    lease = Lease.objects.get(pk=first.data["lease"]["id"])
    clock[0] = lease.expires_at
    assert api.post(f"/api/leases/{lease.pk}/renew/", {}).status_code == 409
    lease.refresh_from_db()
    assert lease.closed_at is not None
    assert lease.frame_review.state == FrameReview.State.UNREVIEWED
    again = api.post(next_url(), {"run_id": run_id}, format="json")
    assert again.status_code == 200 and again.data["resumed"] is False
    new_lease = Lease.objects.get(pk=again.data["lease"]["id"])
    persist_manual_decision(world, new_lease.pk)
    clock[0] = new_lease.expires_at
    assert api.post(f"/api/leases/{new_lease.pk}/renew/", {}).status_code == 409
    clock[0] += timedelta(seconds=1)
    resumed = api.post(next_url(), {"run_id": run_id}, format="json")
    assert resumed.status_code == 200 and resumed.data["resumed"] is True


@pytest.mark.django_db
def test_transaction_rolls_back_when_lease_creation_fails(world, monkeypatch):
    def fail_create(**_kwargs):
        raise RuntimeError("injected failure")

    monkeypatch.setattr(Lease.objects, "create", fail_create)
    with pytest.raises(RuntimeError, match="injected failure"):
        client(world["reviewer"]).post(next_url(), {"run_id": world["run"].pk}, format="json")
    assert Lease.objects.count() == 0
    assert FrameReview.objects.count() == 0


@pytest.mark.django_db
def test_missing_ranking_provenance_returns_controlled_404(world):
    api = client(world["reviewer"])
    run_id = world["run"].pk
    first = api.post(next_url(), {"run_id": run_id}, format="json")
    assert first.status_code == 200
    RunRankingEntry.objects.filter(
        ranking__run_id=run_id, ranking__source=RunRanking.Source.RISK
    ).delete()
    response = api.post(next_url(), {"run_id": run_id}, format="json")
    assert response.status_code == 404 and response.data["code"] == "NOT_FOUND"


@pytest.mark.django_db
def test_policy_has_no_business_default(world, settings):
    settings.REVIEW_LEASE_TTL_SECONDS = None
    with pytest.raises(Exception, match="REVIEW_LEASE_TTL_SECONDS"):
        client(world["reviewer"]).post(next_url(), {"run_id": world["run"].pk}, format="json")


@pytest.mark.django_db(transaction=True)
def test_migration_upgrade_from_baseline_schema():
    assert connection.vendor == "postgresql"
    executor = MigrationExecutor(connection)
    executor.migrate([("review", None)])
    assert "review_lease" not in connection.introspection.table_names()
    executor = MigrationExecutor(connection)
    executor.migrate([("review", "0002_issue_reviewdecision_and_more")])
    assert {"frame_review", "review_lease", "review_issue", "review_decision"} <= set(
        connection.introspection.table_names()
    )
    # Leave the shared test database at the latest schema for later transactional tests.
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_postgresql_barrier_two_tabs_same_reviewer(world):
    assert connection.vendor == "postgresql"
    barrier = Barrier(2)

    def race():
        connections.close_all()
        api = client(world["reviewer"])
        barrier.wait(timeout=15)
        response = api.post(next_url(), {"run_id": world["run"].pk}, format="json")
        connections.close_all()
        return response.status_code, response.data["lease"]["id"], response.data["resumed"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _i: race(), range(2)))
    assert [status for status, _, _ in results] == [200, 200]
    assert results[0][1] == results[1][1]
    assert sorted(resumed for _, _, resumed in results) == [False, True]
    assert Lease.objects.filter(closed_at__isnull=True).count() == 1


@pytest.mark.django_db(transaction=True)
def test_postgresql_barrier_expired_renew_vs_claim(world, monkeypatch):
    assert connection.vendor == "postgresql"
    clock = [timezone.now()]
    monkeypatch.setattr("review.services._now", lambda: clock[0])
    first = client(world["reviewer"]).post(next_url(), {"run_id": world["run"].pk}, format="json")
    assert first.status_code == 200
    lease_id = first.data["lease"]["id"]
    clock[0] = Lease.objects.get(pk=lease_id).expires_at
    barrier = Barrier(2)

    def race(user, url, payload):
        connections.close_all()
        api = client(user)
        barrier.wait(timeout=15)
        response = api.post(url, payload, format="json")
        connections.close_all()
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        renew_future = pool.submit(race, world["reviewer"], f"/api/leases/{lease_id}/renew/", {})
        claim_future = pool.submit(race, world["other"], next_url(), {"run_id": world["run"].pk})
        outcomes = (renew_future.result(), claim_future.result())
    assert outcomes == (409, 200)
    assert Lease.objects.filter(closed_at__isnull=True).count() == 1
    assert Lease.objects.get(pk=lease_id).closed_at is not None


@pytest.mark.django_db(transaction=True)
def test_postgresql_barrier_same_reviewer_two_runs_one_lease(world):
    assert connection.vendor == "postgresql"
    run = world["run"]
    second = QCRun.objects.create(
        snapshot=run.snapshot,
        config_version=run.config_version,
        seed=2,
        status=QCRun.Status.COMPLETED,
        dataset_id=42,
        scope_hash="2" * 64,
        created_by=world["admin"],
    )
    ranking = RunRanking.objects.create(
        run=second,
        source=RunRanking.Source.RANDOM_AUDIT,
        seed=2,
        score_version="v0",
        content_hash="e" * 64,
        ranking_hash="b" * 64,
    )
    RunRankingEntry.objects.create(
        ranking=ranking,
        snapshot_frame=world["frame"],
        rank=1,
        score=1,
        baseline_score=1,
        tie_break_hash="b" * 64,
    )
    barrier = Barrier(2)

    def race(run_id, queue):
        connections.close_all()
        api = client(world["reviewer"])
        barrier.wait(timeout=15)
        response = api.post(next_url(queue), {"run_id": run_id}, format="json")
        connections.close_all()
        return response.status_code, response.data["lease"]["id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(race, run.pk, "risk"), pool.submit(race, second.pk, "random")]
        results = [future.result() for future in futures]
    assert [status for status, _ in results] == [200, 200]
    assert results[0][1] == results[1][1]
    assert Lease.objects.filter(holder=world["reviewer"], closed_at__isnull=True).count() == 1


@pytest.mark.django_db(transaction=True)
def test_postgresql_barrier_claim_same_frame_once(world):
    assert connection.vendor == "postgresql", "NFR-15 requires real PostgreSQL"
    barrier = Barrier(2)
    run_id = world["run"].pk

    def race(user):
        connections.close_all()
        api = client(user)
        barrier.wait(timeout=15)
        result = api.post(next_url(), {"run_id": run_id}, format="json")
        connections.close_all()
        return result.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(race, [world["reviewer"], world["other"]]))
    assert sorted(results) == [200, 204]
    assert Lease.objects.filter(closed_at__isnull=True).count() == 1


def ranking_rows(api, run_id, queue="risk", **params):
    response = api.get(f"/api/runs/{run_id}/ranking/", {"queue": queue, **params})
    assert response.status_code == 200, response.data
    return response.data["results"]


@pytest.mark.django_db
def test_ranking_reports_persisted_state_holder_and_filters(world, monkeypatch):
    clock = [timezone.now()]
    monkeypatch.setattr("review.services._now", lambda: clock[0])
    api = client(world["reviewer"])
    run_id = world["run"].pk
    (row,) = ranking_rows(api, run_id)
    assert row["review_state"] == "unreviewed" and row["lease_holder_user_id"] is None

    claim = api.post(next_url(), {"run_id": run_id}, format="json")
    assert claim.status_code == 200
    for queue in ("risk", "random"):  # one frame state shared; queues keep their own entries
        (row,) = ranking_rows(api, run_id, queue)
        assert row["review_state"] == "in_review"
        assert row["lease_holder_user_id"] == world["reviewer"].pk
        (filtered_row,) = ranking_rows(api, run_id, queue, review_state="in_review")
        # Snapshot URLs are signed independently for each response and may have a
        # different expiry when calls cross a second boundary.
        assert {k: v for k, v in filtered_row.items() if k != "thumbnail_url"} == {
            k: v for k, v in row.items() if k != "thumbnail_url"
        }
        assert filtered_row["thumbnail_url"]
        for other in ("unreviewed", "incomplete", "reviewed", "awaiting_followup", "completed"):
            assert ranking_rows(api, run_id, queue, review_state=other) == []

    # Expiry is shown without any write from a GET: no decision -> unreviewed.
    lease = Lease.objects.get(pk=claim.data["lease"]["id"])
    clock[0] = lease.expires_at
    (row,) = ranking_rows(api, run_id)
    assert row["review_state"] == "unreviewed" and row["lease_holder_user_id"] is None
    assert len(ranking_rows(api, run_id, review_state="unreviewed")) == 1
    lease.refresh_from_db()
    assert lease.closed_at is None


@pytest.mark.django_db
def test_ranking_expired_lease_with_saved_decision_is_incomplete_then_resumes(world, monkeypatch):
    clock = [timezone.now()]
    monkeypatch.setattr("review.services._now", lambda: clock[0])
    api = client(world["reviewer"])
    run_id = world["run"].pk
    claim = api.post(next_url(), {"run_id": run_id}, format="json")
    lease = Lease.objects.get(pk=claim.data["lease"]["id"])
    persist_manual_decision(world, lease.pk)
    clock[0] = lease.expires_at
    (row,) = ranking_rows(api, run_id, review_state="incomplete")
    assert row["review_state"] == "incomplete" and row["lease_holder_user_id"] is None
    assert ranking_rows(api, run_id, review_state="in_review") == []
    resumed = api.post(next_url(), {"run_id": run_id}, format="json")
    assert resumed.data["resumed"] is True
    (row,) = ranking_rows(api, run_id, review_state="in_review")
    assert row["lease_holder_user_id"] == world["reviewer"].pk


@pytest.mark.django_db
def test_ranking_filter_covers_terminal_states_and_rejects_invalid(world):
    api = client(world["reviewer"])
    run_id = world["run"].pk
    frame_review = FrameReview.objects.create(run=world["run"], snapshot_frame=world["frame"])
    for state in ("reviewed", "awaiting_followup", "completed"):
        frame_review.state = state
        frame_review.save(update_fields=["state"])
        assert [r["review_state"] for r in ranking_rows(api, run_id, review_state=state)] == [state]
        assert ranking_rows(api, run_id, review_state="unreviewed") == []
    bad = api.get(f"/api/runs/{run_id}/ranking/", {"review_state": "bogus"})
    assert bad.status_code == 400


@pytest.mark.django_db
def test_frame_issues_serves_locked_revision_full_annotations_and_scope(world, monkeypatch):
    monkeypatch.setattr(storages["snapshots"], "url", lambda name: f"https://storage.test/{name}")
    api = client(world["reviewer"])
    claim = api.post(next_url(), {"run_id": world["run"].pk}, format="json")
    frame_id = claim.data["frame"]["id"]
    response = api.get(f"/api/frames/{frame_id}/issues/")
    assert response.status_code == 200, response.data
    assert response.data["snapshot_revision"] == world["run"].snapshot.revision_sha256
    # The shape has no engine candidate yet is still delivered, with class and bbox.
    assert response.data["predictions"] == []
    (annotation,) = response.data["annotations"]
    assert annotation["id"] == "shape:91" and annotation["label_id"] == 1
    assert annotation["bbox"] == {"x1": 1, "y1": 1, "x2": 10, "y2": 10}
    assert response.data["issues"] == []  # read never auto-creates/confirms issues
    # Authorization boundary is unchanged: author (annotator) and out-of-scope users are denied.
    assert client(world["author"]).get(f"/api/frames/{frame_id}/issues/").status_code == 403
    outsider = User.objects.create_user("outsider-r03")
    assert client(outsider).get(f"/api/frames/{frame_id}/issues/").status_code == 403


@pytest.mark.django_db
def test_claim_with_candidate_outside_review_contract_is_422_and_atomic(world):
    """queues_next documents 422: a candidate whose family is not in the contract blocks claim."""
    from orchestration.models import CandidateRecord, ShardCommit

    run = world["run"]
    shard = ShardCommit.objects.create(
        idempotency_key="bogus-shard",
        run=run,
        snapshot_id=run.snapshot_id,
        engine="detector",
        engine_version="v1",
        shard_index=0,
        output_sha256="a" * 64,
    )
    CandidateRecord.objects.create(
        run=run,
        dedup_key="d" * 64,
        shard=shard,
        engine="detector",
        engine_version="v1",
        family="bogus_family",
        cvat_task_id=200,
        frame_number=0,
        anchor={"kind": "prediction_region", "objects": [], "policy_version": "anchor-v1"},
        policy_version="anchor-v1",
        evidence={"engine": "detector"},
        evidence_sha256="e" * 64,
    )
    response = client(world["reviewer"]).post(next_url(), {"run_id": run.pk}, format="json")
    assert response.status_code == 422, response.data
    assert response.data["code"] == "BUSINESS_RULE_UNMET"
    assert not Lease.objects.filter(closed_at__isnull=True).exists()  # nothing half-claimed


@pytest.mark.django_db
def test_ranking_passes_stored_json_through_even_when_unexpected(world):
    """The documented schema must not coerce runtime data (no 500 on odd stored JSON)."""
    entry = RunRankingEntry.objects.filter(ranking__source=RunRanking.Source.RISK).get()
    entry.issue_counts = {"E1": "three", "E2": None, "extra": {"nested": 1}}
    entry.explanation = ["not", "a", "dict"]
    entry.save(update_fields=["issue_counts", "explanation"])
    (row,) = ranking_rows(client(world["reviewer"]), world["run"].pk)
    assert row["issue_counts"] == {"E1": "three", "E2": None, "extra": {"nested": 1}}
    assert row["explanation"] == ["not", "a", "dict"]
