"""Deterministic ``labelx.snapshot.v1`` normalization and SHA-256 helpers.

The normalized JSON is the shared boundary consumed by QC engines. It contains
only stable source data: no database ids, creation timestamps, or parent links.
Consequently the same CVAT export produces the same job and snapshot hashes.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

SCHEMA_VERSION = "labelx.snapshot.v1"
COORDINATE_DECIMALS = 6


@dataclass(frozen=True)
class FrameExport:
    """Media and source mapping for one CVAT frame."""

    frame_index: int
    file_name: str
    width: int
    height: int
    media_bytes: bytes
    media_storage_key: str
    source_frame_id: int | None = None
    media_mime_type: str = "image/jpeg"


@dataclass(frozen=True)
class JobExport:
    """Stable inputs captured while exporting one CVAT job."""

    cvat_job_id: int
    cvat_task_id: int
    source_updated_at: str
    annotations: Mapping[str, object]
    frames: Sequence[FrameExport]
    assignee_cvat_user_id: int | None = None
    assignee_user_id: int | None = None


@dataclass(frozen=True)
class NormalizedJob:
    """Canonical result persisted by ``SnapshotJob``."""

    payload: dict[str, object]
    canonical_json: str
    sha256: str
    rectangle_count: int
    skipped_shape_counts: dict[str, int]


def canonical_json(value: object) -> str:
    """Serialize JSON using the single representation hashed by LabelX."""

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _integer(value: object, *, field: str, minimum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return value


def _number(value: object, *, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{field} must be numeric")
    rounded = round(float(value), COORDINATE_DECIMALS)
    return 0.0 if rounded == 0 else rounded


def _attributes(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    result: list[dict[str, object]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        result.append(
            {
                "spec_id": _integer(raw.get("spec_id"), field="attribute.spec_id"),
                "value": raw.get("value"),
            }
        )
    return sorted(result, key=lambda item: int(item["spec_id"]))


def _shape_type(raw: object) -> str:
    if not isinstance(raw, Mapping):
        return "unknown"
    value = raw.get("type")
    return value if isinstance(value, str) and value else "unknown"


def _rectangle(
    raw: Mapping[str, object],
    *,
    source_kind: str,
    source_id: int,
    frame_index: int,
    label_id: int,
) -> dict[str, object]:
    points = raw.get("points")
    if not isinstance(points, Sequence) or isinstance(points, (str, bytes)):
        raise TypeError("rectangle.points must be a list")
    if len(points) != 4:
        raise ValueError("rectangle.points must contain exactly four coordinates")
    return {
        "attributes": _attributes(raw.get("attributes", [])),
        "frame_index": frame_index,
        "label_id": label_id,
        "occluded": bool(raw.get("occluded", False)),
        "outside": bool(raw.get("outside", False)),
        "points": [_number(point, field="rectangle.points") for point in points],
        "rotation": _number(raw.get("rotation", 0), field="rectangle.rotation"),
        "source": {"id": source_id, "kind": source_kind},
        "z_order": _integer(raw.get("z_order", 0), field="rectangle.z_order"),
    }


def _shape_sort_key(shape: Mapping[str, object]) -> tuple[object, ...]:
    source = shape["source"]
    if not isinstance(source, Mapping):  # pragma: no cover - constructed internally
        raise TypeError("shape.source must be an object")
    return (
        str(source["kind"]),
        int(source["id"]),
        int(shape["label_id"]),
        canonical_json(shape),
    )


def normalize_job(export: JobExport) -> NormalizedJob:
    """Keep rectangles, count every skipped shape type, and hash canonical JSON."""

    _integer(export.cvat_job_id, field="cvat_job_id", minimum=1)
    _integer(export.cvat_task_id, field="cvat_task_id", minimum=1)
    if not export.source_updated_at.strip():
        raise ValueError("source_updated_at must not be empty")
    if not export.frames:
        raise ValueError("a snapshot job must contain at least one frame")

    frame_payloads: dict[int, dict[str, object]] = {}
    for frame in export.frames:
        index = _integer(frame.frame_index, field="frame_index", minimum=0)
        if index in frame_payloads:
            raise ValueError(f"duplicate frame_index {index}")
        if not frame.file_name.strip() or not frame.media_storage_key.strip():
            raise ValueError("frame file_name and media_storage_key must not be empty")
        frame_payloads[index] = {
            "file_name": frame.file_name,
            "frame_index": index,
            "height": _integer(frame.height, field="height", minimum=1),
            "media": {
                "mime_type": frame.media_mime_type,
                "sha256": hashlib.sha256(frame.media_bytes).hexdigest(),
                "size_bytes": len(frame.media_bytes),
                "storage_key": frame.media_storage_key,
            },
            "shapes": [],
            "source_frame_id": frame.source_frame_id,
            "width": _integer(frame.width, field="width", minimum=1),
        }

    skipped: Counter[str] = Counter()
    annotations = export.annotations
    raw_shapes = annotations.get("shapes", [])
    raw_tracks = annotations.get("tracks", [])
    if not isinstance(raw_shapes, Sequence) or isinstance(raw_shapes, (str, bytes)):
        raise TypeError("annotations.shapes must be a list")
    if not isinstance(raw_tracks, Sequence) or isinstance(raw_tracks, (str, bytes)):
        raise TypeError("annotations.tracks must be a list")

    for raw in raw_shapes:
        shape_type = _shape_type(raw)
        if not isinstance(raw, Mapping) or shape_type != "rectangle":
            skipped[shape_type] += 1
            continue
        frame_index = _integer(raw.get("frame"), field="shape.frame", minimum=0)
        if frame_index not in frame_payloads:
            raise ValueError(f"shape references missing frame_index {frame_index}")
        rectangle = _rectangle(
            raw,
            source_kind="shape",
            source_id=_integer(raw.get("id"), field="shape.id", minimum=0),
            frame_index=frame_index,
            label_id=_integer(raw.get("label_id"), field="shape.label_id", minimum=0),
        )
        shapes = frame_payloads[frame_index]["shapes"]
        assert isinstance(shapes, list)
        shapes.append(rectangle)

    for raw_track in raw_tracks:
        if not isinstance(raw_track, Mapping):
            skipped["unknown"] += 1
            continue
        track_id = _integer(raw_track.get("id"), field="track.id", minimum=0)
        label_id = _integer(raw_track.get("label_id"), field="track.label_id", minimum=0)
        raw_keyframes = raw_track.get("shapes", [])
        if not isinstance(raw_keyframes, Sequence) or isinstance(raw_keyframes, (str, bytes)):
            raise TypeError("track.shapes must be a list")
        for raw in raw_keyframes:
            shape_type = _shape_type(raw)
            if not isinstance(raw, Mapping) or shape_type != "rectangle":
                skipped[shape_type] += 1
                continue
            frame_index = _integer(raw.get("frame"), field="track.shape.frame", minimum=0)
            if frame_index not in frame_payloads:
                raise ValueError(f"track shape references missing frame_index {frame_index}")
            rectangle = _rectangle(
                raw,
                source_kind="track",
                source_id=track_id,
                frame_index=frame_index,
                label_id=label_id,
            )
            shapes = frame_payloads[frame_index]["shapes"]
            assert isinstance(shapes, list)
            shapes.append(rectangle)

    frames = [frame_payloads[index] for index in sorted(frame_payloads)]
    rectangle_count = 0
    for frame in frames:
        shapes = frame["shapes"]
        assert isinstance(shapes, list)
        shapes.sort(key=_shape_sort_key)
        rectangle_count += len(shapes)

    payload: dict[str, object] = {
        "assignee_cvat_user_id": export.assignee_cvat_user_id,
        "assignee_user_id": export.assignee_user_id,
        "cvat_job_id": export.cvat_job_id,
        "cvat_task_id": export.cvat_task_id,
        "frames": frames,
        "schema_version": SCHEMA_VERSION,
        "skipped_shapes": dict(sorted(skipped.items())),
        "source_updated_at": export.source_updated_at,
    }
    serialized = canonical_json(payload)
    return NormalizedJob(
        payload=payload,
        canonical_json=serialized,
        sha256=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        rectangle_count=rectangle_count,
        skipped_shape_counts=dict(sorted(skipped.items())),
    )


def normalize_snapshot(
    *,
    dataset_id: int,
    jobs: Sequence[NormalizedJob],
    taxonomy_version: str,
    guideline_version: str,
) -> tuple[dict[str, object], str]:
    """Build and hash a stable snapshot payload, independent of export order."""

    if not jobs:
        raise ValueError("a snapshot must contain at least one job")
    ordered = sorted(jobs, key=lambda job: int(job.payload["cvat_job_id"]))
    job_ids = [int(job.payload["cvat_job_id"]) for job in ordered]
    if len(job_ids) != len(set(job_ids)):
        raise ValueError("cvat_job_id values must be unique within a snapshot")
    payload: dict[str, object] = {
        "dataset_id": _integer(dataset_id, field="dataset_id", minimum=1),
        "guideline_version": guideline_version,
        "jobs": [job.payload for job in ordered],
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": taxonomy_version,
    }
    return payload, sha256_json(payload)
