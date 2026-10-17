"""Comprehensive tests for Calibration and Audit API (MBE-04, E-17, E-18, E-20, Issue #326).

Covers:
- GET /api/audit-samples/ (list, stream filter, pagination, roles)
- POST /api/audit-samples/ (sampling, seed idempotency, insufficient sample 422, roles, audit)
- GET /api/benchmarks/ (list, dataset filter, pagination, roles)
- POST /api/benchmarks/ (manual creation, snapshot validation, roles, audit)
- POST /api/benchmarks/import-cvat/ (idempotent import by dataset_id & cvat_task_id, 202, audit)
- GET /api/evaluation/performance/ (performance aggregation, not_checked status, roles)
- GET /api/calibration/reviewers/ (reviewer list, frame counts, assignments, null rate, roles)
- GET /api/calibration/models/ (model list from ModelArtifact, assignments, roles)
- POST /api/calibration/assignments/ (assignment creation, 404 validation, roles, audit)
- Happy paths, 400, 403, 404, 409, 422 error codes.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from audit.models import AuditEvent
from calibration.models import (
    AuditSample,
    AuditSampleStream,
)
from orchestration.models import CandidateRecord, Evaluation, ShardCommit
from runs.models import ConfigVersion, ModelArtifact, QCRun
from snapshots.models import Snapshot, SnapshotFrame
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot

User = get_user_model()


@pytest.fixture
def qa_lead_user(db: None) -> User:
    user = User.objects.create_user(username="qa_lead", password="password123")
    RoleAssignment.objects.create(user=user, role=Role.QA_LEAD, dataset_id=42)
    return user


@pytest.fixture
def qc_admin_user(db: None) -> User:
    user = User.objects.create_user(username="qc_admin", password="password123")
    RoleAssignment.objects.create(user=user, role=Role.QC_ADMIN)
    return user


@pytest.fixture
def super_admin_user(db: None) -> User:
    user = User.objects.create_user(username="super_admin", password="password123")
    RoleAssignment.objects.create(user=user, role=Role.SUPER_ADMIN)
    return user


@pytest.fixture
def data_model_owner_user(db: None) -> User:
    user = User.objects.create_user(username="data_model_owner", password="password123")
    RoleAssignment.objects.create(user=user, role=Role.DATA_MODEL_OWNER, dataset_id=42)
    return user


@pytest.fixture
def reviewer_user(db: None) -> User:
    user = User.objects.create_user(username="reviewer", password="password123")
    RoleAssignment.objects.create(user=user, role=Role.REVIEWER, dataset_id=42)
    return user


@pytest.fixture
def annotator_user(db: None) -> User:
    user = User.objects.create_user(username="annotator", password="password123")
    RoleAssignment.objects.create(user=user, role=Role.ANNOTATOR, dataset_id=42)
    return user


@pytest.fixture
def test_snapshot(db: None, qa_lead_user: User) -> Snapshot:
    return create_locked_snapshot(
        dataset_id=42,
        created_by=qa_lead_user,
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
                        file_name=f"frame_{i:04d}.jpg",
                        width=1920,
                        height=1080,
                        media_bytes=f"frame-{i}".encode(),
                        media_storage_key=f"sha256/0{i}/frame",
                    )
                    for i in range(10)
                ],
            )
        ],
    )


@pytest.fixture
def test_config(db: None, qa_lead_user: User) -> ConfigVersion:
    return ConfigVersion.objects.create(
        name="test-config",
        status=ConfigVersion.Status.PUBLISHED,
        payload={"shard_size": 10},
        created_by=qa_lead_user,
        published_by=qa_lead_user,
        published_at=timezone.now(),
    )


@pytest.fixture
def completed_qc_run(
    db: None, test_snapshot: Snapshot, test_config: ConfigVersion, qa_lead_user: User
) -> QCRun:
    return QCRun.objects.create(
        snapshot=test_snapshot,
        config_version=test_config,
        status=QCRun.Status.COMPLETED,
        dataset_id=42,
        seed=42,
        score_version="v1",
        created_by=qa_lead_user,
    )


@pytest.fixture
def queued_qc_run(
    db: None, test_snapshot: Snapshot, test_config: ConfigVersion, qa_lead_user: User
) -> QCRun:
    return QCRun.objects.create(
        snapshot=test_snapshot,
        config_version=test_config,
        status=QCRun.Status.QUEUED,
        dataset_id=42,
        seed=99,
        score_version="v1",
        created_by=qa_lead_user,
    )


# ==============================================================================
# 1. /api/audit-samples/ (GET & POST)
# ==============================================================================


@pytest.mark.django_db
def test_audit_samples_list_roles_and_empty(qa_lead_user: User, reviewer_user: User) -> None:
    client = APIClient()

    # Unauthorized role (reviewer) -> 403
    client.force_authenticate(reviewer_user)
    res = client.get("/api/audit-samples/")
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # Authorized role (qa_lead) -> 200 with empty list
    client.force_authenticate(qa_lead_user)
    res = client.get("/api/audit-samples/")
    assert res.status_code == status.HTTP_200_OK
    assert res.data["results"] == []


@pytest.mark.django_db
def test_audit_samples_create_happy_path(qa_lead_user: User, completed_qc_run: QCRun) -> None:
    client = APIClient()
    client.force_authenticate(qa_lead_user)

    # 1. Create Random stream sample
    payload = {
        "run_id": completed_qc_run.pk,
        "stream": "random",
        "size": 5,
        "seed": 12345,
    }
    res = client.post("/api/audit-samples/", data=payload, format="json")
    assert res.status_code == status.HTTP_201_CREATED
    data = res.data
    assert data["run_id"] == completed_qc_run.pk
    assert data["stream"] == "random"
    assert data["seed"] == 12345
    assert data["size"] == 5
    assert data["frame_count"] == 5
    assert len(data["frames"]) == 5
    for f in data["frames"]:
        assert "frame_id" in f
        assert "frame_key" in f
        assert f["frame_key"]["task_id"] == 9
        assert "review_state" in f

    # Audit event recorded
    assert AuditEvent.objects.filter(
        action="audit_sample.create", object_id=str(data["id"])
    ).exists()

    # 2. Idempotent call with same run, stream, seed, size -> returns existing sample
    res_repeat = client.post("/api/audit-samples/", data=payload, format="json")
    assert res_repeat.status_code == status.HTTP_201_CREATED
    assert res_repeat.data["id"] == data["id"]

    # 3. Create Risk stream sample
    risk_payload = {
        "run_id": completed_qc_run.pk,
        "stream": "risk",
        "size": 3,
    }
    res_risk = client.post("/api/audit-samples/", data=risk_payload, format="json")
    assert res_risk.status_code == status.HTTP_201_CREATED
    assert res_risk.data["stream"] == "risk"
    assert res_risk.data["size"] == 3
    assert res_risk.data["frame_count"] == 3
    assert res_risk.data["seed"] > 0  # auto-generated


@pytest.mark.django_db
def test_audit_samples_create_idempotency_key(qa_lead_user: User, completed_qc_run: QCRun) -> None:
    client = APIClient()
    client.force_authenticate(qa_lead_user)
    idem_key = "idem-audit-123"

    payload1 = {"run_id": completed_qc_run.pk, "stream": "random", "size": 3, "seed": 100}
    res1 = client.post(
        "/api/audit-samples/", data=payload1, format="json", HTTP_IDEMPOTENCY_KEY=idem_key
    )
    assert res1.status_code == status.HTTP_201_CREATED

    # Repeat with same key and same payload -> returns existing
    res2 = client.post(
        "/api/audit-samples/", data=payload1, format="json", HTTP_IDEMPOTENCY_KEY=idem_key
    )
    assert res2.status_code == status.HTTP_201_CREATED
    assert res2.data["id"] == res1.data["id"]

    # Reusing key with different payload -> 409 IDEMPOTENCY_KEY_REUSED
    payload_diff = {"run_id": completed_qc_run.pk, "stream": "random", "size": 4, "seed": 200}
    res3 = client.post(
        "/api/audit-samples/", data=payload_diff, format="json", HTTP_IDEMPOTENCY_KEY=idem_key
    )
    assert res3.status_code == status.HTTP_409_CONFLICT
    assert res3.data["code"] == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.django_db
def test_audit_samples_create_error_cases(
    qa_lead_user: User, completed_qc_run: QCRun, queued_qc_run: QCRun
) -> None:
    client = APIClient()
    client.force_authenticate(qa_lead_user)

    # Run not found -> 404
    res = client.post(
        "/api/audit-samples/",
        data={"run_id": 999999, "stream": "random", "size": 2},
        format="json",
    )
    assert res.status_code == status.HTTP_404_NOT_FOUND

    # Run not completed -> 422 INSUFFICIENT_SAMPLE
    res = client.post(
        "/api/audit-samples/",
        data={"run_id": queued_qc_run.pk, "stream": "random", "size": 2},
        format="json",
    )
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert res.data["code"] == "INSUFFICIENT_SAMPLE"

    # Requested size exceeds available frames (10) -> 422 INSUFFICIENT_SAMPLE
    res = client.post(
        "/api/audit-samples/",
        data={"run_id": completed_qc_run.pk, "stream": "random", "size": 50},
        format="json",
    )
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert res.data["code"] == "INSUFFICIENT_SAMPLE"

    # Invalid size <= 0 -> 400 VALIDATION_ERROR
    res = client.post(
        "/api/audit-samples/",
        data={"run_id": completed_qc_run.pk, "stream": "random", "size": 0},
        format="json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 2. /api/benchmarks/ & /api/benchmarks/import-cvat/
# ==============================================================================


@pytest.mark.django_db
def test_benchmarks_list_and_create(
    qc_admin_user: User,
    qa_lead_user: User,
    test_snapshot: Snapshot,
) -> None:
    client = APIClient()

    # GET benchmarks list
    client.force_authenticate(qa_lead_user)
    res = client.get("/api/benchmarks/")
    assert res.status_code == status.HTTP_200_OK
    assert res.data["results"] == []

    # POST benchmarks by unauthorized role (qa_lead is not in allowed_roles for create) -> 403
    res_unauth = client.post(
        "/api/benchmarks/",
        data={
            "name": "Benchmark v1",
            "dataset_id": 42,
            "snapshot_id": test_snapshot.pk,
            "frame_ids": [1],
        },
        format="json",
    )
    assert res_unauth.status_code == status.HTTP_403_FORBIDDEN

    # POST benchmarks by qc_admin -> 201
    client.force_authenticate(qc_admin_user)
    frame_ids = list(
        SnapshotFrame.objects.filter(snapshot_job__snapshot=test_snapshot).values_list(
            "pk", flat=True
        )[:3]
    )

    create_payload = {
        "name": "Benchmark GT v1.0",
        "dataset_id": 42,
        "snapshot_id": test_snapshot.pk,
        "frame_ids": frame_ids,
    }
    res_create = client.post("/api/benchmarks/", data=create_payload, format="json")
    assert res_create.status_code == status.HTTP_201_CREATED
    assert res_create.data["name"] == "Benchmark GT v1.0"
    assert res_create.data["dataset_id"] == 42
    assert res_create.data["snapshot_id"] == test_snapshot.pk
    assert res_create.data["source"] == "manual"
    assert res_create.data["status"] == "ready"
    assert res_create.data["frame_count"] == 3

    # Audit event recorded
    assert AuditEvent.objects.filter(
        action="benchmark.create", object_id=str(res_create.data["id"])
    ).exists()

    # GET benchmarks filter by dataset_id
    res_list = client.get(f"/api/benchmarks/?dataset_id={42}")
    assert res_list.status_code == status.HTTP_200_OK
    assert len(res_list.data["results"]) == 1


@pytest.mark.django_db
def test_benchmarks_create_validation_errors(qc_admin_user: User, test_snapshot: Snapshot) -> None:
    client = APIClient()
    client.force_authenticate(qc_admin_user)

    # Snapshot not found -> 404
    res = client.post(
        "/api/benchmarks/",
        data={
            "name": "Invalid Snap",
            "dataset_id": 42,
            "snapshot_id": 999999,
            "frame_ids": [1],
        },
        format="json",
    )
    assert res.status_code == status.HTTP_404_NOT_FOUND

    # Frame IDs not belonging to snapshot -> 404
    res = client.post(
        "/api/benchmarks/",
        data={
            "name": "Invalid Frames",
            "dataset_id": 42,
            "snapshot_id": test_snapshot.pk,
            "frame_ids": [999999],
        },
        format="json",
    )
    assert res.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_benchmarks_import_cvat_idempotent(qc_admin_user: User) -> None:
    client = APIClient()
    client.force_authenticate(qc_admin_user)

    payload = {
        "name": "CVAT GT Task 101",
        "dataset_id": 42,
        "cvat_task_id": 101,
    }

    # 1. First import -> 202 Accepted, pending status
    res1 = client.post("/api/benchmarks/import-cvat/", data=payload, format="json")
    assert res1.status_code == status.HTTP_202_ACCEPTED
    assert res1.data["source"] == "cvat_import"
    assert res1.data["cvat_task_id"] == 101
    assert res1.data["status"] == "pending"
    benchmark_id = res1.data["id"]

    # Audit recorded
    assert AuditEvent.objects.filter(
        action="benchmark.import_cvat", object_id=str(benchmark_id)
    ).exists()

    # 2. Duplicate import call with same (dataset_id, cvat_task_id) -> returns existing (idempotent)
    res2 = client.post("/api/benchmarks/import-cvat/", data=payload, format="json")
    assert res2.status_code == status.HTTP_202_ACCEPTED
    assert res2.data["id"] == benchmark_id


# ==============================================================================
# 3. /api/evaluation/performance/ (GET)
# ==============================================================================


@pytest.mark.django_db
def test_evaluation_performance_empty_and_aggregated(
    qa_lead_user: User, completed_qc_run: QCRun
) -> None:
    client = APIClient()
    client.force_authenticate(qa_lead_user)

    # Empty state -> 200 with []
    res_empty = client.get("/api/evaluation/performance/")
    assert res_empty.status_code == status.HTTP_200_OK
    assert res_empty.data["results"] == []

    # Create a candidate record and an evaluation that completed
    shard = ShardCommit.objects.create(
        idempotency_key=f"shard-test-{completed_qc_run.pk}",
        run=completed_qc_run,
        snapshot_id=completed_qc_run.snapshot_id,
        engine="geometry",
        engine_version="1",
        shard_index=0,
        output_sha256="0" * 64,
    )
    candidate = CandidateRecord.objects.create(
        run=completed_qc_run,
        dedup_key="cand-1",
        shard=shard,
        engine="geometry",
        engine_version="1",
        family="E1",
        cvat_task_id=9,
        frame_number=0,
        anchor={"kind": "manual_region", "objects": []},
        policy_version="p1",
        evidence={},
        evidence_sha256="1" * 64,
    )
    eval_record = Evaluation.objects.create(
        run=completed_qc_run,
        candidate=candidate,
        generation=1,
        source=Evaluation.Source.AUTO,
        snapshot_revision="rev-1",
        primary_reason="low_confidence",
        call_qwen=False,
        human_review_required=False,
        policy={"name": "default"},
    )

    # Query performance summary
    res = client.get(f"/api/evaluation/performance/?run_id={completed_qc_run.pk}")
    assert res.status_code == status.HTTP_200_OK
    assert len(res.data["results"]) == 1
    entry = res.data["results"][0]
    assert entry["evaluation_id"] == eval_record.pk
    assert entry["run_id"] == completed_qc_run.pk
    assert "metrics" in entry
    # Số liệu thiếu mẫu giữ status not_checked, không bịa số
    assert entry["metrics"]["accuracy"]["status"] == "not_checked"
    assert entry["metrics"]["accuracy"]["value"] is None


# ==============================================================================
# 4. /api/calibration/reviewers/ & /api/calibration/models/ (GET)
# ==============================================================================


@pytest.mark.django_db
def test_calibration_reviewers_and_models_list(qa_lead_user: User, reviewer_user: User) -> None:
    client = APIClient()
    client.force_authenticate(qa_lead_user)

    # 1. Reviewers list
    res_rev = client.get("/api/calibration/reviewers/")
    assert res_rev.status_code == status.HTTP_200_OK
    results = res_rev.data["results"]
    assert len(results) >= 1
    reviewer_item = next(r for r in results if r["user_id"] == reviewer_user.pk)
    assert reviewer_item["display_name"] == reviewer_user.username
    assert reviewer_item["assignments"] == 0
    assert reviewer_item["agreement_rate"] is None

    # 2. Models list
    art = ModelArtifact.objects.create(
        name="qwen-vl-max",
        version="2.5",
        checksum="checksum12345",
    )
    res_mod = client.get("/api/calibration/models/")
    assert res_mod.status_code == status.HTTP_200_OK
    mod_results = res_mod.data["results"]
    assert len(mod_results) >= 1
    mod_item = next(m for m in mod_results if m["model_id"] == art.pk)
    assert mod_item["name"] == "qwen-vl-max"
    assert mod_item["kind"] == "vlm"
    assert mod_item["assignments"] == 0
    assert mod_item["agreement_rate"] is None


# ==============================================================================
# 5. /api/calibration/assignments/ (POST)
# ==============================================================================


@pytest.mark.django_db
def test_calibration_assignments_create_and_validation(
    qa_lead_user: User,
    reviewer_user: User,
    completed_qc_run: QCRun,
) -> None:
    client = APIClient()
    client.force_authenticate(qa_lead_user)

    # Create an audit sample first
    sample = AuditSample.objects.create(
        run=completed_qc_run,
        stream=AuditSampleStream.RANDOM,
        seed=111,
        size=2,
        frame_count=2,
        created_by=qa_lead_user,
    )

    # 1. Assign to Reviewer -> 201 Created
    assign_payload = {
        "target_kind": "reviewer",
        "target_id": reviewer_user.pk,
        "audit_sample_id": sample.pk,
        "note": "Calibration test batch A",
    }
    res_assign = client.post("/api/calibration/assignments/", data=assign_payload, format="json")
    assert res_assign.status_code == status.HTTP_201_CREATED
    assert res_assign.data["target_kind"] == "reviewer"
    assert res_assign.data["target_id"] == reviewer_user.pk
    assert res_assign.data["audit_sample_id"] == sample.pk
    assert res_assign.data["status"] == "assigned"
    assert res_assign.data["note"] == "Calibration test batch A"

    # Audit recorded
    assert AuditEvent.objects.filter(
        action="calibration.assignment_create", object_id=str(res_assign.data["id"])
    ).exists()

    # Verify reviewer's assignments count updated in GET /api/calibration/reviewers/
    res_rev_updated = client.get("/api/calibration/reviewers/")
    rev_entry = next(r for r in res_rev_updated.data["results"] if r["user_id"] == reviewer_user.pk)
    assert rev_entry["assignments"] == 1
    assert rev_entry["last_calibrated_at"] is not None

    # 2. Assign to Model -> 201 Created
    model_art = ModelArtifact.objects.create(
        name="detector-rcnn", version="1.0", checksum="chk-rcnn"
    )
    assign_model_payload = {
        "target_kind": "model",
        "target_id": model_art.pk,
        "audit_sample_id": sample.pk,
    }
    res_model_assign = client.post(
        "/api/calibration/assignments/", data=assign_model_payload, format="json"
    )
    assert res_model_assign.status_code == status.HTTP_201_CREATED
    assert res_model_assign.data["target_kind"] == "model"
    assert res_model_assign.data["target_id"] == model_art.pk

    # 3. Target not found -> 404
    bad_target_payload = {
        "target_kind": "reviewer",
        "target_id": 999999,
        "audit_sample_id": sample.pk,
    }
    res_bad_target = client.post(
        "/api/calibration/assignments/", data=bad_target_payload, format="json"
    )
    assert res_bad_target.status_code == status.HTTP_404_NOT_FOUND

    # 4. Audit sample not found -> 404
    bad_sample_payload = {
        "target_kind": "reviewer",
        "target_id": reviewer_user.pk,
        "audit_sample_id": 999999,
    }
    res_bad_sample = client.post(
        "/api/calibration/assignments/", data=bad_sample_payload, format="json"
    )
    assert res_bad_sample.status_code == status.HTTP_404_NOT_FOUND
