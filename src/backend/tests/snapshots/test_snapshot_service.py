from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.db import DatabaseError, transaction

from snapshots.models import LockedSnapshotError, Snapshot, SnapshotFrame, SnapshotJob
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot, mark_snapshot_failed

pytestmark = pytest.mark.django_db(transaction=True)


def actor(username: str):
    return get_user_model().objects.create_user(username=username, password="safe-test-password")


def export(*, job_id: int = 17, task_id: int = 9) -> JobExport:
    return JobExport(
        cvat_job_id=job_id,
        cvat_task_id=task_id,
        source_updated_at="2026-10-09T07:05:45Z",
        annotations={
            "shapes": [
                {
                    "id": 12,
                    "type": "rectangle",
                    "frame": 0,
                    "label_id": 4,
                    "points": [10, 20, 110, 120],
                },
                {"id": 13, "type": "polygon", "frame": 0, "label_id": 4},
            ],
            "tracks": [],
        },
        frames=(
            FrameExport(
                frame_index=0,
                source_frame_id=1000,
                file_name="000000.jpg",
                width=1280,
                height=720,
                media_bytes=b"frame-0",
                media_storage_key="snapshots/source/000000.jpg",
            ),
        ),
        assignee_cvat_user_id=501,
    )


def create_snapshot(*, username: str, parent: Snapshot | None = None) -> Snapshot:
    return create_locked_snapshot(
        dataset_id=42,
        created_by=actor(username),
        jobs=[export()],
        taxonomy_version="bdd100k-10-v1",
        guideline_version="bdd100k-guideline-v1",
        parent_snapshot=parent,
        provenance={"source": "CVAT", "cvat_project_id": 3},
    )


def test_service_persists_provenance_frames_checksums_and_skip_counts() -> None:
    snapshot = create_snapshot(username="creator")

    assert snapshot.status == Snapshot.Status.LOCKED
    assert snapshot.locked_at is not None
    assert len(snapshot.revision_sha256) == 64
    assert snapshot.provenance == {"source": "CVAT", "cvat_project_id": 3}
    assert snapshot.skipped_shape_counts == {"polygon": 1}
    job = snapshot.jobs.get()
    assert job.cvat_job_id == 17
    assert job.cvat_task_id == 9
    assert job.assignee_cvat_user_id == 501
    assert job.rectangle_count == 1
    assert len(job.sha256) == 64
    frame = job.frames.get()
    assert frame.source_frame_id == 1000
    assert frame.media_storage_key == "snapshots/source/000000.jpg"
    assert frame.media_sha256 == "f8952f8aff2a83a859aa47f33adb73441412143c3982ae0e7ec57d49d0ba7320"
    assert frame.rectangle_count == 1


def test_unchanged_child_snapshot_has_same_hash_and_correct_parent_lineage() -> None:
    parent = create_snapshot(username="parent-creator")
    child = create_snapshot(username="child-creator", parent=parent)

    assert child.parent_snapshot == parent
    assert child.revision_sha256 == parent.revision_sha256
    assert child.jobs.get().sha256 == parent.jobs.get().sha256


def test_parent_must_be_locked_and_belong_to_same_dataset() -> None:
    parent = Snapshot.objects.create(
        dataset_id=42,
        status=Snapshot.Status.PENDING,
        taxonomy_version="bdd100k-10-v1",
        guideline_version="bdd100k-guideline-v1",
        schema_version="labelx.snapshot.v1",
        created_by=actor("draft-parent"),
    )
    with pytest.raises(ValueError, match="already be locked"):
        create_locked_snapshot(
            dataset_id=42,
            created_by=actor("child-of-draft"),
            jobs=[export()],
            taxonomy_version="bdd100k-10-v1",
            guideline_version="bdd100k-guideline-v1",
            parent_snapshot=parent,
        )

    locked = create_snapshot(username="other-dataset-parent")
    with pytest.raises(ValueError, match="same dataset"):
        create_locked_snapshot(
            dataset_id=43,
            created_by=actor("wrong-dataset-child"),
            jobs=[export()],
            taxonomy_version="bdd100k-10-v1",
            guideline_version="bdd100k-guideline-v1",
            parent_snapshot=locked,
        )


def test_locked_snapshot_rejects_model_and_service_mutation() -> None:
    snapshot = create_snapshot(username="locked-model")
    job = snapshot.jobs.get()
    frame = job.frames.get()

    snapshot.provenance = {"tampered": True}
    with pytest.raises(LockedSnapshotError, match="cannot be updated"):
        snapshot.save()
    with pytest.raises(LockedSnapshotError, match="cannot be deleted"):
        snapshot.delete()
    with pytest.raises(LockedSnapshotError, match="snapshot services"):
        mark_snapshot_failed(snapshot, reason="tamper")
    job.rectangle_count = 99
    with pytest.raises(LockedSnapshotError, match="cannot be mutated"):
        job.save()
    frame.file_name = "tampered.jpg"
    with pytest.raises(LockedSnapshotError, match="cannot be mutated"):
        frame.save()


def test_locked_snapshot_rejects_queryset_mutation_at_database_layer() -> None:
    snapshot = create_snapshot(username="locked-database")
    job = snapshot.jobs.get()
    frame = job.frames.get()

    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        Snapshot.objects.filter(pk=snapshot.pk).update(provenance={"tampered": True})
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        SnapshotJob.objects.filter(pk=job.pk).update(rectangle_count=99)
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        SnapshotFrame.objects.filter(pk=frame.pk).delete()
    snapshot.refresh_from_db()
    job.refresh_from_db()
    assert snapshot.provenance == {"source": "CVAT", "cvat_project_id": 3}
    assert job.rectangle_count == 1
    assert SnapshotFrame.objects.filter(pk=frame.pk).exists()
