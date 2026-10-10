"""DEMO-ONLY contract tests for M-DEMO01 D-03."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from orchestration.models import CandidateRecord, ShardCommit
from runs.models import ConfigVersion, EngineResult, QCRun
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def demo_run() -> QCRun:
    creator = User.objects.create_user(username="demo-run-creator")
    snapshot = create_locked_snapshot(
        dataset_id=42,
        created_by=creator,
        taxonomy_version="bdd100k-10-v1",
        guideline_version="bdd100k-demo-v1",
        jobs=[
            JobExport(
                cvat_job_id=20,
                cvat_task_id=23,
                source_updated_at="2026-10-10T00:00:00Z",
                annotations={
                    "shapes": [
                        {
                            "id": 11,
                            "type": "rectangle",
                            "frame": 0,
                            "label_id": 1,
                            "points": [100, 200, 400, 420],
                        },
                        {
                            "id": 12,
                            "type": "rectangle",
                            "frame": 0,
                            "label_id": 1,
                            "points": [110, 205, 405, 425],
                        },
                        {
                            "id": 13,
                            "type": "rectangle",
                            "frame": 1,
                            "label_id": 2,
                            "points": [1270, 10, 1300, 60],
                        },
                    ],
                    "tracks": [],
                },
                frames=[
                    FrameExport(
                        frame_index=index,
                        file_name=f"{index + 1:04d}.jpg",
                        width=1280,
                        height=720,
                        media_bytes=f"demo-frame-{index}".encode(),
                        media_storage_key=f"demo/frames/{index}.jpg",
                    )
                    for index in range(3)
                ],
            )
        ],
    )
    config = ConfigVersion.objects.create(
        name="M-DEMO01",
        status=ConfigVersion.Status.PUBLISHED,
        created_by=creator,
    )
    run = QCRun.objects.create(
        snapshot=snapshot,
        config_version=config,
        seed=42,
        status=QCRun.Status.COMPLETED,
        dataset_id=42,
        scope_hash="demo-scope",
        created_by=creator,
    )
    EngineResult.objects.bulk_create(
        [
            EngineResult(run=run, engine="duplicate_overlap", status="completed"),
            EngineResult(run=run, engine="geometry", status="failed"),
            EngineResult(run=run, engine="schema_taxonomy", status="not_checked"),
        ]
    )
    shard = ShardCommit.objects.create(
        idempotency_key="demo-shard",
        run=run,
        snapshot_id=snapshot.pk,
        engine="duplicate_overlap",
        engine_version="demo-v1",
        shard_index=0,
        output_sha256="a" * 64,
    )
    CandidateRecord.objects.create(
        run=run,
        dedup_key="b" * 64,
        shard=shard,
        engine="duplicate_overlap",
        engine_version="demo-v1",
        family="E3",
        cvat_task_id=23,
        frame_number=0,
        anchor={"rule_id": "DUP-01", "objects": [{"id": 11}, {"id": 12}]},
        policy_version="demo-v1",
        evidence={"iou": 0.93, "severity": "high"},
        evidence_sha256="c" * 64,
    )
    CandidateRecord.objects.create(
        run=run,
        dedup_key="d" * 64,
        shard=shard,
        engine="geometry",
        engine_version="demo-v1",
        family="structural",
        cvat_task_id=23,
        frame_number=1,
        anchor={"rule_id": "GEO-01", "objects": [{"id": 13}]},
        policy_version="demo-v1",
        evidence={"overflow_px": 20, "message": "Box vuot ngoai anh"},
        evidence_sha256="e" * 64,
    )
    return run


def _client(role: Role, dataset_id: int | None = 42) -> APIClient:
    user = User.objects.create_user(username=f"demo-{role}-{dataset_id}")
    RoleAssignment.objects.create(user=user, role=role, dataset_id=dataset_id)
    client = APIClient()
    client.force_authenticate(user)
    return client


@override_settings(CVAT_BASE_URL="http://localhost:8080")
def test_ranked_frames_match_demo_contract_and_are_stable(demo_run: QCRun) -> None:
    client = _client(Role.REVIEWER)
    url = f"/api/runs/{demo_run.pk}/frames/"

    first = client.get(url)
    second = client.get(url)

    assert first.status_code == second.status_code == 200
    assert first.data == second.data
    assert first.data["run_id"] == demo_run.pk
    assert first.data["snapshot_id"] == demo_run.snapshot_id
    assert first.data["score_version"] == "score_v0"
    assert [item["rank"] for item in first.data["items"]] == [1, 2, 3]
    assert first.data["items"][0]["score"] == 0.52
    assert first.data["items"][1]["score"] == 0.01
    assert first.data["items"][1]["candidates"][0]["family"] == "structural"
    assert "media_storage_key" not in str(first.data)
    assert first.data["items"][0]["cvat"] == {
        "task_id": 23,
        "job_id": 20,
        "frame": 0,
        "deep_link": "http://localhost:8080/tasks/23/jobs/20?frame=0",
    }
    assert first.data["engines"] == [
        {"engine": "duplicate_overlap", "status": "checked"},
        {"engine": "geometry", "status": "failed"},
        {"engine": "schema_taxonomy", "status": "not_checked"},
    ]


def test_cursor_paginates_ranked_result_without_duplicates(demo_run: QCRun) -> None:
    client = _client(Role.QA_LEAD)
    url = f"/api/runs/{demo_run.pk}/frames/?page_size=1"

    page_one = client.get(url)
    page_two = client.get(
        f"/api/runs/{demo_run.pk}/frames/?page_size=1&cursor={page_one.data['next']}"
    )

    assert page_one.status_code == page_two.status_code == 200
    assert page_one.data["items"][0]["rank"] == 1
    assert page_two.data["items"][0]["rank"] == 2
    assert page_one.data["items"][0]["frame_id"] != page_two.data["items"][0]["frame_id"]


@pytest.mark.parametrize("query", ["page_size=0", "page_size=abc", "cursor=not-base64!"])
def test_invalid_pagination_is_rejected(demo_run: QCRun, query: str) -> None:
    response = _client(Role.REVIEWER).get(f"/api/runs/{demo_run.pk}/frames/?{query}")
    assert response.status_code == 400
    assert response.data["code"] == "VALIDATION_ERROR"


def test_demo_frames_are_role_and_dataset_scoped(demo_run: QCRun) -> None:
    url = f"/api/runs/{demo_run.pk}/frames/"

    unauthenticated = APIClient().get(url)
    annotator = _client(Role.ANNOTATOR).get(url)
    outsider = _client(Role.REVIEWER, 99).get(url)
    super_admin = _client(Role.SUPER_ADMIN, None).get(url)

    assert (unauthenticated.status_code, unauthenticated.data["code"]) == (
        403,
        "NOT_AUTHENTICATED",
    )
    assert (annotator.status_code, annotator.data["code"]) == (403, "FORBIDDEN")
    assert (outsider.status_code, outsider.data["code"]) == (403, "OUT_OF_SCOPE")
    assert super_admin.status_code == 200


def test_image_endpoint_proxies_bytes_and_hides_storage_key(demo_run: QCRun) -> None:
    client = _client(Role.REVIEWER)
    frame = demo_run.snapshot.jobs.get().frames.get(frame_index=0)
    storage = Mock()
    storage.get.return_value = b"jpeg-bytes"

    with patch("runs.views.ObjectStorage.from_django_settings", return_value=storage) as factory:
        response = client.get(f"/api/runs/{demo_run.pk}/frames/{frame.pk}/image/")

    assert response.status_code == 200
    assert response.content == b"jpeg-bytes"
    assert response["Content-Type"] == "image/jpeg"
    factory.assert_called_once_with("snapshots")
    storage.get.assert_called_once_with("demo/frames/0.jpg")
    assert client.get(f"/api/runs/{demo_run.pk}/frames/999999/image/").status_code == 404
