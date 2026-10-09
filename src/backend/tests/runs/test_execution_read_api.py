"""Read APIs used by AnalysisConfig and ExecutionHistory."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from orchestration.models import LedgerUnit
from runs.models import ConfigVersion, QCRun
from runs.services import create_qc_run
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot

pytestmark = pytest.mark.django_db(transaction=True)


def _actor(role: Role, dataset_id: int) -> APIClient:
    user = User.objects.create_user(username=f"execution-{role}-{dataset_id}")
    RoleAssignment.objects.create(user=user, role=role, dataset_id=dataset_id)
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_config_list_ledger_and_shards_are_real_and_dataset_scoped() -> None:
    client = _actor(Role.QA_LEAD, 42)
    user = User.objects.get(username="execution-qa_lead-42")
    other = _actor(Role.QA_LEAD, 99)
    snapshot = create_locked_snapshot(
        dataset_id=42,
        created_by=user,
        taxonomy_version="tax-1",
        guideline_version="guide-1",
        jobs=[
            JobExport(
                cvat_job_id=17,
                cvat_task_id=9,
                source_updated_at="2026-10-09T07:05:45Z",
                annotations={"shapes": [], "tracks": []},
                frames=[
                    FrameExport(
                        frame_index=index,
                        file_name=f"{index}.jpg",
                        width=640,
                        height=480,
                        media_bytes=f"frame-{index}".encode(),
                        media_storage_key=f"frames/{index}",
                    )
                    for index in range(2)
                ],
            )
        ],
    )
    config = ConfigVersion.objects.create(
        name="Published",
        status=ConfigVersion.Status.PUBLISHED,
        created_by=user,
        engines={"duplicate": {"enabled": True}, "geometry": {"enabled": False}},
    )
    run, _ = create_qc_run(
        snapshot_id=snapshot.pk,
        config_version_id=config.pk,
        seed=7,
        created_by=user,
        idempotency_key="execution-read-api",
    )
    result = run.engine_results.get(engine="duplicate")
    result.applicability_version = "2026.10"
    result.save(update_fields=["applicability_version"])
    LedgerUnit.objects.bulk_create(
        [
            LedgerUnit(
                run_id=run.pk,
                engine="duplicate",
                kind="shape",
                cvat_task_id=9,
                frame_number=0,
                outcome="completed",
            ),
            LedgerUnit(
                run_id=run.pk,
                engine="duplicate",
                kind="shape",
                cvat_task_id=9,
                frame_number=1,
                outcome="not_checked",
                not_checked_reason="not_applicable",
            ),
        ]
    )

    configs = client.get("/api/config-versions/?status=published")
    assert configs.status_code == 200
    assert [item["id"] for item in configs.data["results"]] == [config.pk]
    assert client.get("/api/config-versions/?status=invalid").status_code == 400

    ledger = client.get(f"/api/runs/{run.pk}/ledger/")
    assert ledger.status_code == 200
    entry = next(row for row in ledger.data if row["engine"] == "duplicate")
    assert entry["engine"] == "duplicate"
    assert (entry["total"], entry["eligible"], entry["excluded"]) == (2, 1, 1)
    assert entry["not_checked_reasons"] == {"not_applicable": 1}
    assert entry["applicability_version"] == "2026.10"
    assert entry["coverage"] == 1.0
    disabled = next(row for row in ledger.data if row["engine"] == "geometry")
    assert disabled["status"] == "not_checked"
    assert disabled["coverage"] is None
    assert run.engine_results.get(engine="geometry").reason == "disabled"

    shards = client.get(f"/api/runs/{run.pk}/shards/")
    assert shards.status_code == 200
    assert shards.data["results"][0]["status"] == "pending"
    assert shards.data["results"][0]["engine"] == "duplicate"
    assert other.get(f"/api/runs/{run.pk}/ledger/").status_code == 403
    assert other.get(f"/api/runs/{run.pk}/shards/").status_code == 403
    assert other.get("/api/runs/99999/shards/").status_code == 404
    global_user = User.objects.create_user(username="execution-global-qc")
    RoleAssignment.objects.create(user=global_user, role=Role.QC_ADMIN, dataset_id=None)
    global_admin = APIClient()
    global_admin.force_authenticate(global_user)
    assert global_admin.get("/api/runs/?dataset=42").status_code == 200
    assert global_admin.get(f"/api/runs/{run.pk}/ledger/").status_code == 200
    assert QCRun.objects.filter(pk=run.pk).exists()


def test_config_create_publish_is_idempotent_and_restricted() -> None:
    admin = _actor(Role.QC_ADMIN, 42)
    qa_lead = _actor(Role.QA_LEAD, 42)
    body = {
        "name": "Road Vision",
        "engines": {"duplicate": {"enabled": True}, "geometry": {"enabled": False}},
        "thresholds": {"iou": 0.7},
        "models": {},
    }
    assert (
        qa_lead.post(
            "/api/config-versions/", body, format="json", HTTP_IDEMPOTENCY_KEY="cfg-1"
        ).status_code
        == 403
    )
    disabled_only = admin.post(
        "/api/config-versions/",
        {**body, "engines": {"geometry": {"enabled": False}}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="cfg-disabled",
    )
    assert disabled_only.status_code == 400
    created = admin.post("/api/config-versions/", body, format="json", HTTP_IDEMPOTENCY_KEY="cfg-1")
    assert created.status_code == 201
    assert created.data["status"] == "draft"
    config_id = created.data["id"]
    replay = admin.post("/api/config-versions/", body, format="json", HTTP_IDEMPOTENCY_KEY="cfg-1")
    assert replay.status_code == 201
    assert replay.data["id"] == config_id
    collision = admin.post(
        "/api/config-versions/",
        {**body, "name": "Different"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="cfg-1",
    )
    assert collision.status_code == 409
    assert qa_lead.post(f"/api/config-versions/{config_id}/publish/").status_code == 403
    published = admin.post(f"/api/config-versions/{config_id}/publish/")
    assert published.status_code == 200
    assert published.data["status"] == "published"
    assert admin.post(f"/api/config-versions/{config_id}/publish/").status_code == 409
