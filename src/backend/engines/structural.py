"""Shared immutable input adapter for deterministic structural engines (T-027)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from engines.interface import EngineUnitRef, FrameKey, ObjectRef


@dataclass(frozen=True, order=True)
class AnnotationAttribute:
    """One normalized CVAT attribute value."""

    spec_id: int
    value: str


@dataclass(frozen=True)
class StructuralAnnotation:
    """Snapshot fields consumed by Schema/Taxonomy and Geometry."""

    annotation_id: str
    label_id: int
    attributes: tuple[AnnotationAttribute, ...]
    x1: float
    y1: float
    x2: float
    y2: float
    image_width: int
    image_height: int
    outside: bool = False

    @property
    def object_ref(self) -> ObjectRef:
        return ObjectRef(namespace="cvat_shape", id=self.annotation_id)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)


@dataclass(frozen=True)
class StructuralFrame:
    """All structural annotations for one immutable snapshot frame."""

    width: int
    height: int
    annotations: tuple[StructuralAnnotation, ...]


def structural_frames_from_snapshot(
    snapshot: Mapping[str, Any],
) -> dict[FrameKey, StructuralFrame]:
    """Adapt a T-020 ``labelx.snapshot.v1`` payload without I/O or mutation."""
    if snapshot.get("schema_version") != "labelx.snapshot.v1":
        raise ValueError("unsupported normalized snapshot schema_version")

    frames: dict[FrameKey, StructuralFrame] = {}
    for job in snapshot.get("jobs", ()):
        task_id = _required_int(job, "cvat_task_id")
        for frame in job.get("frames", ()):
            frame_key = FrameKey(
                cvat_task_id=task_id,
                frame_number=_required_int(frame, "frame_index"),
            )
            if frame_key in frames:
                raise ValueError(f"duplicate normalized frame: {frame_key}")
            width = _required_int(frame, "width")
            height = _required_int(frame, "height")
            annotations: list[StructuralAnnotation] = []
            seen_annotation_ids: set[str] = set()
            for shape in frame.get("shapes", ()):
                source = shape.get("source")
                if not isinstance(source, Mapping) or source.get("id") is None:
                    raise ValueError("normalized shape must have source.id")
                points = shape.get("points")
                if not isinstance(points, list | tuple) or len(points) != 4:
                    raise ValueError("normalized shape points must contain four coordinates")
                annotation_id = str(source["id"])
                if annotation_id in seen_annotation_ids:
                    raise ValueError(
                        f"duplicate normalized annotation id in frame: {annotation_id}"
                    )
                seen_annotation_ids.add(annotation_id)
                raw_attributes = shape.get("attributes", ())
                attributes = tuple(
                    sorted(
                        (
                            AnnotationAttribute(
                                spec_id=_required_int(attribute, "spec_id"),
                                value=str(attribute.get("value", "")),
                            )
                            for attribute in raw_attributes
                        ),
                        key=lambda attribute: (attribute.spec_id, attribute.value),
                    )
                )
                annotations.append(
                    StructuralAnnotation(
                        annotation_id=annotation_id,
                        label_id=_required_int(shape, "label_id"),
                        attributes=attributes,
                        x1=float(points[0]),
                        y1=float(points[1]),
                        x2=float(points[2]),
                        y2=float(points[3]),
                        image_width=width,
                        image_height=height,
                        outside=bool(shape.get("outside", False)),
                    )
                )
            frames[frame_key] = StructuralFrame(
                width=width,
                height=height,
                annotations=tuple(
                    sorted(annotations, key=lambda annotation: annotation.annotation_id)
                ),
            )
    return frames


def ordered_frame_units(engine_units: tuple[EngineUnitRef, ...]) -> tuple[EngineUnitRef, ...]:
    """Validate and stably order frame units for reproducible output."""
    if len(set(engine_units)) != len(engine_units):
        raise ValueError("duplicate frame unit in engine input")
    for unit in engine_units:
        if unit.kind != "frame":
            raise ValueError("structural engines only accept frame units")
    return tuple(sorted(engine_units, key=lambda unit: unit.frame))


def frame_for_unit(
    unit: EngineUnitRef,
    frames_by_key: Mapping[FrameKey, StructuralFrame],
) -> StructuralFrame:
    """Resolve a frame unit from immutable snapshot data."""
    try:
        return frames_by_key[unit.frame]
    except KeyError as exc:
        raise ValueError(f"missing snapshot frame for unit {unit}") from exc


def _required_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value
