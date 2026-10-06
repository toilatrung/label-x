"""Canonicalization and stable SHA-256 hashes for CVAT job annotations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

HASH_ALGORITHM_VERSION = "cvat-rectangle-v1"
COORDINATE_DECIMALS = 6


@dataclass(frozen=True)
class JobAnnotationDigest:
    job_id: int
    sha256: str
    canonical_json: str
    rectangle_count: int
    ignored_shape_count: int


def _number(value: object, *, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{field} must be numeric")
    return round(float(value), COORDINATE_DECIMALS)


def _integer(value: object, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field} must be an integer")
    return value


def _canonical_attributes(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    attributes: list[dict[str, object]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        attributes.append(
            {
                "spec_id": _integer(raw.get("spec_id"), field="attribute.spec_id"),
                "value": raw.get("value"),
            }
        )
    return sorted(attributes, key=lambda item: _integer(item["spec_id"], field="attribute.spec_id"))


def canonicalize_job_annotations(
    job_id: int, annotations: Mapping[str, object]
) -> JobAnnotationDigest:
    """Canonicalize rectangles and hash the exact UTF-8 JSON representation."""

    raw_shapes = annotations.get("shapes", [])
    if not isinstance(raw_shapes, Sequence) or isinstance(raw_shapes, (str, bytes)):
        raise TypeError("annotations.shapes must be a list")

    rectangles: list[dict[str, object]] = []
    ignored = 0
    for raw in raw_shapes:
        if not isinstance(raw, Mapping):
            ignored += 1
            continue
        if raw.get("type") != "rectangle":
            ignored += 1
            continue
        raw_points = raw.get("points")
        if not isinstance(raw_points, Sequence) or isinstance(raw_points, (str, bytes)):
            raise TypeError("rectangle.points must be a list")
        if len(raw_points) != 4:
            raise ValueError("rectangle.points must contain exactly four coordinates")
        rectangles.append(
            {
                "attributes": _canonical_attributes(raw.get("attributes", [])),
                "cvat_shape_id": _integer(raw.get("id"), field="shape.id"),
                "frame": _integer(raw.get("frame"), field="shape.frame"),
                "label_id": _integer(raw.get("label_id"), field="shape.label_id"),
                "occluded": bool(raw.get("occluded", False)),
                "outside": bool(raw.get("outside", False)),
                "points": [_number(point, field="shape.points") for point in raw_points],
                "rotation": _number(raw.get("rotation", 0), field="shape.rotation"),
                "z_order": _integer(raw.get("z_order", 0), field="shape.z_order"),
            }
        )

    rectangles.sort(
        key=lambda shape: (
            _integer(shape["frame"], field="shape.frame"),
            _integer(shape["cvat_shape_id"], field="shape.id"),
        )
    )
    canonical = {
        "algorithm": HASH_ALGORITHM_VERSION,
        "coordinate_decimals": COORDINATE_DECIMALS,
        "job_id": job_id,
        "shapes": rectangles,
    }
    canonical_json = json.dumps(
        canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return JobAnnotationDigest(
        job_id=job_id,
        sha256=hashlib.sha256(canonical_json.encode("utf-8")).hexdigest(),
        canonical_json=canonical_json,
        rectangle_count=len(rectangles),
        ignored_shape_count=ignored,
    )


def aggregate_job_hash(digests: Sequence[JobAnnotationDigest]) -> str:
    pairs = sorted((digest.job_id, digest.sha256) for digest in digests)
    payload = json.dumps(pairs, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
