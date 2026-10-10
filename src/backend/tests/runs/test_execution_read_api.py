"""Read APIs used by AnalysisConfig and ExecutionHistory."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from orchestration.models import CandidateRecord, LedgerUnit, ShardCommit
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


def test_run_candidates_list_permissions_pagination_and_null_raw_count() -> None:
    user = User.objects.create_user(username="cand-owner")
    qa_lead = _actor(Role.QA_LEAD, 42)
    reviewer = _actor(Role.REVIEWER, 42)
    annotator = _actor(Role.ANNOTATOR, 42)
    other_lead = _actor(Role.QA_LEAD, 99)

    snapshot = create_locked_snapshot(
        dataset_id=42,
        created_by=user,
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
                        frame_index=index,
                        file_name=f"{index}.jpg",
                        width=640,
                        height=480,
                        media_bytes=f"frame-{index}".encode(),
                        media_storage_key=f"frames/{index}",
                    )
                    for index in range(3)
                ],
            )
        ],
    )
    config = ConfigVersion.objects.create(
        name="Candidate Config",
        status=ConfigVersion.Status.PUBLISHED,
        created_by=user,
        engines={"duplicate": {"enabled": True}, "detector": {"enabled": True}},
    )
    run, _ = create_qc_run(
        snapshot_id=snapshot.pk,
        config_version_id=config.pk,
        seed=11,
        created_by=user,
        idempotency_key="candidates-read-test",
    )

    shard = ShardCommit.objects.create(
        idempotency_key="shard-cand-1",
        run=run,
        snapshot_id=snapshot.pk,
        engine="duplicate",
        engine_version="1.0.0",
        shard_index=0,
        output_sha256="deadbeef",
        attempts=1,
    )

    CandidateRecord.objects.bulk_create(
        [
            CandidateRecord(
                run=run,
                dedup_key="cand-1",
                shard=shard,
                engine="duplicate",
                engine_version="1.0.0",
                family="E3",
                cvat_task_id=9,
                frame_number=0,
                anchor={
                    "kind": "annotation",
                    "objects": [{"namespace": "cvat_shape", "id": "1"}],
                    "policy_version": "v1",
                },
                policy_version="v1",
                evidence={"engine": "duplicate", "iou": 0.95, "rule_id": "R-01"},
                evidence_sha256="sha-cand-1",
            ),
            CandidateRecord(
                run=run,
                dedup_key="cand-2",
                shard=shard,
                engine="duplicate",
                engine_version="1.0.0",
                family="E3",
                cvat_task_id=9,
                frame_number=1,
                anchor={
                    "kind": "annotation",
                    "objects": [{"namespace": "cvat_shape", "id": "2"}],
                    "policy_version": "v1",
                },
                policy_version="v1",
                evidence={"engine": "duplicate", "iou": 0.88, "rule_id": "R-01"},
                evidence_sha256="sha-cand-2",
            ),
            CandidateRecord(
                run=run,
                dedup_key="cand-3",
                shard=shard,
                engine="detector",
                engine_version="2.0.0",
                family="E2",
                cvat_task_id=9,
                frame_number=2,
                anchor={
                    "kind": "prediction_region",
                    "objects": [{"namespace": "detector", "id": "d-1"}],
                    "policy_version": "v1",
                },
                policy_version="v1",
                evidence={
                    "engine": "detector",
                    "prediction_class": "truck",
                    "prediction_bbox": {"x1": 10, "y1": 20, "x2": 30, "y2": 40},
                    "confidence": 0.85,
                },
                evidence_sha256="sha-cand-3",
            ),
        ]
    )

    # 1. Run không tồn tại -> 404 NOT_FOUND
    assert qa_lead.get("/api/runs/999999/candidates/").status_code == 404

    # 2. Dataset ngoài phạm vi -> 403 FORBIDDEN
    assert other_lead.get(f"/api/runs/{run.pk}/candidates/").status_code == 403

    # 3. Role không có quyền (Annotator) -> 403 FORBIDDEN
    assert annotator.get(f"/api/runs/{run.pk}/candidates/").status_code == 403

    # 4. Role hợp lệ (Reviewer) -> 200 OK
    assert reviewer.get(f"/api/runs/{run.pk}/candidates/").status_code == 200

    # 5. QA Lead lấy danh sách đầy đủ, kiểm tra schema, dedup_count và raw_count là null
    resp = qa_lead.get(f"/api/runs/{run.pk}/candidates/")
    assert resp.status_code == 200
    assert resp.data["raw_count"] is None
    assert resp.data["dedup_count"] == 3
    assert len(resp.data["results"]) == 3

    # Kiểm tra chi tiết candidate và evidence detector
    det_cand = next(c for c in resp.data["results"] if c["engine"] == "detector")
    assert det_cand["engine_version"] == "2.0.0"
    assert det_cand["family"] == "E2"
    assert det_cand["frame"] == {"cvat_task_id": 9, "frame_number": 2}
    assert det_cand["evidence"]["prediction_class"] == "truck"
    assert det_cand["evidence"]["engine"] == "detector"
    assert det_cand["evidence"]["prediction_bbox"] == {"x1": 10, "y1": 20, "x2": 30, "y2": 40}
    assert det_cand["severity"] is None
    assert qa_lead.get(f"/api/runs/{run.pk}/candidates/?dataset_id=99").status_code == 400
    assert other_lead.get(f"/api/runs/{run.pk}/candidates/?dataset=99").status_code == 403
    family_filtered = qa_lead.get(f"/api/runs/{run.pk}/candidates/?family=E2")
    assert len(family_filtered.data["results"]) == 1
    assert family_filtered.data["dedup_count"] == 3

    # 6. Filter theo engine
    resp_filtered = qa_lead.get(f"/api/runs/{run.pk}/candidates/?engine=duplicate")
    assert resp_filtered.status_code == 200
    assert len(resp_filtered.data["results"]) == 2
    assert resp_filtered.data["dedup_count"] == 3
    assert resp_filtered.data["raw_count"] is None

    # 7. Phân trang (page_size = 2)
    resp_page1 = qa_lead.get(f"/api/runs/{run.pk}/candidates/?page_size=2")
    assert resp_page1.status_code == 200
    assert len(resp_page1.data["results"]) == 2
    assert resp_page1.data["next"] is not None
    assert resp_page1.data["raw_count"] is None
    assert resp_page1.data["dedup_count"] == 3

    next_url = resp_page1.data["next"]
    resp_page2 = qa_lead.get(next_url)
    assert resp_page2.status_code == 200
    assert len(resp_page2.data["results"]) == 1
    assert resp_page2.data["results"][0]["engine"] == "detector"
    assert resp_page2.data["dedup_count"] == 3
    assert resp_page2.data["raw_count"] is None
