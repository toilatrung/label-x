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


def iter_candidates(snapshot: Mapping[str, Any]) -> Iterator[tuple[dict, dict, dict]]:
    for job in snapshot.get("jobs", []):
        for frame in job.get("frames", []):
            for shape in frame.get("shapes", []):
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
) -> dict[str, Any]:
    """Write crops under ``out_dir`` and return the manifest (also saved as JSON)."""

    if group_by not in GROUP_KEYS:
        raise DatasetError(f"group_by must be one of {GROUP_KEYS}")
    if snapshot.get("schema_version") != "labelx.snapshot.v1":
        raise DatasetError("snapshot.schema_version must be labelx.snapshot.v1")
    split = split or SplitConfig()
    snapshot_sha = sha256_hex(canonical_json(snapshot))
    crops_dir = out_dir / "crops"
    records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    image_cache: dict[tuple[int, int], Image.Image | None] = {}

    for job, frame, shape in iter_candidates(snapshot):
        if shape.get("outside"):
            rejected.append(_reject("outside_shape", job, frame, shape))
            continue
        points = shape.get("points") or []
        if len(points) != 4 or float(shape.get("rotation") or 0.0) != 0.0:
            rejected.append(_reject("not_axis_aligned_rectangle", job, frame, shape))
            continue
        name = label_map.get(shape.get("label_id"))
        if name is None:
            rejected.append(_reject("label_not_in_label_map", job, frame, shape))
            continue
        if name not in CLASS_INDEX:
            rejected.append(_reject("class_outside_taxonomy", job, frame, shape, name))
            continue
        cache_key = (job["cvat_job_id"], frame["frame_index"])
        if cache_key not in image_cache:
            image_cache[cache_key] = _load_frame(image_root, frame)
        image = image_cache[cache_key]
        if image is None:
            rejected.append(_reject("frame_image_unavailable", job, frame, shape))
            continue
        try:
            crop, geometry = letterbox_crop(image, tuple(points), min_side=min_side)
        except CropError as exc:
            rejected.append(_reject(exc.reason, job, frame, shape, str(exc)))
            continue
        source = shape["source"]
        crop_id = (
            f"{snapshot_sha[:12]}-j{job['cvat_job_id']}-f{frame['frame_index']}"
            f"-{source['kind']}{source['id']}"
        )
        group = _group_of(group_by, job, frame)
        assigned = split.assign(group)
        path = crops_dir / assigned / name.replace(" ", "_") / f"{crop_id}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        crop.save(path, format="PNG")
        records.append(
            {
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
                    "snapshot_revision_sha256": snapshot_revision_sha256,
                    "dataset_id": snapshot.get("dataset_id"),
                    "cvat_task_id": job["cvat_task_id"],
                    "cvat_job_id": job["cvat_job_id"],
                    "frame_index": frame["frame_index"],
                    "source_frame_id": frame.get("source_frame_id"),
                    "frame_media_sha256": (frame.get("media") or {}).get("sha256"),
                    "annotation_source": {"kind": source["kind"], "id": source["id"]},
                    "label_id": shape["label_id"],
                    "box": [float(value) for value in points],
                    "geometry": geometry.as_dict(),
                },
            }
        )

    records.sort(key=lambda record: record["crop_id"])
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "class_mapping": {"version": MAPPING_VERSION, "classes": list(CLASSES)},
        "input_size": INPUT_SIZE,
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
        "crops": records,
        "rejected": rejected,
    }
    manifest["manifest_sha256"] = sha256_hex(canonical_json(manifest))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dataset-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def _groups_by_split(records: list[dict[str, Any]]) -> dict[str, int]:
    groups: dict[str, set[str]] = {}
    for record in records:
        groups.setdefault(record["split"], set()).add(record["source_group"])
    return {key: len(value) for key, value in sorted(groups.items())}


def _load_frame(image_root: Path, frame: Mapping[str, Any]) -> Image.Image | None:
    media = frame.get("media") or {}
    key = media.get("storage_key")
    if not key:
        return None
    root = image_root.resolve()
    path = (root / key).resolve()
    if root not in path.parents or not path.is_file():
        return None
    expected = media.get("sha256")
    if expected and file_sha256(path) != expected:
        return None  # provenance mismatch: never crop from a file that is not the snapshot's frame
    try:
        with Image.open(path) as handle:
            return handle.convert("RGB")
    except (OSError, UnidentifiedImageError):
        return None
