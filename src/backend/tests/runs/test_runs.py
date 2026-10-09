"""Comprehensive test suite for QC Run lifecycle, sharding, and idempotency (T-024)."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from audit.models import AuditEvent
from runs.models import ConfigVersion, EngineResult, ModelArtifact, QCRun, WorkUnit
from runs.services import (
    BusinessRuleUnmetError,
    IdempotencyKeyReusedError,
    InvalidTransitionError,
    cancel_qc_run,
    compute_shard_idempotency_key,
    create_qc_run,
    retry_failed_qc_run,
)
from snapshots.models import Snapshot, SnapshotJob


@pytest.fixture
def qa_user(db: None) -> User:
    user = User.objects.create_user(username="qa_lead_user", password="password123")
    RoleAssignment.objects.create(user=user, role=Role.QA_LEAD, dataset_id=42)
    return user


@pytest.fixture
def other_user(db: None) -> User:
    user = User.objects.create_user(username="other_qa_user", password="password123")
    RoleAssignment.objects.create(user=user, role=Role.QA_LEAD, dataset_id=99)
    return user


@pytest.fixture
def locked_snapshot(db: None, qa_user: User) -> Snapshot:
    snap = Snapshot.objects.create(
        dataset_id=42,
        status=Snapshot.Status.LOCKED,
        taxonomy_version="tax-1",
        guideline_version="guide-1",
        schema_version="schema-1",
        revision_sha256="rev-hash-123",
        created_by=qa_user,
        locked_at=timezone.now(),
        normalized_json={
            "jobs": [
                {
                    "cvat_job_id": 101,
                    "frames": [
                        {"frame_index": 0},
                        {"frame_index": 1},
                    ],
                }
            ]
        },
    )
    return snap


@pytest.fixture
def published_config(db: None, qa_user: User) -> ConfigVersion:
    return ConfigVersion.objects.create(
        name="test_config",
        status=ConfigVersion.Status.PUBLISHED,
        payload={"shard_size": 50},
        created_by=qa_user,
        published_by=qa_user,
        published_at=timezone.now(),
    )


# --- 1. Shard Idempotency Key Tests ---

def test_shard_idempotency_key_deterministic_and_sensitive() -> None:
    base_key = compute_shard_idempotency_key(
        snapshot_id=1,
        engine="duplicate",
        engine_version="1.0.0",
        config_version_id=2,
        model_checksum="abc",
        shard_key="job:101:frames:0-1",
    )
    # Order-independent / Deterministic
    same_key = compute_shard_idempotency_key(
        snapshot_id=1,
        engine="duplicate",
        engine_version="1.0.0",
        config_version_id=2,
        model_checksum="abc",
        shard_key="job:101:frames:0-1",
    )
    assert base_key == same_key
    assert len(base_key) == 64

    # Sensitive to snapshot_id
    assert base_key != compute_shard_idempotency_key(
        snapshot_id=99,
        engine="duplicate",
        engine_version="1.0.0",
        config_version_id=2,
        model_checksum="abc",
        shard_key="job:101:frames:0-1",
    )
    # Sensitive to engine
    assert base_key != compute_shard_idempotency_key(
        snapshot_id=1,
        engine="geometry",
        engine_version="1.0.0",
        config_version_id=2,
        model_checksum="abc",
        shard_key="job:101:frames:0-1",
    )
    # Sensitive to engine_version
    assert base_key != compute_shard_idempotency_key(
        snapshot_id=1,
        engine="duplicate",
        engine_version="2.0.0",
        config_version_id=2,
        model_checksum="abc",
        shard_key="job:101:frames:0-1",
    )
    # Sensitive to config_version_id
    assert base_key != compute_shard_idempotency_key(
        snapshot_id=1,
        engine="duplicate",
        engine_version="1.0.0",
        config_version_id=99,
        model_checksum="abc",
        shard_key="job:101:frames:0-1",
    )
    # Sensitive to model_checksum
    assert base_key != compute_shard_idempotency_key(
        snapshot_id=1,
        engine="duplicate",
        engine_version="1.0.0",
        config_version_id=2,
        model_checksum="different_checksum",
        shard_key="job:101:frames:0-1",
    )
    # Sensitive to shard_key
    assert base_key != compute_shard_idempotency_key(
        snapshot_id=1,
        engine="duplicate",
        engine_version="1.0.0",
        config_version_id=2,
        model_checksum="abc",
        shard_key="job:101:frames:2-3",
    )


# --- 2. Run Creation & State Machine Tests ---

@pytest.mark.django_db
def test_create_qc_run_success(locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User) -> None:
    run, created = create_qc_run(
        snapshot_id=locked_snapshot.pk,
        config_version_id=published_config.pk,
        seed=123,
        created_by=qa_user,
        idempotency_key="test-key-1",
    )
    assert created is True
    assert run.status == QCRun.Status.QUEUED
    assert run.dataset_id == 42
    assert run.work_units.count() > 0
    assert run.engine_results.count() > 0

    # Audit recorded
    assert AuditEvent.objects.filter(action="run.create", object_id=str(run.pk)).exists()


@pytest.mark.django_db
def test_create_qc_run_snapshot_not_locked(qa_user: User, published_config: ConfigVersion) -> None:
    pending_snap = Snapshot.objects.create(
        dataset_id=42,
        status=Snapshot.Status.PENDING,
        taxonomy_version="tax-1",
        guideline_version="guide-1",
        schema_version="schema-1",
        created_by=qa_user,
    )
    with pytest.raises(BusinessRuleUnmetError, match="chưa ở trạng thái locked"):
        create_qc_run(
            snapshot_id=pending_snap.pk,
            config_version_id=published_config.pk,
            seed=123,
            created_by=qa_user,
        )


@pytest.mark.django_db
def test_create_qc_run_config_not_published(qa_user: User, locked_snapshot: Snapshot) -> None:
    draft_config = ConfigVersion.objects.create(
        name="draft_cfg",
        status=ConfigVersion.Status.DRAFT,
        created_by=qa_user,
    )
    with pytest.raises(BusinessRuleUnmetError, match="chưa ở trạng thái published"):
        create_qc_run(
            snapshot_id=locked_snapshot.pk,
            config_version_id=draft_config.pk,
            seed=123,
            created_by=qa_user,
        )


# --- 3. Dual Idempotency Tests ---

@pytest.mark.django_db
def test_http_idempotency_same_key_same_payload(locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User) -> None:
    run1, created1 = create_qc_run(
        snapshot_id=locked_snapshot.pk,
        config_version_id=published_config.pk,
        seed=123,
        created_by=qa_user,
        idempotency_key="idem-key-same",
    )
    assert created1 is True

    # Replay
    run2, created2 = create_qc_run(
        snapshot_id=locked_snapshot.pk,
        config_version_id=published_config.pk,
        seed=123,
        created_by=qa_user,
        idempotency_key="idem-key-same",
    )
    assert created2 is False
    assert run1.pk == run2.pk
    assert QCRun.objects.count() == 1


@pytest.mark.django_db
def test_http_idempotency_same_key_different_payload(locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User) -> None:
    create_qc_run(
        snapshot_id=locked_snapshot.pk,
        config_version_id=published_config.pk,
        seed=123,
        created_by=qa_user,
        idempotency_key="idem-key-diff",
    )
    with pytest.raises(IdempotencyKeyReusedError):
        create_qc_run(
            snapshot_id=locked_snapshot.pk,
            config_version_id=published_config.pk,
            seed=456,  # Different seed
            created_by=qa_user,
            idempotency_key="idem-key-diff",
        )


# --- 4. Cancel & Retry-Failed Lifecycle ---

@pytest.mark.django_db
def test_cancel_lifecycle(locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User) -> None:
    run, _ = create_qc_run(
        snapshot_id=locked_snapshot.pk,
        config_version_id=published_config.pk,
        seed=123,
        created_by=qa_user,
    )
    # Cancel from queued
    cancelled_run = cancel_qc_run(run_id=run.pk, actor=qa_user)
    assert cancelled_run.status == QCRun.Status.CANCELLED
    assert cancelled_run.cancel_requested_at is not None

    # Idempotent cancel
    cancelled_again = cancel_qc_run(run_id=run.pk, actor=qa_user)
    assert cancelled_again.status == QCRun.Status.CANCELLED

    # Invalid cancel from completed
    run.status = QCRun.Status.COMPLETED
    run.save(update_fields=["status"])
    with pytest.raises(InvalidTransitionError):
        cancel_qc_run(run_id=run.pk, actor=qa_user)


@pytest.mark.django_db
def test_retry_failed_lifecycle(locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User) -> None:
    run, _ = create_qc_run(
        snapshot_id=locked_snapshot.pk,
        config_version_id=published_config.pk,
        seed=123,
        created_by=qa_user,
    )
    # Cannot retry from queued
    with pytest.raises(InvalidTransitionError):
        retry_failed_qc_run(run_id=run.pk, actor=qa_user)

    # Set run to partial and one work unit to failed
    run.status = QCRun.Status.PARTIAL
    run.save(update_fields=["status"])
    wu = run.work_units.first()
    assert wu is not None
    wu.status = WorkUnit.Status.FAILED
    wu.save(update_fields=["status"])

    retried_run = retry_failed_qc_run(run_id=run.pk, actor=qa_user)
    assert retried_run.status == QCRun.Status.RUNNING

    wu.refresh_from_db()
    assert wu.status == WorkUnit.Status.PENDING
    assert wu.attempt == 2


# --- 5. REST API & RBAC / IDOR Tests ---

@pytest.mark.django_db
def test_api_runs_create_and_retrieve_flow(locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User) -> None:
    client = APIClient()
    client.force_authenticate(user=qa_user)

    # POST /api/runs/
    resp = client.post(
        "/api/runs/",
        {
            "snapshot_id": locked_snapshot.pk,
            "config_version_id": published_config.pk,
            "seed": 42,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-test-key-1",
    )
    assert resp.status_code == 201
    run_id = resp.data["id"]
    assert resp.data["status"] == "queued"
    assert resp.data["snapshot_id"] == locked_snapshot.pk

    # GET /api/runs/{id}/
    detail_resp = client.get(f"/api/runs/{run_id}/")
    assert detail_resp.status_code == 200
    assert detail_resp.data["id"] == run_id

    # GET /api/runs/ list
    list_resp = client.get("/api/runs/", {"dataset": 42})
    assert list_resp.status_code == 200
    assert len(list_resp.data["results"]) == 1

    # POST /api/runs/{id}/cancel/
    cancel_resp = client.post(f"/api/runs/{run_id}/cancel/")
    assert cancel_resp.status_code == 200
    assert cancel_resp.data["status"] == "cancelled"


@pytest.mark.django_db
def test_api_idor_protection(locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User, other_user: User) -> None:
    # qa_user creates run on dataset 42
    run, _ = create_qc_run(
        snapshot_id=locked_snapshot.pk,
        config_version_id=published_config.pk,
        seed=42,
        created_by=qa_user,
    )

    client = APIClient()
    client.force_authenticate(user=other_user)  # Scope: dataset 99

    # Cannot view run 42 (IDOR protection)
    resp = client.get(f"/api/runs/{run.pk}/")
    assert resp.status_code == 403

    # Cannot cancel run 42
    cancel_resp = client.post(f"/api/runs/{run.pk}/cancel/")
    assert cancel_resp.status_code == 403