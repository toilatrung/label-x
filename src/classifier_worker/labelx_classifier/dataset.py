"""Crop dataset builder with provenance, source-group split and a hashed manifest (M04B-01).

Input is a normalized LabelX snapshot (``labelx.snapshot.v1``) plus the frame images it
references. Every crop traces back to snapshot -> job -> frame -> annotation. Labels outside the
class map are rejected (never silently turned into an eleventh class). The split is a fixed,
order-independent function of the source group, so no group spans two splits. The split is a
technical partition only; it is not a calibration pass or a held-out reference.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from .crops import INPUT_SIZE, MIN_SIDE_PX, CropError, letterbox_crop
from .taxonomy import CLASS_INDEX, CLASSES, MAPPING_VERSION

SCHEMA_VERSION = "labelx.classifier.dataset.v1"
GROUP_KEYS = ("task", "job", "frame")
FIT_SPLITS = ("train", "val")
HELD_OUT = "held_out"
ALL_SPLITS = ("train", "val", HELD_OUT)
DATA_ORIGINS = ("fixture", "real")
MAX_FRAME_PIXELS = 64_000_000


class DatasetError(ValueError):
    """Raised when the input snapshot or options are unusable."""


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class SplitConfig:
    """Fractions of source groups. ``held_out`` defaults to 0: nothing is reserved silently."""

    val: float = 0.2
    held_out: float = 0.0
    seed: str = "labelx-m04b-v1"

    def __post_init__(self) -> None:
        if not (0.0 <= self.val < 1.0 and 0.0 <= self.held_out < 1.0):
            raise DatasetError("split fractions must be in [0, 1)")
        if self.val + self.held_out >= 1.0:
            raise DatasetError("val + held_out must leave a train share")

    def assign(self, group: str) -> str:
        bucket = int(sha256_hex(f"{self.seed}:{group}".encode())[:12], 16) / float(16**12)
        if bucket < self.held_out:
            return HELD_OUT
        if bucket < self.held_out + self.val:
            return "val"
        return "train"


def _group_of(kind: str, job: Mapping[str, Any], frame: Mapping[str, Any]) -> str:
    if kind == "task":
        return f"task:{job['cvat_task_id']}"
    if kind == "job":
        return f"job:{job['cvat_job_id']}"
    return f"frame:{job['cvat_job_id']}:{frame['frame_index']}"


def parse_label_map(raw: Mapping[str, str]) -> dict[int, str]:
    """``{"<label_id>": "<class name>"}`` -> ``{int: str}`` (names lower-cased)."""

    result: dict[int, str] = {}
    for key, name in raw.items():
        try:
            result[int(key)] = str(name).strip().lower()
        except ValueError as exc:
            raise DatasetError(f"label map key {key!r} is not an integer label_id") from exc
    return result


def iter_candidates(
    snapshot: Mapping[str, Any], rejected: list[dict[str, Any]]
) -> Iterator[tuple[Mapping[str, Any], Mapping[str, Any], Any]]:
    """Walk jobs/frames/shapes; structurally wrong nodes become ``malformed_*`` rejections."""

    for job in snapshot.get("jobs", []):
        if not isinstance(job, Mapping) or not isinstance(job.get("frames"), list):
            rejected.append(_reject("malformed_job", _safe(job), {}, {}, "job must hold frames[]"))
            continue
        for frame in job["frames"]:
            if not isinstance(frame, Mapping) or not isinstance(frame.get("shapes"), list):
                rejected.append(_reject("malformed_frame", job, _safe(frame), {}, "frame/shapes"))
                continue
            for shape in frame["shapes"]:
                if not isinstance(shape, Mapping):
                    rejected.append(_reject("malformed_shape", job, frame, {}, "shape"))
                    continue
                yield job, frame, shape


def _reject(reason: str, job: Mapping, frame: Mapping, shape: Mapping, detail: str = "") -> dict:
    source = shape.get("source") or {}
    return {
        "reason": reason,
        "detail": detail,
        "cvat_job_id": job.get("cvat_job_id"),
        "frame_index": frame.get("frame_index"),
        "source_kind": source.get("kind"),
        "source_id": source.get("id"),
        "label_id": shape.get("label_id"),
    }


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError("expected a finite number")
    return float(value)


def _parse_shape(shape: Mapping[str, Any]) -> tuple[int, list[float], float, dict[str, Any]]:
    """Strictly typed view of one shape; raises ``ValueError`` on any malformed field."""

    label_id = shape.get("label_id")
    if isinstance(label_id, bool) or not isinstance(label_id, int):
        raise ValueError("label_id must be an integer")
    points = shape.get("points")
    if not isinstance(points, list | tuple) or len(points) not in (4,):
        raise ValueError("points must be a list of 4 numbers")
    box = [_number(value) for value in points]
    rotation = _number(shape.get("rotation") or 0.0)
    source = shape.get("source")
    if not isinstance(source, Mapping) or not isinstance(source.get("kind"), str):
        raise ValueError("source.kind is required")
    source_id = source.get("id")
    if isinstance(source_id, bool) or not isinstance(source_id, int | str):
        raise ValueError("source.id is required")
    return label_id, box, rotation, {"kind": source["kind"], "id": source_id}


def _remove_previous_crops(out_dir: Path, crops_dir: Path) -> None:
    """Drop only crops a previous build of this tool wrote; never a user's own files.

    The previous ``dataset-manifest.json`` lists those files. Without such a manifest a
    non-empty ``crops`` directory is refused rather than emptied.
    """

    if not crops_dir.exists():
        return
    previous = out_dir / "dataset-manifest.json"
    listed: list[str] = []
    if previous.is_file():
        try:
            data = json.loads(previous.read_text(encoding="utf-8"))
            if data.get("schema_version") == SCHEMA_VERSION:
                listed = [str(record["path"]) for record in data.get("crops", [])]
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            listed = []
    if not listed and any(crops_dir.iterdir()):
        raise DatasetError(
            f"{crops_dir} is not empty and has no dataset-manifest.json from this tool; "
            "refusing to modify it. Use an empty out_dir."
        )
    crops_root = crops_dir.resolve()
    for relative in listed:
        path = (out_dir / relative).resolve()
        if crops_root in path.parents and path.is_file():  # only files under crops/
            path.unlink()
    for directory in sorted((p for p in crops_dir.rglob("*") if p.is_dir()), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()


def build_dataset(
    snapshot: Mapping[str, Any],
    *,
    image_root: Path,
    out_dir: Path,
    label_map: Mapping[int, str],
    split: SplitConfig | None = None,
    group_by: str = "task",
    snapshot_revision_sha256: str | None = None,
    min_side: int = MIN_SIDE_PX,
    data_origin: str = "fixture",
) -> dict[str, Any]:
    """Write crops under ``out_dir`` and return the manifest (also saved as JSON)."""

    if data_origin not in DATA_ORIGINS:
        raise DatasetError(f"data_origin must be one of {DATA_ORIGINS}")
    if group_by not in GROUP_KEYS:
        raise DatasetError(f"group_by must be one of {GROUP_KEYS}")
    if snapshot.get("schema_version") != "labelx.snapshot.v1":
        raise DatasetError("snapshot.schema_version must be labelx.snapshot.v1")
    if not isinstance(snapshot.get("jobs"), list):
        raise DatasetError("snapshot.jobs must be a list")
    split = split or SplitConfig()
    snapshot_sha = sha256_hex(canonical_json(snapshot))
    crops_dir = out_dir / "crops"
    _remove_previous_crops(out_dir, crops_dir)
    records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    image_cache: dict[tuple[int, int], Image.Image | None] = {}

    for job, frame, shape in iter_candidates(snapshot, rejected):
        try:
            record = _process_shape(
                job,
                frame,
                shape,
                snapshot_sha,
                snapshot,
                image_root,
                crops_dir,
                out_dir,
                label_map,
                split,
                group_by,
                min_side,
                image_cache,
                snapshot_revision_sha256,
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            rejected.append(
                _reject("malformed_shape", _safe(job), _safe(frame), _safe(shape), str(exc))
            )
            continue
        if "reason" in record:
            rejected.append(record)
        else:
            records.append(record)

    records.sort(key=lambda record: record["crop_id"])
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "class_mapping": {"version": MAPPING_VERSION, "classes": list(CLASSES)},
        "input_size": INPUT_SIZE,
        "data_origin": data_origin,
        "data_origin_note": "declared by the operator; not verified by this tool",
        "snapshot": {
            "sha256": snapshot_sha,
            "revision_sha256": snapshot_revision_sha256,
            "taxonomy_version": snapshot.get("taxonomy_version"),
            "guideline_version": snapshot.get("guideline_version"),
            "dataset_id": snapshot.get("dataset_id"),
        },
        "split": {
            "method": "sha256(seed:group) bucket over source groups",
            "group_by": group_by,
            "seed": split.seed,
            "val_fraction": split.val,
            "held_out_fraction": split.held_out,
            "fit_allowed_splits": list(FIT_SPLITS),
            "note": "Technical partition only; not a calibration pass or a reference held-out.",
        },
        "counts": {
            "crops": len(records),
            "by_split": dict(sorted(Counter(r["split"] for r in records).items())),
            "by_class": dict(sorted(Counter(r["class_name"] for r in records).items())),
            "groups_by_split": _groups_by_split(records),
            "rejected_by_reason": dict(sorted(Counter(r["reason"] for r in rejected).items())),
        },
        "leakage_warnings": _leakage_warnings(records),
        "crops": records,
        "rejected": rejected,
    }
    manifest["manifest_sha256"] = sha256_hex(canonical_json(manifest))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dataset-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def _safe(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _process_shape(
    job,
    frame,
    shape,
    snapshot_sha,
    snapshot,
    image_root,
    crops_dir,
    out_dir,  # noqa: PLR0913
    label_map,
    split,
    group_by,
    min_side,
    image_cache,
    revision,
) -> dict[str, Any]:
    """Return a crop record, or a rejection dict (has ``reason``)."""

    outside = shape.get("outside", False)
    if not isinstance(outside, bool):
        raise ValueError("outside must be a boolean")
    if outside:
        return _reject("outside_shape", job, frame, shape)
    points = shape.get("points")
    if isinstance(points, list | tuple) and len(points) != 4:
        return _reject("not_axis_aligned_rectangle", job, frame, shape)
    label_id, box, rotation, source = _parse_shape(shape)
    if rotation != 0.0:
        return _reject("not_axis_aligned_rectangle", job, frame, shape)
    name = label_map.get(label_id)
    if name is None:
        return _reject("label_not_in_label_map", job, frame, shape)
    if name not in CLASS_INDEX:
        return _reject("class_outside_taxonomy", job, frame, shape, name)
    cache_key = (job["cvat_job_id"], frame["frame_index"])
    if cache_key not in image_cache:
        image_cache[cache_key] = _load_frame(image_root, frame)
    loaded = image_cache[cache_key]
    if isinstance(loaded, str):
        return _reject(loaded, job, frame, shape)
    try:
        crop, geometry = letterbox_crop(loaded, tuple(box), min_side=min_side)
    except CropError as exc:
        return _reject(exc.reason, job, frame, shape, str(exc))
    crop_id = (
        f"{snapshot_sha[:12]}-j{job['cvat_job_id']}-f{frame['frame_index']}"
        f"-{source['kind']}{source['id']}"
    )
    group = _group_of(group_by, job, frame)
    assigned = split.assign(group)
    path = crops_dir / assigned / name.replace(" ", "_") / f"{crop_id}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(path, format="PNG")
    return {
        "crop_id": crop_id,
        "path": path.relative_to(out_dir).as_posix(),
        "class_name": name,
        "class_id": CLASS_INDEX[name],
        "split": assigned,
        "source_group": group,
        "crop_sha256": file_sha256(path),
        "pixel_sha256": sha256_hex(crop.tobytes()),
        "provenance": {
            "snapshot_sha256": snapshot_sha,
            "snapshot_revision_sha256": revision,
            "dataset_id": snapshot.get("dataset_id"),
            "cvat_task_id": job["cvat_task_id"],
            "cvat_job_id": job["cvat_job_id"],
            "frame_index": frame["frame_index"],
            "source_frame_id": frame.get("source_frame_id"),
            "frame_media_sha256": frame["media"]["sha256"],
            "annotation_source": source,
            "label_id": label_id,
            "box": box,
            "geometry": geometry.as_dict(),
        },
    }


def _leakage_warnings(records: list[dict[str, Any]]) -> list[str]:
    """Tasks spread over several splits (only possible with group_by job/frame)."""

    splits: dict[int, set[str]] = {}
    for record in records:
        splits.setdefault(record["provenance"]["cvat_task_id"], set()).add(record["split"])
    return [
        f"task {task} spans splits {sorted(found)}"
        for task, found in sorted(splits.items())
        if len(found) > 1
    ]


def _groups_by_split(records: list[dict[str, Any]]) -> dict[str, int]:
    groups: dict[str, set[str]] = {}
    for record in records:
        groups.setdefault(record["split"], set()).add(record["source_group"])
    return {key: len(value) for key, value in sorted(groups.items())}


def _load_frame(image_root: Path, frame: Mapping[str, Any]) -> Image.Image | str:
    """The frame image, or a rejection reason string."""

    media = frame.get("media")
    media = media if isinstance(media, Mapping) else {}
    key = media.get("storage_key")
    expected = media.get("sha256")
    if not isinstance(key, str) or not key:
        return "frame_image_unavailable"
    if not isinstance(expected, str) or not expected:
        return "frame_media_sha256_missing"  # without a recorded hash provenance cannot be proven
    root = image_root.resolve()
    path = (root / key).resolve()
    if root not in path.parents or not path.is_file():
        return "frame_image_unavailable"
    if file_sha256(path) != expected:
        return "frame_image_unavailable"  # not the snapshot's frame: never crop from it
    try:
        with Image.open(path) as handle:
            if handle.width * handle.height > MAX_FRAME_PIXELS:
                return "frame_too_large"
            return handle.convert("RGB")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError, ValueError):
        return "frame_image_unavailable"
