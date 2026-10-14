from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import CvatIdentity, EmployeeIdentity, Role, RoleAssignment
from audit.models import AuditEvent
from releases.models import Release
from reports.models import EffectivenessReport, ReportExport
from reports.tasks import generate_report_export
from runs.models import ConfigVersion, EngineResult, QCRun
from snapshots.models import Snapshot, SnapshotFrame, SnapshotJob

pytestmark = pytest.mark.django_db


def _user(username: str, role: Role, dataset_id: int | None = 42) -> User:
    user = User.objects.create_user(username=username)
    RoleAssignment.objects.create(user=user, role=role, dataset_id=dataset_id)
    return user


def _client(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def _identity(user: User, number: int, verifier: User) -> None:
    employee = EmployeeIdentity.objects.create(
        employee_id=f"EMP-{number}", verified_at=timezone.now(), verified_by=verifier
    )
    CvatIdentity.objects.create(
        user=user,
        cvat_user_id=number,
        cvat_username=user.username,
        employee=employee,
    )


@pytest.fixture
def world() -> dict[str, object]:
    creator = _user("mbe03-creator", Role.QA_LEAD)
    reviewer = _user("mbe03-reviewer", Role.REVIEWER)
    annotator = _user("mbe03-annotator", Role.ANNOTATOR)
    approver = _user("mbe03-approver", Role.PRODUCT_OWNER)
    outsider = _user("mbe03-outsider", Role.QA_LEAD, 99)
    super_admin = _user("mbe03-super", Role.SUPER_ADMIN, None)
    _identity(creator, 301, super_admin)
    _identity(approver, 302, super_admin)

    snapshot = Snapshot.objects.create(
        dataset_id=42,
        status=Snapshot.Status.PENDING,
        taxonomy_version="tax-1",
        guideline_version="guide-1",
        schema_version="schema-1",
        revision_sha256="a" * 64,
        normalized_json={"dataset": 42},
        created_by=creator,
    )
    job = SnapshotJob.objects.create(
        snapshot=snapshot,
        cvat_job_id=101,
        cvat_task_id=201,
        source_updated_at="2026-10-13T00:00:00Z",
        sha256="b" * 64,
        normalized_json={},
    )
    SnapshotFrame.objects.create(
        snapshot_job=job,
        frame_index=0,
        source_frame_id=1,
        file_name="frame.jpg",
        width=640,
        height=480,
        media_storage_key="frames/frame.jpg",
        media_sha256="c" * 64,
        media_size_bytes=100,
        media_mime_type="image/jpeg",
    )
    config = ConfigVersion.objects.create(
        name="mbe03-config",
        status=ConfigVersion.Status.PUBLISHED,
        created_by=creator,
        published_by=creator,
        published_at=timezone.now(),
    )
    run = QCRun.objects.create(
        snapshot=snapshot,
        config_version=config,
        status=QCRun.Status.COMPLETED,
        dataset_id=42,
        scope_hash="d" * 64,
        score_version="score-v1",
        created_by=creator,
        finished_at=timezone.now(),
    )
    EngineResult.objects.create(
        run=run,
        engine="geometry",
        status="not_checked",
        reason="no_reference",
        required=True,
    )
    return {
        "creator": creator,
        "reviewer": reviewer,
        "annotator": annotator,
        "approver": approver,
        "outsider": outsider,
        "super_admin": super_admin,
        "snapshot": snapshot,
        "config": config,
        "run": run,
    }


def test_run_report_real_data_scope_and_not_found(world: dict[str, object]) -> None:
    run = world["run"]
    response = _client(world["reviewer"]).get(f"/api/runs/{run.pk}/report/")
    assert response.status_code == 200
    assert response.data["run_id"] == run.pk
    assert response.data["source_run_id"] == run.pk
    assert response.data["metrics"] == {
        "run_id": run.pk,
        "status": "completed",
        "frames_total": 1,
        "frames_reviewed": 0,
        "issues_total": 0,
        "issues_by_family": {},
        "issues_by_state": {},
        "reviewed_ratio": 0.0,
    }
    assert response.data["gate"] is None
    assert response.data["release_id"] is None
    assert response.data["engine_coverage"][0]["coverage"] is None
    assert _client(world["outsider"]).get(f"/api/runs/{run.pk}/report/").status_code == 403
    assert _client(world["reviewer"]).get("/api/runs/999999/report/").status_code == 404


def test_report_export_is_idempotent_and_rejects_key_reuse(world: dict[str, object]) -> None:
    run = world["run"]
    api = _client(world["reviewer"])
    url = f"/api/runs/{run.pk}/report/export/"
    first = api.post(url, {"format": "json"}, format="json", HTTP_IDEMPOTENCY_KEY="export-1")
    assert first.status_code == 202
    assert first.data["status"] == "queued"
    replay = api.post(url, {"format": "json"}, format="json", HTTP_IDEMPOTENCY_KEY="export-2")
    assert replay.status_code == 202
    assert replay.data["id"] == first.data["id"]
    assert ReportExport.objects.count() == 1
    collision = api.post(url, {"format": "csv"}, format="json", HTTP_IDEMPOTENCY_KEY="export-1")
    assert collision.status_code == 409
    assert collision.data["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert api.post(url, {"format": "pdf"}, format="json").status_code == 400
    assert (
        _client(world["annotator"])
        .post(url, {"format": "pdf"}, format="json", HTTP_IDEMPOTENCY_KEY="export-a")
        .status_code
        == 403
    )


def test_report_export_worker_materializes_json_csv_and_pdf(
    world: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[tuple[bytes, str]] = []

    class FakeStorage:
        def put(
            self, content: bytes, *, extension: str | None, content_type: str
        ) -> SimpleNamespace:
            captured.append((content, content_type))
            return SimpleNamespace(
                key=f"reports/{extension}/artifact",
                sha256="f" * 64,
                size=len(content),
            )

    monkeypatch.setattr(
        "reports.tasks.ObjectStorage.from_django_settings", lambda _alias: FakeStorage()
    )
    for index, export_format in enumerate(ReportExport.Format.values, start=1):
        export = ReportExport.objects.create(
            run=world["run"],
            format=export_format,
            idempotency_key=f"worker-{index}",
            request_sha256=str(index) * 64,
        )
        generate_report_export.run(export.pk)
        export.refresh_from_db()
        assert export.status == ReportExport.Status.COMPLETED
        assert export.sha256 == "f" * 64
        assert export.finished_at is not None
        if export_format == ReportExport.Format.PDF:
            assert captured[-1][0].startswith(b"%PDF-1.4")
            assert captured[-1][1] == "application/pdf"
        elif export_format == ReportExport.Format.CSV:
            assert captured[-1][0].startswith(b"field,value\n")
            assert captured[-1][1] == "text/csv"
        else:
            assert captured[-1][0].startswith(b"{")
            assert captured[-1][1] == "application/json"


@pytest.mark.skip(
    reason="D-04: GET /api/reports/{id}/ giữ bản MBE-01 (id = KPI evaluation); "
    "route EffectivenessReport của MBE-03 đã gỡ, chờ PO chốt có tách endpoint không"
)
def test_effectiveness_report_json_pdf_csv_and_404(world: dict[str, object]) -> None:
    report = EffectivenessReport.objects.create(
        input_snapshot=world["snapshot"],
        reference_id=77,
        source_run=world["run"],
        source_reason="selected_final",
        score_version="score-v1",
        metrics={
            "agreement": {
                "status": "not_checked",
                "value": None,
                "sample_size": 0,
                "denominator": 0,
                "method": "reference unavailable",
            }
        },
        risk_queue={},
        random_queue={},
        engine_coverage=[],
    )
    api = _client(world["reviewer"])
    response = api.get(f"/api/reports/{report.pk}/")
    assert response.status_code == 200
    assert response.data["reference_id"] == 77
    pdf = api.get(f"/api/reports/{report.pk}/?format=pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF-1.4")
    csv = api.get(f"/api/reports/{report.pk}/?format=csv")
    assert csv.status_code == 200
    assert csv.content.startswith(b"field,value\n")
    assert api.get(f"/api/reports/{report.pk}/?format=xlsx").status_code == 400
    assert api.get("/api/reports/999999/").status_code == 404


def test_release_list_manifest_approval_audit_and_errors(world: dict[str, object]) -> None:
    release = Release.objects.create(
        run=world["run"],
        snapshot=world["snapshot"],
        config_version=world["config"],
        version_tag="v2026.10.13",
        gate_status=Release.GateStatus.PASSED,
        gate={
            "run_id": world["run"].pk,
            "source_run_id": world["run"].pk,
            "source_reason": "selected_final",
            "status": "passed",
            "conditions": [],
        },
        created_by=world["creator"],
    )
    approver = _client(world["approver"])
    listing = approver.get("/api/releases/?status=pending")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.data["results"]] == [release.pk]
    assert approver.get("/api/releases/?status=invalid").status_code == 400
    assert _client(world["outsider"]).get("/api/releases/").data["results"] == []

    first_manifest = approver.get(f"/api/releases/{release.pk}/manifest/")
    second_manifest = approver.get(f"/api/releases/{release.pk}/manifest/")
    assert first_manifest.status_code == 200
    assert first_manifest.data["checksum"] == second_manifest.data["checksum"]
    assert re.fullmatch(r"[0-9a-f]{64}", first_manifest.data["checksum"])
    assert first_manifest.data["artifacts"][0]["name"] == "snapshot"

    approved = approver.post(
        f"/api/releases/{release.pk}/approve/",
        {"note": "Gate đã đạt."},
        format="json",
        HTTP_IDEMPOTENCY_KEY="approve-1",
    )
    assert approved.status_code == 200
    assert approved.data["status"] == "approved"
    assert approved.data["approved_by"] == world["approver"].pk
    event = AuditEvent.objects.get(action="release.approve", object_id=str(release.pk))
    assert event.after["status"] == "approved"
    again = approver.post(
        f"/api/releases/{release.pk}/approve/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="approve-1",
    )
    assert again.status_code == 409
    assert again.data["code"] == "INVALID_TRANSITION"

    blocked = Release.objects.create(
        run=world["run"],
        snapshot=world["snapshot"],
        config_version=world["config"],
        version_tag="v-blocked",
        gate_status=Release.GateStatus.FAILED,
        created_by=world["creator"],
    )
    unmet = approver.post(
        f"/api/releases/{blocked.pk}/approve/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="approve-2",
    )
    assert unmet.status_code == 422
    assert unmet.data["code"] == "BUSINESS_RULE_UNMET"
    assert (
        _client(world["creator"])
        .post(
            f"/api/releases/{blocked.pk}/approve/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="approve-3",
        )
        .status_code
        == 403
    )
    assert approver.get("/api/releases/999999/manifest/").status_code == 404
