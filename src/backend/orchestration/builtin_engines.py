"""Engine có sẵn cắm vào registry: duplicate/overlap (T-028) đọc annotation từ snapshot."""

from __future__ import annotations

from collections import defaultdict

from engines.duplicate_overlap import (
    DUPLICATE_OVERLAP_DESCRIPTOR,
    Annotation,
    run_duplicate_overlap_engine,
)
from engines.interface import EngineInput, EngineOutput, FrameKey
from orchestration.registry import EngineRegistry
from snapshots.models import SnapshotFrame


def load_annotations(engine_input: EngineInput) -> dict[FrameKey, list[Annotation]]:
    wanted: dict[int, set[int]] = defaultdict(set)
    for unit in engine_input.units:
        wanted[unit.frame.cvat_task_id].add(unit.frame.frame_number)
    result: dict[FrameKey, list[Annotation]] = {u.frame: [] for u in engine_input.units}
    for task_id, frames in wanted.items():
        rows = (
            SnapshotFrame.objects.filter(
                snapshot_job__snapshot_id=engine_input.snapshot_id,
                snapshot_job__cvat_task_id=task_id,
                frame_index__in=frames,
            )
            .select_related("snapshot_job")
            .order_by("frame_index", "snapshot_job__cvat_job_id", "id")
        )
        annotations_by_key: dict[FrameKey, dict[str, Annotation]] = defaultdict(dict)
        for row in rows:
            key = FrameKey(task_id, row.frame_index)
            for shape in row.shapes:
                x1, y1, x2, y2 = shape["points"]
                source = shape["source"]
                annotation = Annotation(
                    annotation_id=f"{source['kind']}:{source['id']}",
                    label=str(shape["label_id"]),
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                    ignored=bool(shape.get("outside", False)),
                )
                annotations_by_key[key].setdefault(annotation.annotation_id, annotation)
        for key, annotations_for_frame in annotations_by_key.items():
            result[key] = [annotations_for_frame[item] for item in sorted(annotations_for_frame)]
    return result


def run_duplicate(engine_input: EngineInput) -> EngineOutput:
    return run_duplicate_overlap_engine(engine_input, load_annotations(engine_input))


def register_builtin_engines(target: EngineRegistry) -> None:
    descriptor = DUPLICATE_OVERLAP_DESCRIPTOR
    if not any(d.name == descriptor.name for d in target.descriptors()):
        target.register(descriptor, run_duplicate)
