"""Dataset upload lifecycle, immutable run binding and retryable file cleanup."""

from __future__ import annotations

import hashlib
import logging
import math
import uuid
from functools import partial
from pathlib import PurePath
from typing import Any

from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import transaction
from django.utils import timezone

from audit.services import append_audit_event
from engines.interface import FrameKey
from engines.matching import ALGORITHM_VERSION
from engines.metric import _truth_boxes, parse_gt_frames
from runs.models import EngineResult, GroundTruthUpload, QCRun, Reference
from snapshots.models import Snapshot, SnapshotFrame

logger = logging.getLogger("labelx.ground_truth")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def lock_dataset(dataset_id: int) -> None:
    # A stable existing row serializes uploads and run binding across snapshots.
    Snapshot.objects.select_for_update().filter(dataset_id=dataset_id).order_by("pk").first()


def create_upload(
    *,
    snapshot: Snapshot,
    actor: Any,
    file: Any,
    mapping_version: str,
    key: str,
    matching_threshold: float = 0.5,
    minimum_area: float = 0.0,
) -> GroundTruthUpload:
    if not math.isfinite(matching_threshold) or not 0 <= matching_threshold <= 1:
        raise ValueError("Ngưỡng matching phải là số hữu hạn trong khoảng 0–1.")
    if not math.isfinite(minimum_area) or minimum_area < 0:
        raise ValueError("Diện tích tối thiểu phải là số hữu hạn không âm.")
    if snapshot.status != Snapshot.Status.LOCKED:
        raise ValueError("Snapshot phải được khóa trước khi upload Ground Truth.")
    raw = file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("Ground Truth tối đa 20 MiB.")
    frames = parse_gt_frames(raw, snapshot.pk, mapping_version)
    if not frames:
        raise ValueError("Ground Truth phải có ít nhất một frame.")
    snapshot_frames = {
        FrameKey(task, number): (width, height)
        for task, number, width, height in SnapshotFrame.objects.filter(
            snapshot_job__snapshot=snapshot
        ).values_list("snapshot_job__cvat_task_id", "frame_index", "width", "height")
    }
    box_count = 0
    for identity, frame in frames.items():
        if identity not in snapshot_frames:
            raise ValueError("Ground Truth chứa frame không thuộc Snapshot đã chọn.")
        width, height = snapshot_frames[identity]
        for box in _truth_boxes(frame, 0):
            if not (0 <= box.x1 < box.x2 <= width and 0 <= box.y1 < box.y2 <= height):
                raise ValueError("Bounding box vượt kích thước ảnh trong Snapshot.")
            box_count += 1
    checksum = hashlib.sha256(raw).hexdigest()
    digest = hashlib.sha256(
        f"{snapshot.pk}:{checksum}:{mapping_version}:{matching_threshold}:{minimum_area}".encode()
    ).hexdigest()
    with transaction.atomic():
        lock_dataset(snapshot.dataset_id)
        existing = Reference.objects.filter(idempotency_key=key).first()
        if existing:
            if existing.created_by_id != actor.pk or existing.request_sha256 != digest:
                raise ValueError("Idempotency-Key đã dùng cho upload khác.")
            return GroundTruthUpload.objects.get(reference=existing)
        source = storages["snapshots"].save(
            f"ground-truth/{snapshot.dataset_id}/{uuid.uuid4().hex}.json", ContentFile(raw)
        )
        try:
            ref = Reference.objects.create(
                snapshot=snapshot,
                gt_source=source,
                gt_checksum=checksum,
                mapping_version=mapping_version,
                matching_threshold=matching_threshold,
                minimum_area=minimum_area,
                algorithm_version=ALGORITHM_VERSION,
                created_by=actor,
                idempotency_key=key,
                request_sha256=digest,
            )
            previous_ids = list(
                GroundTruthUpload.objects.filter(
                    dataset_id=snapshot.dataset_id, is_current=True
                ).values_list("reference_id", flat=True)
            )
            GroundTruthUpload.objects.filter(
                dataset_id=snapshot.dataset_id, is_current=True
            ).update(is_current=False)
            upload = GroundTruthUpload.objects.create(
                reference=ref,
                dataset_id=snapshot.dataset_id,
                filename=PurePath(file.name.replace("\\", "/")).name[:255],
                frame_count=len(frames),
                box_count=box_count,
            )
            append_audit_event(
                actor=actor,
                action="ground_truth.upload",
                object_type="reference",
                object_id=ref.pk,
                before=None,
                after={"gt_checksum": checksum, "frame_count": len(frames), "box_count": box_count},
                revision=snapshot.revision_sha256,
            )
            for previous_id in previous_ids:
                transaction.on_commit(partial(cleanup_upload_safely, previous_id))
            return upload
        except Exception:
            storages["snapshots"].delete(source)
            raise


def bind_upload(snapshot: Snapshot, reference_id: int | None) -> Reference | None:
    """Called inside run creation transaction; same lock order as upload/cleanup."""
    lock_dataset(snapshot.dataset_id)
    uploads = GroundTruthUpload.objects.select_for_update().select_related("reference")
    if reference_id is None:
        upload = uploads.filter(dataset_id=snapshot.dataset_id, is_current=True).first()
    else:
        upload = uploads.filter(reference_id=reference_id, dataset_id=snapshot.dataset_id).first()
        if upload is None:
            raise ValueError("Ground Truth không thuộc Dataset đã chọn.")
    if upload is None:
        return None  # Preserve legacy explicitly configured references.
    ref = upload.reference
    if ref.snapshot_id != snapshot.pk:
        raise ValueError("Ground Truth không thuộc Snapshot đã chọn. Hãy upload lại.")
    if upload.deleted_at:
        raise ValueError("File Ground Truth đã xóa sau lần chạy trước. Hãy upload lại.")
    if not upload.is_current:
        raise ValueError("Ground Truth đã được thay thế. Hãy tải lại bản hiện hành của Dataset.")
    if ref.status != Reference.Status.LOCKED or not ref.locked_at:
        raise ValueError("Ground Truth cần được QA Lead khác người upload duyệt trước khi chạy.")
    return ref


def cleanup_upload(reference_id: int) -> bool:
    with transaction.atomic():
        upload = (
            GroundTruthUpload.objects.select_for_update()
            .select_related("reference")
            .filter(reference_id=reference_id, deleted_at__isnull=True)
            .first()
        )
        if upload is None:
            return False
        runs = QCRun.objects.filter(metric_reference_id=reference_id)
        if not runs.exists() and upload.is_current:
            return False
        if runs.exclude(status=QCRun.Status.COMPLETED).exists():
            return False
        # Completed run can still contain Not checked metric units. Retain its input.
        checked = EngineResult.objects.filter(
            run__in=runs,
            engine="metric",
            status="checked",
            failed_units=0,
            not_checked_units=0,
            completed_units__gt=0,
        ).count()
        if checked != runs.count():
            return False
        storages["snapshots"].delete(upload.reference.gt_source)
        upload.deleted_at = timezone.now()
        upload.save(update_fields=["deleted_at"])
        return True


def cleanup_upload_safely(reference_id: int) -> bool:
    try:
        return cleanup_upload(reference_id)
    except Exception:
        logger.exception(
            "Ground Truth cleanup will be retried", extra={"reference_id": reference_id}
        )
        return False


def cleanup_finished_uploads() -> int:
    ids = (
        GroundTruthUpload.objects.filter(
            deleted_at__isnull=True,
        )
        .values_list("reference_id", flat=True)
        .distinct()
    )
    return sum(cleanup_upload_safely(pk) for pk in ids)
