from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from snapshots.models import Snapshot
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot

pytestmark = pytest.mark.django_db(transaction=True)


def _user(username: str, role: Role, dataset_id: int | None):
    user = get_user_model().objects.create_user(username=username, password="safe-password")
    RoleAssignment.objects.create(user=user, role=role, dataset_id=dataset_id)
    return user


def _snapshot(user, dataset_id: int = 42) -> Snapshot:
    return create_locked_snapshot(
        dataset_id=dataset_id,
        created_by=user,
        taxonomy_version="taxonomy-v1",
        guideline_version="guideline-v1",
        jobs=[
            JobExport(
                cvat_job_id=17,
                cvat_task_id=9,
                source_updated_at="2026-10-09T07:05:45Z",
                annotations={"shapes": [], "tracks": []},
                frames=[
                    FrameExport(
                        frame_index=0,
                        file_name="000000.jpg",
                        width=1280,
                        height=720,
                        media_bytes=b"frame",
                        media_storage_key="sha256/00/frame",
                    )
                ],
            )
        ],
    )


@override_settings(CVAT_BASE_URL="http://cvat.example.test")
def test_detail_checks_server_side_dataset_scope_and_returns_deep_links() -> None:
    creator = _user("creator", Role.QA_LEAD, 42)
    snapshot = _snapshot(creator)
    client = APIClient()
    client.force_authenticate(creator)

    response = client.get(f"/api/snapshots/{snapshot.pk}/")

    assert response.status_code == 200
    assert response.data["revision_hash"] == snapshot.revision_sha256
    job = response.data["jobs"][0]
    assert job["cvat_url"] == "http://cvat.example.test/tasks/9/jobs/17"
    assert job["frames"][0]["cvat_url"].endswith("/tasks/9/jobs/17?frame=0")

    outsider = _user("outsider", Role.QA_LEAD, 99)
    client.force_authenticate(outsider)
    denied = client.get(f"/api/snapshots/{snapshot.pk}/")
    assert denied.status_code == 403
    assert denied.data["code"] == "OUT_OF_SCOPE"


def test_list_requires_dataset_scope() -> None:
    owner = _user("owner", Role.QA_LEAD, 42)
    _snapshot(owner)
    client = APIClient()
    client.force_authenticate(owner)

    response = client.get("/api/snapshots/?dataset_id=42")
    assert response.status_code == 200
    assert len(response.data["results"]) == 1

    denied = client.get("/api/snapshots/?dataset_id=99")
    assert denied.status_code == 403
    assert denied.data["code"] == "OUT_OF_SCOPE"


def test_post_requires_idempotency_key() -> None:
    owner = _user("post-owner", Role.QA_LEAD, 42)
    client = APIClient()
    client.force_authenticate(owner)

    response = client.post(
        "/api/snapshots/",
        {"dataset_id": 42, "scope": {"cvat_job_ids": [17]}},
        format="json",
    )
    assert response.status_code == 400
    assert response.data["code"] == "VALIDATION_ERROR"


def test_two_equal_exports_keep_same_hash_through_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _user("api-export-owner", Role.QA_LEAD, 42)
    client = APIClient()
    client.force_authenticate(owner)

    def fake_export(**kwargs):
        return _snapshot(kwargs["created_by"], kwargs["dataset_id"])

    monkeypatch.setattr("snapshots.views.create_snapshot_from_cvat", fake_export)
    ids = []
    for key in ("api-export-1", "api-export-2"):
        response = client.post(
            "/api/snapshots/",
            {"dataset_id": 42, "scope": {"cvat_job_ids": [17]}},
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        assert response.status_code == 202
        ids.append(response.data["id"])

    first = client.get(f"/api/snapshots/{ids[0]}/")
    second = client.get(f"/api/snapshots/{ids[1]}/")
    assert first.data["revision_hash"] == second.data["revision_hash"]


def test_qc_admin_can_read_but_cannot_create() -> None:
    admin = _user("qc-admin", Role.QC_ADMIN, None)
    snapshot = _snapshot(admin)
    client = APIClient()
    client.force_authenticate(admin)

    assert client.get(f"/api/snapshots/{snapshot.pk}/").status_code == 200
    response = client.post(
        "/api/snapshots/",
        {"dataset_id": 42, "scope": {"cvat_job_ids": [17]}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="qc-admin-create",
    )
    assert response.status_code == 403
    assert response.data["code"] == "FORBIDDEN"
