from __future__ import annotations

from collections.abc import Mapping

import pytest
from django.contrib.auth import get_user_model

from snapshots.models import Snapshot
from snapshots.orchestration import (
    SnapshotRequestConflict,
    SnapshotScope,
    create_snapshot_from_cvat,
)
from storage.client import Blob

pytestmark = pytest.mark.django_db(transaction=True)


ANNOTATIONS = {
    "shapes": [
        {
            "id": 1,
            "type": "rectangle",
            "frame": 0,
            "label_id": 2,
            "points": [10, 20, 110, 120],
        }
    ],
    "tracks": [],
}


class FakeStorage:
    def put(
        self,
        content: bytes,
        *,
        extension: str | None = None,
        content_type: str = "application/octet-stream",
    ) -> Blob:
        return Blob("snapshots", "sha256/ab/content", "a" * 64, len(content), True)


class FakeCvatClient:
    def __init__(self, *, drift: bool = False) -> None:
        self.drift = drift
        self.annotation_reads = 0
        self.job = {
            "id": 17,
            "task_id": 9,
            "start_frame": 0,
            "updated_date": "2026-10-09T07:05:45Z",
            "assignee": None,
        }

    def get_project(self, project_id: int) -> dict[str, object]:
        return {"id": project_id}

    def get_task(self, task_id: int) -> dict[str, object]:
        return {"id": task_id, "project_id": 42}

    def list_tasks(self, *, project_id: int) -> list[dict[str, object]]:
        return [{"id": 9, "project_id": project_id}]

    def list_jobs(self, *, task_id: int) -> list[dict[str, object]]:
        assert task_id == 9
        return [dict(self.job)]

    def list_labels(self, *, project_id: int) -> list[dict[str, object]]:
        return [{"id": 2, "name": "car", "project_id": project_id}]

    def get_job(self, job_id: int) -> dict[str, object]:
        assert job_id == 17
        return dict(self.job)

    def get_job_annotations(self, job_id: int) -> dict[str, object]:
        assert job_id == 17
        self.annotation_reads += 1
        payload: dict[str, object] = {
            "shapes": [dict(shape) for shape in ANNOTATIONS["shapes"]],
            "tracks": [],
        }
        if self.drift and self.annotation_reads == 2:
            shapes = payload["shapes"]
            assert isinstance(shapes, list)
            shape = shapes[0]
            assert isinstance(shape, dict)
            shape["points"] = [10, 20, 130, 120]
        return payload

    def get_job_data_meta(self, job_id: int) -> dict[str, object]:
        return {
            "start_frame": 0,
            "frame_filter": "step=1",
            "frames": [{"name": "000000.jpg", "width": 1280, "height": 720}],
        }

    def get_job_frame(self, job_id: int, frame_index: int) -> tuple[bytes, str]:
        assert (job_id, frame_index) == (17, 0)
        return b"same-frame", "image/jpeg"


def _actor(username: str):
    return get_user_model().objects.create_user(username=username, password="safe-password")


def _create(*, key: str, username: str, client: FakeCvatClient) -> Snapshot:
    return create_snapshot_from_cvat(
        dataset_id=42,
        scope=SnapshotScope(cvat_job_ids=(17,)),
        note="pilot",
        created_by=_actor(username),
        idempotency_key=key,
        client=client,  # type: ignore[arg-type]
        storage=FakeStorage(),
    )


def test_two_unchanged_exports_have_the_same_hash_through_orchestration() -> None:
    first = _create(key="first", username="first", client=FakeCvatClient())
    second = _create(key="second", username="second", client=FakeCvatClient())

    assert first.status == second.status == Snapshot.Status.LOCKED
    assert first.revision_sha256 == second.revision_sha256
    assert first.jobs.get().sha256 == second.jobs.get().sha256
    assert second.parent_snapshot == first


def test_mid_export_drift_returns_job_ids_and_never_locks() -> None:
    snapshot = _create(key="drift", username="drift", client=FakeCvatClient(drift=True))

    assert snapshot.status == Snapshot.Status.FAILED
    assert snapshot.failure_reason == "drift_detected"
    assert snapshot.drift_jobs == [17]
    assert snapshot.revision_sha256 == ""
    assert snapshot.jobs.count() == 0
    assert not Snapshot.objects.filter(status=Snapshot.Status.LOCKED).exists()


def test_idempotency_replays_exact_request_and_rejects_changed_body() -> None:
    actor = _actor("idempotent")
    kwargs = {
        "dataset_id": 42,
        "scope": SnapshotScope(cvat_job_ids=(17,)),
        "note": "pilot",
        "created_by": actor,
        "idempotency_key": "same-key",
        "client": FakeCvatClient(),
        "storage": FakeStorage(),
    }
    first = create_snapshot_from_cvat(**kwargs)  # type: ignore[arg-type]
    replay = create_snapshot_from_cvat(**kwargs)  # type: ignore[arg-type]
    assert replay.pk == first.pk

    kwargs["note"] = "changed"
    with pytest.raises(SnapshotRequestConflict):
        create_snapshot_from_cvat(**kwargs)  # type: ignore[arg-type]


def test_task_outside_dataset_is_rejected() -> None:
    client = FakeCvatClient()

    def other_project(_task_id: int) -> Mapping[str, object]:
        return {"id": 9, "project_id": 99}

    client.get_task = other_project  # type: ignore[method-assign,assignment]
    with pytest.raises(ValueError, match="outside dataset"):
        _create(key="outside", username="outside", client=client)
