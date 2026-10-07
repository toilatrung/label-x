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
    track_rectangle_count: int
    ignored_track_count: int


def _number(value: object, *, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{field} must be numeric")
    rounded = round(float(value), COORDINATE_DECIMALS)
    # JSON distinguishes -0.0 from 0.0 even though geometry does not.
    return 0.0 if rounded == 0 else rounded


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
    raw_tracks = annotations.get("tracks", [])
    if not isinstance(raw_shapes, Sequence) or isinstance(raw_shapes, (str, bytes)):
        raise TypeError("annotations.shapes must be a list")
    if not isinstance(raw_tracks, Sequence) or isinstance(raw_tracks, (str, bytes)):
        raise TypeError("annotations.tracks must be a list")

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
    tracks: list[dict[str, object]] = []
    track_rectangles = 0
    ignored_tracks = 0
    for raw_track in raw_tracks:
        if not isinstance(raw_track, Mapping):
            ignored_tracks += 1
            continue
        raw_keyframes = raw_track.get("shapes", [])
        if not isinstance(raw_keyframes, Sequence) or isinstance(raw_keyframes, (str, bytes)):
            raise TypeError("track.shapes must be a list")
        keyframes: list[dict[str, object]] = []
        unsupported = False
        for raw_keyframe in raw_keyframes:
            if not isinstance(raw_keyframe, Mapping) or raw_keyframe.get("type") != "rectangle":
                unsupported = True
                continue
            raw_points = raw_keyframe.get("points")
            if not isinstance(raw_points, Sequence) or isinstance(raw_points, (str, bytes)):
                raise TypeError("track rectangle.points must be a list")
            if len(raw_points) != 4:
                raise ValueError("track rectangle.points must contain exactly four coordinates")
            keyframes.append(
                {
                    "attributes": _canonical_attributes(raw_keyframe.get("attributes", [])),
                    "frame": _integer(raw_keyframe.get("frame"), field="track.shape.frame"),
                    "occluded": bool(raw_keyframe.get("occluded", False)),
                    "outside": bool(raw_keyframe.get("outside", False)),
                    "points": [_number(point, field="track.shape.points") for point in raw_points],
                    "rotation": _number(
                        raw_keyframe.get("rotation", 0), field="track.shape.rotation"
                    ),
                    "z_order": _integer(
                        raw_keyframe.get("z_order", 0), field="track.shape.z_order"
                    ),
                }
            )
        if unsupported or not keyframes:
            ignored_tracks += 1
        if not keyframes:
            continue
        keyframes.sort(key=lambda shape: _integer(shape["frame"], field="track.shape.frame"))
        tracks.append(
            {
                "attributes": _canonical_attributes(raw_track.get("attributes", [])),
                "cvat_track_id": _integer(raw_track.get("id"), field="track.id"),
                "frame": _integer(raw_track.get("frame", 0), field="track.frame"),
                "label_id": _integer(raw_track.get("label_id"), field="track.label_id"),
                "shapes": keyframes,
            }
        )
        track_rectangles += len(keyframes)
    tracks.sort(key=lambda track: _integer(track["cvat_track_id"], field="track.id"))

    canonical = {
        "algorithm": HASH_ALGORITHM_VERSION,
        "coordinate_decimals": COORDINATE_DECIMALS,
        "job_id": job_id,
        "shapes": rectangles,
        "tracks": tracks,
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
        track_rectangle_count=track_rectangles,
        ignored_track_count=ignored_tracks,
    )


def aggregate_job_hash(digests: Sequence[JobAnnotationDigest]) -> str:
    pairs = sorted((digest.job_id, digest.sha256) for digest in digests)
    payload = json.dumps(pairs, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
