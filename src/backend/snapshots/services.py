"""Transaction-bound service for building and locking immutable snapshots."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import cast

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from snapshots.models import LockedSnapshotError, Snapshot, SnapshotFrame, SnapshotJob
from snapshots.normalization import (
    SCHEMA_VERSION,
    JobExport,
    NormalizedJob,
    normalize_job,
    normalize_snapshot,
)


def ensure_snapshot_mutable(snapshot: Snapshot) -> None:
    """Fail closed using current database state, not a possibly stale instance."""

    status = Snapshot.objects.values_list("status", flat=True).get(pk=snapshot.pk)
    if status == Snapshot.Status.LOCKED:
        raise LockedSnapshotError("Locked snapshots cannot be mutated by snapshot services.")


def _parent_for_update(parent: Snapshot | None, dataset_id: int) -> Snapshot | None:
    if parent is None:
        return None
    stored = Snapshot.objects.select_for_update().get(pk=parent.pk)
    if stored.status != Snapshot.Status.LOCKED:
        raise ValueError("parent_snapshot must already be locked")
    if stored.dataset_id != dataset_id:
        raise ValueError("parent_snapshot must belong to the same dataset")
    return stored


def _persist_job(snapshot: Snapshot, export: JobExport, normalized: NormalizedJob) -> None:
    job = SnapshotJob.objects.create(
        snapshot=snapshot,
        cvat_job_id=export.cvat_job_id,
        cvat_task_id=export.cvat_task_id,
        assignee_cvat_user_id=export.assignee_cvat_user_id,
        assignee_user_id=export.assignee_user_id,
        source_updated_at=export.source_updated_at,
        sha256=normalized.sha256,
        normalized_json=normalized.payload,
        rectangle_count=normalized.rectangle_count,
        skipped_shape_counts=normalized.skipped_shape_counts,
    )
    frames = normalized.payload["frames"]
    if not isinstance(frames, list):  # pragma: no cover - normalization owns this shape
        raise TypeError("normalized frames must be a list")
    for raw_frame in frames:
        frame = cast(dict[str, object], raw_frame)
        media = cast(dict[str, object], frame["media"])
        shapes = cast(list[dict[str, object]], frame["shapes"])
        SnapshotFrame.objects.create(
            snapshot_job=job,
            frame_index=int(cast(int, frame["frame_index"])),
            source_frame_id=cast(int | None, frame["source_frame_id"]),
            file_name=str(frame["file_name"]),
            width=int(cast(int, frame["width"])),
            height=int(cast(int, frame["height"])),
            media_storage_key=str(media["storage_key"]),
            media_sha256=str(media["sha256"]),
            media_size_bytes=int(cast(int, media["size_bytes"])),
            media_mime_type=str(media["mime_type"]),
            shapes=shapes,
            rectangle_count=len(shapes),
        )


@transaction.atomic
def create_locked_snapshot(
    *,
    dataset_id: int,
    created_by: User,
    jobs: Sequence[JobExport],
    taxonomy_version: str,
    guideline_version: str,
    parent_snapshot: Snapshot | None = None,
    provenance: Mapping[str, object] | None = None,
) -> Snapshot:
    """Normalize, persist, and lock one complete snapshot atomically.

    No partial snapshot becomes visible: invalid input or any persistence error
    rolls back the aggregate. Drift checks deliberately belong to T-021 and can
    call this service only after their second source read succeeds.
    """

    parent = _parent_for_update(parent_snapshot, dataset_id)
    normalized_jobs = [normalize_job(job) for job in jobs]
    normalized_payload, revision_sha256 = normalize_snapshot(
        dataset_id=dataset_id,
        jobs=normalized_jobs,
        taxonomy_version=taxonomy_version,
        guideline_version=guideline_version,
    )
    snapshot = Snapshot.objects.create(
        dataset_id=dataset_id,
        status=Snapshot.Status.EXPORTING,
        parent_snapshot=parent,
        taxonomy_version=taxonomy_version,
        guideline_version=guideline_version,
        schema_version=SCHEMA_VERSION,
        normalized_json={},
        provenance=dict(provenance or {}),
        skipped_shape_counts={},
        created_by=created_by,
    )
    skipped: Counter[str] = Counter()
    for export, normalized in sorted(
        zip(jobs, normalized_jobs, strict=True),
        key=lambda pair: pair[0].cvat_job_id,
    ):
        _persist_job(snapshot, export, normalized)
        skipped.update(normalized.skipped_shape_counts)

    snapshot.normalized_json = normalized_payload
    snapshot.revision_sha256 = revision_sha256
    snapshot.skipped_shape_counts = dict(sorted(skipped.items()))
    snapshot.status = Snapshot.Status.LOCKED
    snapshot.locked_at = timezone.now()
    snapshot.save(
        update_fields=[
            "normalized_json",
            "revision_sha256",
            "skipped_shape_counts",
            "status",
            "locked_at",
        ]
    )
    return snapshot


@transaction.atomic
def mark_snapshot_failed(snapshot: Snapshot, *, reason: str) -> Snapshot:
    """Example lifecycle mutation used by the future export/drift orchestration."""

    ensure_snapshot_mutable(snapshot)
    if not reason.strip():
        raise ValueError("failure reason must not be empty")
    snapshot.status = Snapshot.Status.FAILED
    snapshot.failure_reason = reason.strip()
    snapshot.save(update_fields=["status", "failure_reason"])
    return snapshot
