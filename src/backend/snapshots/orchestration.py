"""Read-only CVAT export orchestration with a fail-closed drift barrier."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from accounts.models import CvatIdentity
from cvat_adapter.client import CvatReadClient
from cvat_adapter.hashing import canonicalize_job_annotations
from guideline.models import get_latest_guideline_version
from snapshots.models import Snapshot
from snapshots.normalization import SCHEMA_VERSION, FrameExport, JobExport, sha256_json
from snapshots.services import create_locked_snapshot
from storage.client import Blob, ObjectStorage


class SnapshotRequestConflict(ValueError):
    """An idempotency key was already used for a different request."""


class SnapshotSourceError(ValueError):
    """CVAT returned incomplete data or data outside the requested dataset."""


class SnapshotStorage(Protocol):
    def put(
        self,
        content: bytes,
        *,
        extension: str | None = None,
        content_type: str = "application/octet-stream",
    ) -> Blob: ...


@dataclass(frozen=True, slots=True)
class SnapshotScope:
    cvat_task_ids: tuple[int, ...] = ()
    cvat_job_ids: tuple[int, ...] = ()

    def payload(self) -> dict[str, list[int]]:
        return {
            "cvat_task_ids": sorted(set(self.cvat_task_ids)),
            "cvat_job_ids": sorted(set(self.cvat_job_ids)),
        }


@dataclass(frozen=True, slots=True)
class SourceRevision:
    updated_date: str
    annotation_sha256: str


def _positive_int(value: object, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise SnapshotSourceError(f"{field} must be a positive integer")
    return value


def _job_task_id(job: Mapping[str, object]) -> int:
    value = job.get("task_id")
    if value is None and isinstance(job.get("task"), Mapping):
        value = cast(Mapping[str, object], job["task"]).get("id")
    return _positive_int(value, field="job.task_id")


def _project_id(task: Mapping[str, object]) -> int:
    value = task.get("project_id")
    if value is None and isinstance(task.get("project"), Mapping):
        value = cast(Mapping[str, object], task["project"]).get("id")
    return _positive_int(value, field="task.project_id")


def _assignee_id(job: Mapping[str, object]) -> int | None:
    assignee = job.get("assignee")
    if assignee is None:
        return None
    if isinstance(assignee, Mapping):
        assignee = assignee.get("id")
    return _positive_int(assignee, field="job.assignee.id")


def _source_revision(
    client: CvatReadClient,
    job_id: int,
    *,
    job: Mapping[str, object] | None = None,
    annotations: Mapping[str, object] | None = None,
) -> SourceRevision:
    current_job = job if job is not None else client.get_job(job_id)
    current_annotations = (
        annotations if annotations is not None else client.get_job_annotations(job_id)
    )
    updated_date = current_job.get("updated_date")
    if not isinstance(updated_date, str) or not updated_date.strip():
        raise SnapshotSourceError(f"CVAT job {job_id} has no updated_date")
    return SourceRevision(
        updated_date=updated_date,
        annotation_sha256=canonicalize_job_annotations(job_id, current_annotations).sha256,
    )


def _frame_step(meta: Mapping[str, object]) -> int:
    frame_filter = meta.get("frame_filter", "")
    if not isinstance(frame_filter, str):
        return 1
    match = re.search(r"(?:^|,)step=(\d+)(?:,|$)", frame_filter)
    return max(1, int(match.group(1))) if match else 1


def _frame_exports(
    client: CvatReadClient,
    storage: SnapshotStorage,
    *,
    job_id: int,
    job: Mapping[str, object],
) -> tuple[FrameExport, ...]:
    meta = client.get_job_data_meta(job_id)
    raw_frames = meta.get("frames")
    if not isinstance(raw_frames, Sequence) or isinstance(raw_frames, (str, bytes)):
        raise SnapshotSourceError(f"CVAT job {job_id} data meta has no frame list")
    start = job.get("start_frame", meta.get("start_frame", 0))
    if not isinstance(start, int) or isinstance(start, bool) or start < 0:
        raise SnapshotSourceError(f"CVAT job {job_id} has invalid start_frame")
    step = _frame_step(meta)
    exports: list[FrameExport] = []
    for offset, raw_frame in enumerate(raw_frames):
        if not isinstance(raw_frame, Mapping):
            raise SnapshotSourceError(f"CVAT job {job_id} has invalid frame metadata")
        frame_index = start + offset * step
        content, content_type = client.get_job_frame(job_id, frame_index)
        file_name = raw_frame.get("name")
        width, height = raw_frame.get("width"), raw_frame.get("height")
        if not isinstance(file_name, str) or not file_name.strip():
            raise SnapshotSourceError(f"CVAT job {job_id} frame {frame_index} has no name")
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            raise SnapshotSourceError(
                f"CVAT job {job_id} frame {frame_index} has invalid dimensions"
            )
        extension = file_name.rsplit(".", 1)[1] if "." in file_name else None
        blob = storage.put(content, extension=extension, content_type=content_type)
        exports.append(
            FrameExport(
                frame_index=frame_index,
                source_frame_id=frame_index,
                file_name=file_name,
                width=width,
                height=height,
                media_bytes=content,
                media_storage_key=blob.key,
                media_mime_type=content_type.split(";", 1)[0],
            )
        )
    if not exports:
        raise SnapshotSourceError(f"CVAT job {job_id} contains no frames")
    return tuple(exports)


def _selected_jobs(
    client: CvatReadClient, *, dataset_id: int, scope: SnapshotScope
) -> list[dict[str, object]]:
    client.get_project(dataset_id)
    jobs: dict[int, dict[str, object]] = {}
    task_cache: dict[int, dict[str, object]] = {}

    task_ids = list(scope.payload()["cvat_task_ids"])
    if not task_ids and not scope.cvat_job_ids:
        for task in client.list_tasks(project_id=dataset_id):
            task_id = _positive_int(task.get("id"), field="task.id")
            task_cache[task_id] = task
            task_ids.append(task_id)

    for task_id in task_ids:
        task = task_cache.get(task_id) or client.get_task(task_id)
        if _project_id(task) != dataset_id:
            raise SnapshotSourceError(f"CVAT task {task_id} is outside dataset {dataset_id}")
        for job in client.list_jobs(task_id=task_id):
            job_id = _positive_int(job.get("id"), field="job.id")
            jobs[job_id] = job

    for job_id in scope.payload()["cvat_job_ids"]:
        job = client.get_job(job_id)
        task_id = _job_task_id(job)
        task = task_cache.get(task_id) or client.get_task(task_id)
        task_cache[task_id] = task
        if _project_id(task) != dataset_id:
            raise SnapshotSourceError(f"CVAT job {job_id} is outside dataset {dataset_id}")
        jobs[job_id] = job

    if not jobs:
        raise SnapshotSourceError("snapshot scope contains no CVAT jobs")
    return [jobs[job_id] for job_id in sorted(jobs)]


def _taxonomy_version(client: CvatReadClient, dataset_id: int) -> str:
    labels = client.list_labels(project_id=dataset_id)
    labels.sort(key=lambda label: str(label.get("id", "")))
    return f"cvat-labels:{sha256_json(labels)}"


def _guideline_version() -> str:
    version = get_latest_guideline_version()
    return version.version_tag if version is not None else "unversioned"


def _failed_drift_snapshot(
    *,
    dataset_id: int,
    created_by: User,
    taxonomy_version: str,
    guideline_version: str,
    idempotency_key: str,
    request_sha256: str,
    provenance: Mapping[str, object],
    drift_jobs: Sequence[int],
) -> Snapshot:
    with transaction.atomic():
        parent = (
            Snapshot.objects.filter(dataset_id=dataset_id, status=Snapshot.Status.LOCKED)
            .order_by("-created_at", "-id")
            .first()
        )
        return Snapshot.objects.create(
            dataset_id=dataset_id,
            status=Snapshot.Status.FAILED,
            failure_reason="drift_detected",
            parent_snapshot=parent,
            taxonomy_version=taxonomy_version,
            guideline_version=guideline_version,
            schema_version=SCHEMA_VERSION,
            idempotency_key=idempotency_key,
            request_sha256=request_sha256,
            normalized_json={},
            provenance=dict(provenance),
            skipped_shape_counts={},
            drift_jobs=sorted(set(drift_jobs)),
            created_by=created_by,
        )


def create_snapshot_from_cvat(
    *,
    dataset_id: int,
    scope: SnapshotScope,
    note: str,
    created_by: User,
    idempotency_key: str,
    client: CvatReadClient | None = None,
    storage: SnapshotStorage | None = None,
) -> Snapshot:
    """Export one deterministic snapshot and lock it only after a second source read."""

    request_payload: dict[str, object] = {
        "dataset_id": dataset_id,
        "scope": scope.payload(),
        "note": note,
    }
    request_sha256 = sha256_json(request_payload)
    existing = Snapshot.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        if existing.request_sha256 != request_sha256:
            raise SnapshotRequestConflict("Idempotency-Key was used for another request")
        return existing

    owns_client = client is None
    cvat = client or CvatReadClient(settings.CVAT_BASE_URL, settings.CVAT_SERVICE_TOKEN)
    media_storage = storage or ObjectStorage.from_django_settings("snapshots")
    try:
        selected = _selected_jobs(cvat, dataset_id=dataset_id, scope=scope)
        taxonomy_version = _taxonomy_version(cvat, dataset_id)
        guideline_version = _guideline_version()
        exports: list[JobExport] = []
        initial_revisions: dict[int, SourceRevision] = {}
        for selected_job in selected:
            job_id = _positive_int(selected_job.get("id"), field="job.id")
            # Collection responses can lag behind the object endpoint. Use an
            # authoritative first read so the later drift comparison is fair.
            job = cvat.get_job(job_id)
            task_id = _job_task_id(job)
            if _project_id(cvat.get_task(task_id)) != dataset_id:
                raise SnapshotSourceError(f"CVAT job {job_id} moved outside dataset {dataset_id}")
            annotations = cvat.get_job_annotations(job_id)
            initial_revisions[job_id] = _source_revision(
                cvat, job_id, job=job, annotations=annotations
            )
            assignee_cvat_id = _assignee_id(job)
            assignee_user_id = None
            if assignee_cvat_id is not None:
                assignee_user_id = (
                    CvatIdentity.objects.filter(cvat_user_id=assignee_cvat_id)
                    .values_list("user_id", flat=True)
                    .first()
                )
            exports.append(
                JobExport(
                    cvat_job_id=job_id,
                    cvat_task_id=task_id,
                    source_updated_at=initial_revisions[job_id].updated_date,
                    annotations=annotations,
                    frames=_frame_exports(cvat, media_storage, job_id=job_id, job=job),
                    assignee_cvat_user_id=assignee_cvat_id,
                    assignee_user_id=assignee_user_id,
                )
            )

        drift_jobs = [
            job_id
            for job_id, initial in initial_revisions.items()
            if _source_revision(cvat, job_id) != initial
        ]
        provenance: dict[str, object] = {
            "source": "CVAT",
            "cvat_project_id": dataset_id,
            "scope": scope.payload(),
            "note": note,
        }
        if drift_jobs:
            return _failed_drift_snapshot(
                dataset_id=dataset_id,
                created_by=created_by,
                taxonomy_version=taxonomy_version,
                guideline_version=guideline_version,
                idempotency_key=idempotency_key,
                request_sha256=request_sha256,
                provenance=provenance,
                drift_jobs=drift_jobs,
            )

        parent = (
            Snapshot.objects.filter(dataset_id=dataset_id, status=Snapshot.Status.LOCKED)
            .order_by("-created_at", "-id")
            .first()
        )
        return create_locked_snapshot(
            dataset_id=dataset_id,
            created_by=created_by,
            jobs=exports,
            taxonomy_version=taxonomy_version,
            guideline_version=guideline_version,
            parent_snapshot=parent,
            provenance=provenance,
            idempotency_key=idempotency_key,
            request_sha256=request_sha256,
        )
    except IntegrityError:
        # A concurrent request can finish after the initial idempotency lookup.
        # The unique database key is the final arbiter; return only an exact replay.
        concurrent = Snapshot.objects.filter(idempotency_key=idempotency_key).first()
        if concurrent is not None and concurrent.request_sha256 == request_sha256:
            return concurrent
        raise
    finally:
        if owns_client:
            cvat.close()
