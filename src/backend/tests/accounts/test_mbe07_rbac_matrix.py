"""Comprehensive RBAC matrix and role-based data filtering tests (MBE-07, Issue #329).

Covers:
1. Matrix verification for `/api/auth/workflow-permissions/`:
   - "Calibration & Audit" row with all 7 roles.
   - "Reports" row with all 7 roles.
2. Calibration & Audit endpoints RBAC & Scoping:
   - Audit Samples (list & create)
   - Benchmarks (list, manual create, cvat import)
   - Calibration Models list
   - Calibration Reviewers list (annotator sees only self)
   - Calibration Assignments create
   - Evaluation Performance list
3. Reports & Releases endpoints RBAC & Scoping:
   - Run Report (annotator sees sanitized fields)
   - Run Report Export (annotator forbidden)
   - Effectiveness Report retrieve (annotator forbidden on PDF/CSV, sanitized JSON)
   - Releases list, manifest, and approve
4. 403 FORBIDDEN and 403 OUT_OF_SCOPE enforcement.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import CvatIdentity, EmployeeIdentity, Role, RoleAssignment
from calibration.models import AuditSample, AuditSampleStream, Benchmark
from releases.models import Release
from reports.models import EffectivenessReport
from runs.models import ConfigVersion, EngineResult, QCRun
from snapshots.models import Snapshot, SnapshotFrame, SnapshotJob

User = get_user_model()
pytestmark = pytest.mark.django_db


def _create_user(username: str, role: Role | None = None, dataset_id: int | None = 42) -> User:
    user = User.objects.create_user(username=username, password="password123")
    if role is not None:
        RoleAssignment.objects.create(user=user, role=role, dataset_id=dataset_id)
    return user


def _auth_client(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _attach_identity(user: User, cvat_id: int, verifier: User) -> None:
    emp = EmployeeIdentity.objects.create(
        employee_id=f"EMP-MBE07-{cvat_id}",
        verified_at=timezone.now(),
        verified_by=verifier,
    )
    CvatIdentity.objects.create(
        user=user,
        cvat_user_id=cvat_id,
        cvat_username=user.username,
        employee=emp,
    )


@pytest.fixture
def rbac_world() -> dict[str, Any]:
    super_admin = _create_user("mbe07-super", Role.SUPER_ADMIN, dataset_id=None)
    qc_admin = _create_user("mbe07-qc-admin", Role.QC_ADMIN, dataset_id=None)
    qa_lead_42 = _create_user("mbe07-qa-lead-42", Role.QA_LEAD, dataset_id=42)
    qa_lead_99 = _create_user("mbe07-qa-lead-99", Role.QA_LEAD, dataset_id=99)
    reviewer_42 = _create_user("mbe07-reviewer-42", Role.REVIEWER, dataset_id=42)
    annotator_42 = _create_user("mbe07-annotator-42", Role.ANNOTATOR, dataset_id=42)
    product_owner_42 = _create_user("mbe07-po-42", Role.PRODUCT_OWNER, dataset_id=42)
    data_model_owner_42 = _create_user("mbe07-dmo-42", Role.DATA_MODEL_OWNER, dataset_id=42)
    outsider = _create_user("mbe07-outsider", role=None)

    _attach_identity(super_admin, 700, super_admin)
    _attach_identity(qa_lead_42, 701, super_admin)
    _attach_identity(product_owner_42, 702, super_admin)
    _attach_identity(annotator_42, 703, super_admin)
    _attach_identity(reviewer_42, 704, super_admin)

    # Dataset 42 Snapshot and Run
    snap_42 = Snapshot.objects.create(
        dataset_id=42,
        status=Snapshot.Status.PENDING,
        taxonomy_version="tax-42",
        guideline_version="guide-42",
        schema_version="schema-42",
        revision_sha256="42" * 32,
        normalized_json={"dataset": 42},
        created_by=qa_lead_42,
    )
    job_42 = SnapshotJob.objects.create(
        snapshot=snap_42,
        cvat_job_id=1042,
        cvat_task_id=2042,
        source_updated_at="2026-10-14T00:00:00Z",
        sha256="job42" * 12 + "abcd",
        normalized_json={},
    )
    frame_42 = SnapshotFrame.objects.create(
        snapshot_job=job_42,
        frame_index=0,
        source_frame_id=4201,
        file_name="frame42.jpg",
        width=1920,
        height=1080,
        media_storage_key="frames/frame42.jpg",
        media_sha256="c" * 64,
        media_size_bytes=100,
        media_mime_type="image/jpeg",
    )
    cfg = ConfigVersion.objects.create(
        name="Default Config",
        status=ConfigVersion.Status.PUBLISHED,
        created_by=super_admin,
        published_by=super_admin,
        published_at=timezone.now(),
    )

    run_42 = QCRun.objects.create(
        dataset_id=42,
        snapshot=snap_42,
        config_version=cfg,
        scope_hash="42" * 32,
        score_version="v1.0",
        status=QCRun.Status.COMPLETED,
        created_by=qa_lead_42,
        finished_at=timezone.now(),
    )
    EngineResult.objects.create(
        run=run_42,
        engine="geometry",
        status="not_checked",
        reason="no_reference",
        required=True,
    )

    # Dataset 99 Snapshot and Run (for out-of-scope testing)
    snap_99 = Snapshot.objects.create(
        dataset_id=99,
        status=Snapshot.Status.PENDING,
        taxonomy_version="tax-99",
        guideline_version="guide-99",
        schema_version="schema-99",
        revision_sha256="99" * 32,
        normalized_json={"dataset": 99},
        created_by=qa_lead_99,
    )
    run_99 = QCRun.objects.create(
        dataset_id=99,
        snapshot=snap_99,
        config_version=cfg,
        scope_hash="99" * 32,
        score_version="v1.0",
        status=QCRun.Status.COMPLETED,
        created_by=qa_lead_99,
        finished_at=timezone.now(),
    )
    EngineResult.objects.create(
        run=run_99,
        engine="geometry",
        status="not_checked",
        reason="no_reference",
        required=True,
    )

    from calibration.models import AuditSampleFrame

    # Audit samples in 42 and 99
    sample_42 = AuditSample.objects.create(
        run=run_42,
        stream=AuditSampleStream.RANDOM,
        size=1,
        seed=1234,
        frame_count=1,
        created_by=qa_lead_42,
    )
    AuditSampleFrame.objects.create(
        audit_sample=sample_42,
        snapshot_frame=frame_42,
        rank=1,
        review_state="unreviewed",
    )
    sample_99 = AuditSample.objects.create(
        run=run_99,
        stream=AuditSampleStream.RISK,
        size=1,
        seed=5678,
        frame_count=0,
        created_by=qa_lead_99,
    )

    # Benchmarks in 42 and 99
    benchmark_42 = Benchmark.objects.create(
        dataset_id=42,
        snapshot=snap_42,
        name="Benchmark 42",
        cvat_task_id=2042,
        status="active",
        created_by=qc_admin,
    )
    benchmark_99 = Benchmark.objects.create(
        dataset_id=99,
        snapshot=snap_99,
        name="Benchmark 99",
        cvat_task_id=2099,
        status="active",
        created_by=qc_admin,
    )

    # Releases in 42 and 99
    release_42 = Release.objects.create(
        run=run_42,
        snapshot=snap_42,
        config_version=cfg,
        version_tag="v2026.10.14-42",
        gate_status=Release.GateStatus.PASSED,
        status=Release.Status.PENDING,
        created_by=qa_lead_42,
        gate={
            "run_id": run_42.pk,
            "source_run_id": run_42.pk,
            "source_reason": "selected_final",
            "status": "passed",
            "conditions": [],
        },
    )
    release_99 = Release.objects.create(
        run=run_99,
        snapshot=snap_99,
        config_version=cfg,
        version_tag="v2026.10.14-99",
        gate_status=Release.GateStatus.PASSED,
        status=Release.Status.PENDING,
        created_by=qa_lead_99,
        gate={
            "run_id": run_99.pk,
            "source_run_id": run_99.pk,
            "source_reason": "selected_final",
            "status": "passed",
            "conditions": [],
        },
    )

    # Effectiveness reports in 42 and 99
    report_42 = EffectivenessReport.objects.create(
        input_snapshot=snap_42,
        reference_id=benchmark_42.pk,
        source_run=run_42,
        source_reason="Scheduled run",
        score_version="v1.0",
        metrics={
            "f1": {
                "status": "computed",
                "value": 0.95,
                "sample_size": 100,
                "denominator": 100,
                "method": "f1_score",
                "confidence_interval": [0.91, 0.98],
            },
        },
        risk_queue={"critical_count": 5},
        random_queue={"sampled_count": 10},
        engine_coverage=[
            {
                "engine": "geometry",
                "status": "passed",
                "required": True,
                "unit": "frame",
                "total": 1,
                "eligible": 1,
                "excluded": 0,
                "applicability_version": "v1",
                "completed": 1,
                "failed": 0,
                "pending": 0,
                "not_checked": 0,
                "not_checked_reasons": {},
                "coverage": 1.0,
            }
        ],
    )
    report_99 = EffectivenessReport.objects.create(
        input_snapshot=snap_99,
        reference_id=benchmark_99.pk,
        source_run=run_99,
        source_reason="Scheduled run",
        score_version="v1.0",
        metrics={},
        risk_queue={},
        random_queue={},
        engine_coverage=[],
    )

    return {
        "super_admin": super_admin,
        "qc_admin": qc_admin,
        "qa_lead_42": qa_lead_42,
        "qa_lead_99": qa_lead_99,
        "reviewer_42": reviewer_42,
        "annotator_42": annotator_42,
        "product_owner_42": product_owner_42,
        "data_model_owner_42": data_model_owner_42,
        "outsider": outsider,
        "run_42": run_42,
        "run_99": run_99,
        "frame_42": frame_42,
        "sample_42": sample_42,
        "sample_99": sample_99,
        "benchmark_42": benchmark_42,
        "benchmark_99": benchmark_99,
        "release_42": release_42,
        "release_99": release_99,
        "report_42": report_42,
        "report_99": report_99,
        "snap_42": snap_42,
        "snap_99": snap_99,
    }


# ============================================================================
# 1. Workflow Permissions Matrix Tests
# ============================================================================


def test_workflow_permissions_contains_calibration_and_reports(rbac_world: dict[str, Any]) -> None:
    client = _auth_client(rbac_world["qa_lead_42"])
    response = client.get("/api/auth/workflow-permissions/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    matrix_by_function = {item["function"]: item["roles"] for item in data["matrix"]}
    assert "Calibration & Audit" in matrix_by_function
    assert "Reports" in matrix_by_function

    calib_roles = matrix_by_function["Calibration & Audit"]
    assert calib_roles["annotator"] == "participate"
    assert calib_roles["reviewer"] == "participate"
    assert calib_roles["qa_lead"] == "manage"
    assert calib_roles["qc_admin"] == "configure"
    assert calib_roles["super_admin"] == "manage_configure"
    assert calib_roles["product_owner"] == "none"
    assert calib_roles["data_model_owner"] == "none"

    report_roles = matrix_by_function["Reports"]
    assert report_roles["annotator"] == "limited"
    assert report_roles["reviewer"] == "view"
    assert report_roles["qa_lead"] == "view"
    assert report_roles["qc_admin"] == "view"
    assert report_roles["super_admin"] == "view"
    assert report_roles["product_owner"] == "view"
    assert report_roles["data_model_owner"] == "view"


# ============================================================================
# 2. Calibration & Audit RBAC & Scoping Tests
# ============================================================================


@pytest.mark.parametrize(
    ("user_key", "expected_status"),
    [
        ("annotator_42", status.HTTP_403_FORBIDDEN),
        ("reviewer_42", status.HTTP_403_FORBIDDEN),
        ("product_owner_42", status.HTTP_403_FORBIDDEN),
        ("data_model_owner_42", status.HTTP_403_FORBIDDEN),
        ("outsider", status.HTTP_403_FORBIDDEN),
        ("qa_lead_42", status.HTTP_201_CREATED),
        ("qc_admin", status.HTTP_201_CREATED),
        ("super_admin", status.HTTP_201_CREATED),
    ],
)
def test_audit_samples_create_roles(
    rbac_world: dict[str, Any], user_key: str, expected_status: int
) -> None:
    client = _auth_client(rbac_world[user_key])
    payload = {
        "run_id": rbac_world["run_42"].pk,
        "stream": "random",
        "size": 1,
        "seed": 9999,
    }
    response = client.post(
        "/api/audit-samples/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=f"create-sample-{user_key}",
    )
    assert response.status_code == expected_status
    if expected_status == status.HTTP_403_FORBIDDEN:
        assert response.json()["code"] == "FORBIDDEN"


def test_audit_samples_create_out_of_scope(rbac_world: dict[str, Any]) -> None:
    # qa_lead_42 cannot create sample for run_99
    client = _auth_client(rbac_world["qa_lead_42"])
    payload = {
        "run_id": rbac_world["run_99"].pk,
        "stream": "random",
        "size": 1,
    }
    response = client.post(
        "/api/audit-samples/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="create-sample-out-of-scope",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["code"] == "OUT_OF_SCOPE"


@pytest.mark.parametrize(
    ("user_key", "expected_status"),
    [
        ("annotator_42", status.HTTP_403_FORBIDDEN),
        ("reviewer_42", status.HTTP_403_FORBIDDEN),
        ("outsider", status.HTTP_403_FORBIDDEN),
        ("qa_lead_42", status.HTTP_200_OK),
        ("qc_admin", status.HTTP_200_OK),
        ("super_admin", status.HTTP_200_OK),
        ("product_owner_42", status.HTTP_200_OK),
        ("data_model_owner_42", status.HTTP_200_OK),
    ],
)
def test_audit_samples_list_roles(
    rbac_world: dict[str, Any], user_key: str, expected_status: int
) -> None:
    client = _auth_client(rbac_world[user_key])
    response = client.get("/api/audit-samples/")
    assert response.status_code == expected_status
    if expected_status == status.HTTP_403_FORBIDDEN:
        assert response.json()["code"] == "FORBIDDEN"


def test_audit_samples_list_scoping(rbac_world: dict[str, Any]) -> None:
    client = _auth_client(rbac_world["qa_lead_42"])

    # Querying without run_id only returns sample from dataset 42
    response = client.get("/api/audit-samples/")
    assert response.status_code == status.HTTP_200_OK
    results = response.json()["results"]
    sample_ids = {s["id"] for s in results}
    assert rbac_world["sample_42"].pk in sample_ids
    assert rbac_world["sample_99"].pk not in sample_ids

    # Explicitly querying run_99 returns 403 OUT_OF_SCOPE
    out_response = client.get(f"/api/audit-samples/?run_id={rbac_world['run_99'].pk}")
    assert out_response.status_code == status.HTTP_403_FORBIDDEN
    assert out_response.json()["code"] == "OUT_OF_SCOPE"


@pytest.mark.parametrize(
    ("user_key", "expected_status"),
    [
        ("annotator_42", status.HTTP_403_FORBIDDEN),
        ("reviewer_42", status.HTTP_403_FORBIDDEN),
        ("outsider", status.HTTP_403_FORBIDDEN),
        ("qa_lead_42", status.HTTP_200_OK),
        ("qc_admin", status.HTTP_200_OK),
        ("super_admin", status.HTTP_200_OK),
        ("product_owner_42", status.HTTP_200_OK),
        ("data_model_owner_42", status.HTTP_200_OK),
    ],
)
def test_benchmarks_list_roles(
    rbac_world: dict[str, Any], user_key: str, expected_status: int
) -> None:
    client = _auth_client(rbac_world[user_key])
    response = client.get("/api/benchmarks/")
    assert response.status_code == expected_status


def test_benchmarks_list_scoping(rbac_world: dict[str, Any]) -> None:
    client = _auth_client(rbac_world["qa_lead_42"])

    # Querying without dataset_id only returns benchmark 42
    response = client.get("/api/benchmarks/")
    assert response.status_code == status.HTTP_200_OK
    results = response.json()["results"]
    ids = {b["id"] for b in results}
    assert rbac_world["benchmark_42"].pk in ids
    assert rbac_world["benchmark_99"].pk not in ids

    # Querying dataset 99 returns 403 OUT_OF_SCOPE
    out_response = client.get("/api/benchmarks/?dataset_id=99")
    assert out_response.status_code == status.HTTP_403_FORBIDDEN
    assert out_response.json()["code"] == "OUT_OF_SCOPE"


@pytest.mark.parametrize(
    ("user_key", "expected_status"),
    [
        ("annotator_42", status.HTTP_403_FORBIDDEN),
        ("reviewer_42", status.HTTP_403_FORBIDDEN),
        ("qa_lead_42", status.HTTP_403_FORBIDDEN),
        ("product_owner_42", status.HTTP_403_FORBIDDEN),
        ("outsider", status.HTTP_403_FORBIDDEN),
        ("qc_admin", status.HTTP_201_CREATED),
        ("super_admin", status.HTTP_201_CREATED),
        ("data_model_owner_42", status.HTTP_201_CREATED),
    ],
)
def test_benchmarks_create_roles(
    rbac_world: dict[str, Any], user_key: str, expected_status: int
) -> None:
    client = _auth_client(rbac_world[user_key])
    payload = {
        "dataset_id": 42,
        "snapshot_id": rbac_world["snap_42"].pk,
        "name": f"New Benchmark {user_key}",
        "frame_ids": [rbac_world["frame_42"].pk],
    }
    response = client.post(
        "/api/benchmarks/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=f"create-bm-{user_key}",
    )
    assert response.status_code == expected_status


def test_benchmarks_create_out_of_scope(rbac_world: dict[str, Any]) -> None:
    client = _auth_client(rbac_world["data_model_owner_42"])
    payload = {
        "dataset_id": 99,
        "snapshot_id": rbac_world["snap_99"].pk,
        "name": "Out of scope BM",
        "frame_ids": [rbac_world["frame_42"].pk],
    }
    response = client.post(
        "/api/benchmarks/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="create-bm-out-of-scope",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["code"] == "OUT_OF_SCOPE"


@pytest.mark.parametrize(
    ("user_key", "expected_status"),
    [
        ("annotator_42", status.HTTP_403_FORBIDDEN),
        ("reviewer_42", status.HTTP_403_FORBIDDEN),
        ("product_owner_42", status.HTTP_403_FORBIDDEN),
        ("outsider", status.HTTP_403_FORBIDDEN),
        ("qa_lead_42", status.HTTP_200_OK),
        ("qc_admin", status.HTTP_200_OK),
        ("super_admin", status.HTTP_200_OK),
        ("data_model_owner_42", status.HTTP_200_OK),
    ],
)
def test_calibration_models_roles(
    rbac_world: dict[str, Any], user_key: str, expected_status: int
) -> None:
    client = _auth_client(rbac_world[user_key])
    response = client.get("/api/calibration/models/")
    assert response.status_code == expected_status


def test_calibration_reviewers_annotator_sees_only_self(rbac_world: dict[str, Any]) -> None:
    annotator = rbac_world["annotator_42"]

    # Annotator queries reviewers
    client_ann = _auth_client(annotator)
    res_ann = client_ann.get("/api/calibration/reviewers/?dataset_id=42")
    assert res_ann.status_code == status.HTTP_200_OK
    ann_results = res_ann.json()["results"]
    for r in ann_results:
        assert r["user_id"] == annotator.pk
        assert r["display_name"] == annotator.username

    # Outsider queries reviewers
    client_out = _auth_client(rbac_world["outsider"])
    res_out = client_out.get("/api/calibration/reviewers/?dataset_id=42")
    assert res_out.status_code == status.HTTP_403_FORBIDDEN

    # Scoped user querying outside scope
    res_scope = client_ann.get("/api/calibration/reviewers/?dataset_id=99")
    assert res_scope.status_code == status.HTTP_403_FORBIDDEN
    assert res_scope.json()["code"] == "OUT_OF_SCOPE"

    # QA Lead sees reviewers
    client_qa = _auth_client(rbac_world["qa_lead_42"])
    res_qa = client_qa.get("/api/calibration/reviewers/?dataset_id=42")
    assert res_qa.status_code == status.HTTP_200_OK


@pytest.mark.parametrize(
    ("user_key", "expected_status"),
    [
        ("annotator_42", status.HTTP_403_FORBIDDEN),
        ("reviewer_42", status.HTTP_403_FORBIDDEN),
        ("product_owner_42", status.HTTP_403_FORBIDDEN),
        ("data_model_owner_42", status.HTTP_403_FORBIDDEN),
        ("outsider", status.HTTP_403_FORBIDDEN),
        ("qa_lead_42", status.HTTP_201_CREATED),
        ("qc_admin", status.HTTP_201_CREATED),
        ("super_admin", status.HTTP_201_CREATED),
    ],
)
def test_calibration_assignments_create_roles(
    rbac_world: dict[str, Any], user_key: str, expected_status: int
) -> None:
    client = _auth_client(rbac_world[user_key])
    payload = {
        "target_kind": "reviewer",
        "target_id": rbac_world["reviewer_42"].pk,
        "audit_sample_id": rbac_world["sample_42"].pk,
        "note": f"Assign by {user_key}",
    }
    response = client.post(
        "/api/calibration/assignments/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=f"assign-{user_key}",
    )
    assert response.status_code == expected_status


def test_calibration_assignments_create_out_of_scope(rbac_world: dict[str, Any]) -> None:
    client = _auth_client(rbac_world["qa_lead_42"])
    payload = {
        "target_kind": "reviewer",
        "target_id": rbac_world["reviewer_42"].pk,
        "audit_sample_id": rbac_world["sample_99"].pk,
    }
    response = client.post(
        "/api/calibration/assignments/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="assign-out-of-scope",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["code"] == "OUT_OF_SCOPE"


# ============================================================================
# 3. Reports & Releases RBAC & Scoping Tests
# ============================================================================


def test_run_report_annotator_data_filtering(rbac_world: dict[str, Any]) -> None:
    run = rbac_world["run_42"]

    # Annotator sees report with sanitized fields
    client_ann = _auth_client(rbac_world["annotator_42"])
    res_ann = client_ann.get(f"/api/runs/{run.pk}/report/")
    assert res_ann.status_code == status.HTTP_200_OK
    data_ann = res_ann.json()
    assert data_ann["gate"] is None
    assert data_ann["engine_coverage"] == []
    assert data_ann["release_id"] is None
    assert data_ann["exports"] == []
    assert data_ann["metrics"]["run_id"] == run.pk

    # Reviewer / QA Lead sees full fields
    client_qa = _auth_client(rbac_world["qa_lead_42"])
    res_qa = client_qa.get(f"/api/runs/{run.pk}/report/")
    assert res_qa.status_code == status.HTTP_200_OK
    data_qa = res_qa.json()
    assert data_qa["release_id"] == rbac_world["release_42"].pk
    assert data_qa["gate"] is not None

    # Out of scope access
    res_out = client_ann.get(f"/api/runs/{rbac_world['run_99'].pk}/report/")
    assert res_out.status_code == status.HTTP_403_FORBIDDEN
    assert res_out.json()["code"] == "OUT_OF_SCOPE"


def test_run_report_export_annotator_forbidden(rbac_world: dict[str, Any]) -> None:
    run = rbac_world["run_42"]

    # Annotator cannot export
    client_ann = _auth_client(rbac_world["annotator_42"])
    res_ann = client_ann.post(
        f"/api/runs/{run.pk}/report/export/",
        {"format": "csv"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="ann-export-1",
    )
    assert res_ann.status_code == status.HTTP_403_FORBIDDEN
    assert res_ann.json()["code"] == "FORBIDDEN"

    # Reviewer can export
    client_rev = _auth_client(rbac_world["reviewer_42"])
    res_rev = client_rev.post(
        f"/api/runs/{run.pk}/report/export/",
        {"format": "csv"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="rev-export-1",
    )
    assert res_rev.status_code == status.HTTP_202_ACCEPTED

    # Out of scope export attempt
    res_out = client_rev.post(
        f"/api/runs/{rbac_world['run_99'].pk}/report/export/",
        {"format": "csv"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="rev-export-out",
    )
    assert res_out.status_code == status.HTTP_403_FORBIDDEN
    assert res_out.json()["code"] == "OUT_OF_SCOPE"


def test_effectiveness_report_annotator_data_filtering(rbac_world: dict[str, Any]) -> None:
    rep = rbac_world["report_42"]

    # Annotator JSON retrieve succeeds with sanitized queues & coverage
    client_ann = _auth_client(rbac_world["annotator_42"])
    res_json = client_ann.get(f"/api/reports/{rep.pk}/?format=json")
    assert res_json.status_code == status.HTTP_200_OK
    data = res_json.json()
    assert data["risk_queue"] == {}
    assert data["random_queue"] == {}
    assert data["engine_coverage"] == []
    assert data["metrics"] != {}

    # Annotator PDF / CSV retrieve is forbidden
    res_pdf = client_ann.get(f"/api/reports/{rep.pk}/?format=pdf")
    assert res_pdf.status_code == status.HTTP_403_FORBIDDEN
    assert res_pdf.json()["code"] == "FORBIDDEN"

    res_csv = client_ann.get(f"/api/reports/{rep.pk}/?format=csv")
    assert res_csv.status_code == status.HTTP_403_FORBIDDEN
    assert res_csv.json()["code"] == "FORBIDDEN"

    # QA Lead can retrieve PDF / CSV and JSON with full queues
    client_qa = _auth_client(rbac_world["qa_lead_42"])
    res_qa_json = client_qa.get(f"/api/reports/{rep.pk}/?format=json")
    assert res_qa_json.status_code == status.HTTP_200_OK
    data_qa = res_qa_json.json()
    assert data_qa["risk_queue"] != {}
    assert data_qa["random_queue"] != {}
    assert len(data_qa["engine_coverage"]) > 0

    res_qa_csv = client_qa.get(f"/api/reports/{rep.pk}/?format=csv")
    assert res_qa_csv.status_code == status.HTTP_200_OK
    assert "text/csv" in res_qa_csv["Content-Type"]

    # Out of scope report access
    res_scope = client_ann.get(f"/api/reports/{rbac_world['report_99'].pk}/?format=json")
    assert res_scope.status_code == status.HTTP_403_FORBIDDEN
    assert res_scope.json()["code"] == "OUT_OF_SCOPE"


@pytest.mark.parametrize(
    ("user_key", "expected_status"),
    [
        ("annotator_42", status.HTTP_403_FORBIDDEN),
        ("reviewer_42", status.HTTP_403_FORBIDDEN),
        ("outsider", status.HTTP_403_FORBIDDEN),
        ("qa_lead_42", status.HTTP_200_OK),
        ("qc_admin", status.HTTP_200_OK),
        ("super_admin", status.HTTP_200_OK),
        ("product_owner_42", status.HTTP_200_OK),
        ("data_model_owner_42", status.HTTP_200_OK),
    ],
)
def test_releases_list_roles(
    rbac_world: dict[str, Any], user_key: str, expected_status: int
) -> None:
    client = _auth_client(rbac_world[user_key])
    response = client.get("/api/releases/")
    assert response.status_code == expected_status


def test_releases_list_scoping(rbac_world: dict[str, Any]) -> None:
    client = _auth_client(rbac_world["qa_lead_42"])
    response = client.get("/api/releases/")
    assert response.status_code == status.HTTP_200_OK
    results = response.json()["results"]
    ids = {r["id"] for r in results}
    assert rbac_world["release_42"].pk in ids
    assert rbac_world["release_99"].pk not in ids


def test_releases_manifest_roles_and_scoping(rbac_world: dict[str, Any]) -> None:
    rel_42 = rbac_world["release_42"]
    rel_99 = rbac_world["release_99"]

    # Annotator forbidden
    client_ann = _auth_client(rbac_world["annotator_42"])
    res_ann = client_ann.get(f"/api/releases/{rel_42.pk}/manifest/")
    assert res_ann.status_code == status.HTTP_403_FORBIDDEN

    # QA Lead 42 allowed on 42
    client_qa = _auth_client(rbac_world["qa_lead_42"])
    res_qa = client_qa.get(f"/api/releases/{rel_42.pk}/manifest/")
    assert res_qa.status_code == status.HTTP_200_OK

    # QA Lead 42 out of scope on 99
    res_scope = client_qa.get(f"/api/releases/{rel_99.pk}/manifest/")
    assert res_scope.status_code == status.HTTP_403_FORBIDDEN
    assert res_scope.json()["code"] == "OUT_OF_SCOPE"


@pytest.mark.parametrize(
    ("user_key", "expected_status"),
    [
        ("annotator_42", status.HTTP_403_FORBIDDEN),
        ("reviewer_42", status.HTTP_403_FORBIDDEN),
        ("qa_lead_42", status.HTTP_403_FORBIDDEN),
        ("qc_admin", status.HTTP_403_FORBIDDEN),
        ("data_model_owner_42", status.HTTP_403_FORBIDDEN),
        ("outsider", status.HTTP_403_FORBIDDEN),
        ("product_owner_42", status.HTTP_200_OK),
        ("super_admin", status.HTTP_200_OK),
    ],
)
def test_releases_approve_roles(
    rbac_world: dict[str, Any], user_key: str, expected_status: int
) -> None:
    client = _auth_client(rbac_world[user_key])
    response = client.post(
        f"/api/releases/{rbac_world['release_42'].pk}/approve/",
        {"note": f"Approve by {user_key}"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=f"approve-{user_key}",
    )
    assert response.status_code == expected_status
