"""Comprehensive test suite for QC Run lifecycle, sharding, and idempotency (T-024)."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from audit.models import AuditEvent
from runs.models import ConfigVersion, QCRun, WorkUnit
from runs.services import (
    BusinessRuleUnmetError,
    IdempotencyKeyReusedError,
    InvalidTransitionError,
    cancel_qc_run,
    compute_shard_idempotency_key,
    create_qc_run,
    retry_failed_qc_run,
)
from snapshots.models import Snapshot
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot


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
    # Đi qua service T-021: trigger DB chỉ cho khoá snapshot có aggregate khớp job/frame đã lưu.
    return create_locked_snapshot(
        dataset_id=42,
        created_by=qa_user,
        taxonomy_version="tax-1",
        guideline_version="guide-1",
        jobs=[
            JobExport(
                cvat_job_id=101,
                cvat_task_id=9,
                source_updated_at="2026-10-09T07:05:45Z",
                annotations={"shapes": [], "tracks": []},
                frames=[
                    FrameExport(
                        frame_index=i,
                        file_name=f"{i:06d}.jpg",
                        width=1280,
                        height=720,
                        media_bytes=f"frame-{i}".encode(),
                        media_storage_key=f"sha256/0{i}/frame",
                    )
                    for i in range(2)
                ],
            )
        ],
    )


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
def test_create_qc_run_success(
    locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User
) -> None:
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
def test_http_idempotency_same_key_same_payload(
    locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User
) -> None:
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
def test_http_idempotency_same_key_different_payload(
    locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User
) -> None:
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
def test_cancel_lifecycle(
    locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User
) -> None:
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
def test_retry_failed_lifecycle(
    locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User
) -> None:
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
def test_api_runs_create_and_retrieve_flow(
    locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User
) -> None:
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
def test_api_idor_protection(
    locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User, other_user: User
) -> None:
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


# --- 6. Acceptance criteria T-024 (#66) ---


def _create(snapshot: Snapshot, config: ConfigVersion, user: User, key: str | None = None) -> QCRun:
    run, _ = create_qc_run(
        snapshot_id=snapshot.pk,
        config_version_id=config.pk,
        seed=7,
        created_by=user,
        idempotency_key=key,
    )
    return run


@pytest.mark.django_db
def test_same_input_twice_yields_same_shard_key_set(
    locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User
) -> None:
    first = _create(locked_snapshot, published_config, qa_user)
    second = _create(locked_snapshot, published_config, qa_user)
    assert first.pk != second.pk

    def keys(run: QCRun) -> set[tuple[str, str, str]]:
        return set(run.work_units.values_list("engine", "shard_key", "idempotency_key"))

    assert keys(first) == keys(second) != set()


@pytest.mark.django_db
def test_api_invalid_transitions_return_409(
    locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User
) -> None:
    client = APIClient()
    client.force_authenticate(user=qa_user)
    run = _create(locked_snapshot, published_config, qa_user)

    # retry-failed chỉ hợp lệ từ partial
    resp = client.post(f"/api/runs/{run.pk}/retry-failed/")
    assert resp.status_code == 409
    assert resp.data["code"] == "INVALID_TRANSITION"

    # cancel từ trạng thái terminal
    for terminal in (QCRun.Status.COMPLETED, QCRun.Status.PARTIAL, QCRun.Status.FAILED):
        QCRun.objects.filter(pk=run.pk).update(status=terminal)
        resp = client.post(f"/api/runs/{run.pk}/cancel/")
        assert resp.status_code == 409, terminal
        assert resp.data["code"] == "INVALID_TRANSITION"


@pytest.mark.django_db
def test_api_unknown_run_returns_404(qa_user: User) -> None:
    client = APIClient()
    client.force_authenticate(user=qa_user)
    assert client.get("/api/runs/999999/").status_code == 404
    assert client.post("/api/runs/999999/cancel/").status_code == 404
    assert client.post("/api/runs/999999/retry-failed/").status_code == 404


@pytest.mark.django_db
def test_api_create_idempotency_and_error_codes(
    locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User
) -> None:
    client = APIClient()
    client.force_authenticate(user=qa_user)
    body = {"snapshot_id": locked_snapshot.pk, "config_version_id": published_config.pk, "seed": 1}

    assert (
        client.post("/api/runs/", body, format="json").status_code == 400
    )  # thiếu Idempotency-Key
    first = client.post("/api/runs/", body, format="json", HTTP_IDEMPOTENCY_KEY="k-1")
    again = client.post("/api/runs/", body, format="json", HTTP_IDEMPOTENCY_KEY="k-1")
    assert first.status_code == again.status_code == 201
    assert first.data["id"] == again.data["id"]

    reused = client.post(
        "/api/runs/", {**body, "seed": 2}, format="json", HTTP_IDEMPOTENCY_KEY="k-1"
    )
    assert reused.status_code == 409
    assert reused.data["code"] == "IDEMPOTENCY_KEY_REUSED"

    missing = client.post(
        "/api/runs/", {**body, "snapshot_id": 999999}, format="json", HTTP_IDEMPOTENCY_KEY="k-2"
    )
    assert missing.status_code == 404


# --- 7. Contract test khớp openapi.yaml ---

_JSON_TYPES = {"integer": int, "string": str, "boolean": bool, "array": list, "object": dict}


def _check(value: object, schema: dict, spec: dict, where: str) -> None:
    if "$ref" in schema:
        _check(value, spec["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]], spec, where)
        return
    if value is None and schema.get("nullable"):
        return
    if "allOf" in schema:
        for part in schema["allOf"]:
            _check(value, part, spec, where)
        return
    if value is None:
        assert schema.get("nullable"), f"{where}: null không được phép"
        return
    if "enum" in schema:
        assert value in schema["enum"], f"{where}: {value!r} ngoài enum"
    expected = _JSON_TYPES.get(schema.get("type", ""))
    if expected is not None:
        assert isinstance(value, expected), f"{where}: sai kiểu {type(value).__name__}"
    if isinstance(value, dict):
        for name in schema.get("required", []):
            assert name in value, f"{where}: thiếu {name}"
        for name, sub in schema.get("properties", {}).items():
            if name in value:
                _check(value[name], sub, spec, f"{where}.{name}")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            _check(item, schema["items"], spec, f"{where}[{i}]")


@pytest.mark.django_db
def test_run_responses_match_openapi(
    locked_snapshot: Snapshot, published_config: ConfigVersion, qa_user: User
) -> None:
    import yaml

    from tests.test_contract import CONTRACT

    spec = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    client = APIClient()
    client.force_authenticate(user=qa_user)

    created = client.post(
        "/api/runs/",
        {"snapshot_id": locked_snapshot.pk, "config_version_id": published_config.pk, "seed": 3},
        format="json",
        HTTP_IDEMPOTENCY_KEY="contract-1",
    )
    assert created.status_code == 201
    _check(created.json(), {"$ref": "#/components/schemas/Run"}, spec, "POST /api/runs/")

    run_id = created.json()["id"]
    detail = client.get(f"/api/runs/{run_id}/")
    _check(detail.json(), {"$ref": "#/components/schemas/Run"}, spec, "GET /api/runs/{id}/")

    listing = client.get("/api/runs/", {"dataset": 42})
    _check(
        listing.json(), {"$ref": "#/components/schemas/PaginatedRunList"}, spec, "GET /api/runs/"
    )

    cancelled = client.post(f"/api/runs/{run_id}/cancel/")
    assert cancelled.status_code == 200
    _check(cancelled.json(), {"$ref": "#/components/schemas/Run"}, spec, "cancel")

    QCRun.objects.filter(pk=run_id).update(status=QCRun.Status.PARTIAL)
    retried = client.post(f"/api/runs/{run_id}/retry-failed/")
    assert retried.status_code == 202
    _check(retried.json(), {"$ref": "#/components/schemas/Run"}, spec, "retry-failed")
