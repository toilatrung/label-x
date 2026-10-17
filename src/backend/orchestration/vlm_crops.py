"""Nguồn crop thật cho VLM: cắt vùng annotation của candidate từ ảnh frame trong snapshot (M04A-04).

- Ảnh frame lấy từ object storage (alias `snapshots`) theo `media_storage_key`; kiểm sha256 với
  `media_sha256` đã khoá trong snapshot nên crop gắn chặt với revision.
- Vùng crop là hợp bbox của các annotation trong `anchor.objects` (id dạng `kind:id` khớp
  `shape.source`), nới thêm một lề tương đối, kẹp trong ảnh. Không đoán: anchor không phân giải
  được thành bbox hợp lệ thì lỗi `invalid_crop`, không bao giờ gửi cả frame.
- `CropInput.origin` lưu ánh xạ crop → ảnh gốc (frame, box gốc, box đã nới, kích thước đầu ra)
  để evidence truy được về snapshot/annotation.
- Không ghi bytes ảnh hay khoá storage vào log/lỗi.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from typing import Any

from PIL import Image, UnidentifiedImageError

from orchestration.models import CandidateRecord
from snapshots.models import SnapshotFrame
from storage.client import ObjectStorage
from vlm.contract import MAX_CROP_BYTES, CropInput
from vlm.errors import VlmInvalidCropError

PADDING_RATIO = 0.1
MIN_PADDING_PX = 4.0
MAX_SIDE_PX = 1024
SHRINK_SIDES = (768, 512, 384, 256)
MAX_SOURCE_PIXELS = 50_000_000
MAX_SOURCE_BYTES = 50 * 1024 * 1024
MIN_BOX_PX = 2.0


def _object_ids(candidate: CandidateRecord) -> list[str]:
    anchor = candidate.anchor
    objects = anchor.get("objects") if isinstance(anchor, dict) else None
    if not isinstance(objects, list):
        return []
    result = []
    for obj in objects:
        if not isinstance(obj, dict) or not isinstance(obj.get("id"), str):
            continue
        namespace, object_id = obj.get("namespace"), obj["id"]
        if namespace == "detector":
            continue  # Predictions are not annotation identities in a locked Snapshot.
        if namespace in ("shape", "track") and not object_id.startswith(f"{namespace}:"):
            object_id = f"{namespace}:{object_id}"
        result.append(object_id)
    return sorted(result)


def _shape_box(shape: dict[str, Any]) -> tuple[float, float, float, float] | None:
    """bbox của shape. Giả định: shape trong snapshot chỉ là rectangle (normalization chỉ giữ
    rectangle; shape khác bị bỏ trước khi vào snapshot) và bỏ qua `rotation` (box trục)."""
    points = shape.get("points")
    if not isinstance(points, list) or len(points) != 4:
        return None
    if any(isinstance(p, bool) or not isinstance(p, int | float) for p in points):
        return None
    x1, y1, x2, y2 = (float(p) for p in points)
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def _shape_id(shape: dict[str, Any]) -> str | None:
    source = shape.get("source")
    if isinstance(source, dict) and "kind" in source and "id" in source:
        return f"{source['kind']}:{source['id']}"
    return None


def union_box(
    shapes: list[dict[str, Any]], object_ids: list[str]
) -> tuple[float, float, float, float] | None:
    """Hợp bbox của đúng các annotation được anchor tham chiếu; thiếu một cái nào cũng là None."""
    by_id = {sid: shape for shape in shapes if (sid := _shape_id(shape)) is not None}
    boxes = []
    for object_id in object_ids:
        shape = by_id.get(object_id)
        box = _shape_box(shape) if shape is not None else None
        if box is None:
            return None
        boxes.append(box)
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def pad_box(
    box: tuple[float, float, float, float], width: int, height: int
) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = box
    pad = max(MIN_PADDING_PX, PADDING_RATIO * max(x2 - x1, y2 - y1))
    return (
        max(0.0, x1 - pad),
        max(0.0, y1 - pad),
        min(float(width), x2 + pad),
        min(float(height), y2 + pad),
    )


def candidate_box(
    candidate: CandidateRecord, frame: SnapshotFrame
) -> tuple[float, float, float, float] | None:
    """Use frozen annotation identities, or the verified Detector's explicit prediction box."""
    objects = _object_ids(candidate)
    if objects:
        return union_box(frame.shapes, objects)
    evidence = candidate.evidence
    if candidate.engine != "detector" or evidence.get("artifact_verified") is not True:
        return None
    if evidence.get("coordinate_space", "original") != "original":
        return None
    box = evidence.get("prediction_bbox")
    if (
        not isinstance(box, list)
        or len(box) != 4
        or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            for v in box
        )
    ):
        return None
    x1, y1, x2, y2 = (float(v) for v in box)
    if not (0 <= x1 < x2 <= frame.width and 0 <= y1 < y2 <= frame.height):
        return None
    return x1, y1, x2, y2


class SnapshotCropProvider:
    """CropProvider đọc ảnh từ snapshot đã khoá."""

    def __init__(self, storage: ObjectStorage | None = None) -> None:
        self._storage = storage
        self._frames: dict[tuple[int, int, int], SnapshotFrame | None] = {}

    def prepare(self, candidates: list[CandidateRecord]) -> None:
        """Load only relevant frames once per preparation batch; never read image bytes here."""
        wanted = {(c.run.snapshot_id, c.cvat_task_id, c.frame_number) for c in candidates}
        if not wanted:
            return
        self._frames = dict.fromkeys(wanted)
        frames = (
            SnapshotFrame.objects.filter(
                snapshot_job__snapshot_id__in={k[0] for k in wanted},
                snapshot_job__cvat_task_id__in={k[1] for k in wanted},
                frame_index__in={k[2] for k in wanted},
            )
            .select_related("snapshot_job")
            .defer("snapshot_job__normalized_json", "snapshot_job__skipped_shape_counts")
            .order_by("pk")
        )
        for frame in frames:
            key = (
                frame.snapshot_job.snapshot_id,
                frame.snapshot_job.cvat_task_id,
                frame.frame_index,
            )
            if key in self._frames and self._frames[key] is None:
                self._frames[key] = frame

    def _frame(self, candidate: CandidateRecord) -> SnapshotFrame:
        key = (candidate.run.snapshot_id, candidate.cvat_task_id, candidate.frame_number)
        if key not in self._frames:
            self._frames[key] = (
                SnapshotFrame.objects.filter(
                    snapshot_job__snapshot_id=key[0],
                    snapshot_job__cvat_task_id=key[1],
                    frame_index=key[2],
                )
                .select_related("snapshot_job")
                .defer("snapshot_job__normalized_json", "snapshot_job__skipped_shape_counts")
                .first()
            )
        frame = self._frames[key]
        if frame is None:
            raise VlmInvalidCropError("frame của candidate không có trong snapshot")
        source = candidate.evidence.get("source_frame")
        if source is not None and source != {
            "snapshot_id": candidate.run.snapshot_id,
            "revision_sha256": candidate.run.snapshot.revision_sha256,
            "cvat_task_id": frame.snapshot_job.cvat_task_id,
            "frame_number": frame.frame_index,
            "media_sha256": frame.media_sha256,
            "width": frame.width,
            "height": frame.height,
        }:
            raise VlmInvalidCropError("evidence không khớp frame/revision của snapshot")
        return frame

    def identity(self, candidate: CandidateRecord) -> str:
        """sha256(media_sha256 + bbox + lề): tất định, không tải ảnh."""
        try:
            frame = self._frame(candidate)
        except VlmInvalidCropError:
            return ""
        box = candidate_box(candidate, frame)
        if box is None:
            return ""
        payload = {"media": frame.media_sha256, "box": box, "pad": PADDING_RATIO}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def load(self, candidate: CandidateRecord) -> CropInput:
        frame = self._frame(candidate)
        box = candidate_box(candidate, frame)
        if box is None:
            raise VlmInvalidCropError("anchor không phân giải được thành bbox hợp lệ")
        if frame.width <= 0 or frame.height <= 0 or frame.width * frame.height > MAX_SOURCE_PIXELS:
            raise VlmInvalidCropError("kích thước ảnh gốc không hợp lệ")
        storage = self._storage or ObjectStorage.from_django_settings("snapshots")
        expected = int(frame.media_size_bytes)
        if not 0 < expected <= MAX_SOURCE_BYTES:
            raise VlmInvalidCropError("kích thước byte của ảnh gốc không hợp lệ")
        try:
            head = storage.head(frame.media_storage_key)
            if head is None or head.size != expected:
                # Trần kích thước TRƯỚC khi đọc: không nạp object lạ/lớn vào RAM.
                raise VlmInvalidCropError("object ảnh gốc không khớp kích thước của snapshot")
            raw = storage.get(frame.media_storage_key)
        except VlmInvalidCropError:
            raise
        except Exception:
            raise VlmInvalidCropError("không đọc được ảnh gốc từ storage") from None
        if hashlib.sha256(raw).hexdigest() != frame.media_sha256:
            raise VlmInvalidCropError("ảnh gốc không khớp sha256 của snapshot")
        padded = pad_box(box, frame.width, frame.height)
        if padded[2] - padded[0] < MIN_BOX_PX or padded[3] - padded[1] < MIN_BOX_PX:
            raise VlmInvalidCropError("vùng crop quá nhỏ")
        try:
            opened = Image.open(io.BytesIO(raw))
            if opened.width * opened.height > MAX_SOURCE_PIXELS:
                raise VlmInvalidCropError("ảnh gốc quá lớn")
            image: Image.Image = opened.convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError):
            raise VlmInvalidCropError("ảnh gốc không giải mã được") from None
        if (image.width, image.height) != (frame.width, frame.height):
            raise VlmInvalidCropError("kích thước ảnh không khớp snapshot")
        left, upper, right, lower = (round(v) for v in padded)
        region = image.crop((left, upper, right, lower))
        data, size = _encode(region)
        origin: dict[str, Any] = {
            "snapshot_id": candidate.run.snapshot_id,
            "revision_sha256": candidate.run.snapshot.revision_sha256,
            "frame": {
                "cvat_task_id": candidate.cvat_task_id,
                "frame_number": candidate.frame_number,
                "media_sha256": frame.media_sha256,
                "width": frame.width,
                "height": frame.height,
            },
            "objects": _object_ids(candidate),
            "box": [round(v, 2) for v in box],
            "padded_box": [round(v, 2) for v in padded],
            "padding_ratio": PADDING_RATIO,
            "output_size": list(size),
            "encoding": "png",
        }
        return CropInput(data, "image/png", origin)


def _encode(region: Image.Image) -> tuple[bytes, tuple[int, int]]:
    """PNG; thu nhỏ (không phóng to) đến khi ≤ MAX_CROP_BYTES."""
    for side in (MAX_SIDE_PX, *SHRINK_SIDES):
        image = region
        if max(image.size) > side:
            image = image.copy()
            image.thumbnail((side, side))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        if buffer.tell() <= MAX_CROP_BYTES:
            return buffer.getvalue(), image.size
    raise VlmInvalidCropError("crop vượt kích thước tối đa sau khi thu nhỏ")
