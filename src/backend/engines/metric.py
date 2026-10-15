"""Detector Precision/Recall against checksum-verified, locked GT (BLOCKER-033)."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, cast

from django.core.files.storage import storages

from engines.detector import BDD100K_DETECTOR_CLASSES, _detection_candidate, predict_frames
from engines.interface import (
    EngineDescriptor,
    EngineInput,
    EngineOutput,
    EngineUnitResult,
    FrameKey,
    NotCheckedEngineUnitResult,
)
from engines.matching import ALGORITHM_VERSION, BoundingBox, match_one_to_one
from engines.structural import ordered_frame_units
from runs.models import Reference

METRIC_DESCRIPTOR = EngineDescriptor(
    name="metric",
    version="1.0.0",
    unit="frame",
    required=False,
    needs_model=True,
    needs_reference=True,
    applicability_version="1.0.0",
)


@dataclass(frozen=True)
class MetricUnitResult(EngineUnitResult):
    details: dict[str, Any]


def count_detections(
    truth: Sequence[BoundingBox], predictions: Sequence[BoundingBox], *, tau_m: float
) -> dict[str, dict[str, int | float | None]]:
    """Geometry-first one-to-one matching; wrong class contributes both FP and FN."""
    matched = match_one_to_one(truth, predictions, tau_m=tau_m, tau_amb=tau_m)
    gt = {box.id: box for box in truth if not box.ignored}
    pred = {box.id: box for box in predictions if not box.ignored}
    counts: dict[str, dict[str, int]] = {
        label: {"tp": 0, "fp": 0, "fn": 0}
        for label in sorted({b.label for b in (*gt.values(), *pred.values())})
    }
    for pair in matched.matches:
        expected, observed = gt[pair.left_id].label, pred[pair.right_id].label
        if expected == observed:
            counts[expected]["tp"] += 1
        else:
            counts[expected]["fn"] += 1
            counts[observed]["fp"] += 1
    for box_id in matched.unmatched_left:
        counts[gt[box_id].label]["fn"] += 1
    for box_id in matched.unmatched_right:
        counts[pred[box_id].label]["fp"] += 1
    return _ratios(counts)


def _ratios(counts: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        label: {
            **row,
            "precision": row["tp"] / (row["tp"] + row["fp"]) if row["tp"] + row["fp"] else None,
            "recall": row["tp"] / (row["tp"] + row["fn"]) if row["tp"] + row["fn"] else None,
        }
        for label, row in sorted(counts.items())
    }


def summarize_metric_details(details: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Pool counts across frames/shards, rather than averaging frame ratios."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    slices: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    )
    for frame in details:
        for label, row in frame["classes"].items():
            for key in ("tp", "fp", "fn"):
                counts[label][key] += row[key]
                for name in frame["slices"]:
                    slices[name][label][key] += row[key]
    return {
        "frames": len(details),
        "classes": _ratios(counts),
        "slices": {name: _ratios(rows) for name, rows in sorted(slices.items())},
    }


def _gt_frames(reference: Reference) -> dict[FrameKey, dict[str, Any]]:
    # gt_source is a key in the configured snapshots bucket, never an arbitrary URL/path.
    with storages["snapshots"].open(reference.gt_source, "rb") as source:
        raw = source.read()
    if hashlib.sha256(raw).hexdigest() != reference.gt_checksum:
        raise ValueError("metric GT checksum mismatch")
    return parse_gt_frames(raw, reference.snapshot_id, reference.mapping_version)


def parse_gt_frames(
    raw: bytes, snapshot_id: int, mapping_version: str
) -> dict[FrameKey, dict[str, Any]]:
    """Shared validation for uploads and runtime reads."""
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("File Ground Truth phải là JSON hợp lệ (UTF-8).") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != "labelx.metric.gt.v1"
        or not isinstance(payload.get("frames"), list)
    ):
        raise ValueError(
            "Ground Truth phải có schema_version labelx.metric.gt.v1 và danh sách frames."
        )
    if payload.get("snapshot_id") != snapshot_id:
        source_id = payload.get("snapshot_id")
        source = f"Snapshot #{source_id}" if type(source_id) is int else "Snapshot không xác định"
        raise ValueError(
            f"File Ground Truth thuộc {source}, nhưng bạn đang chọn Snapshot #{snapshot_id}. "
            "Hãy chọn đúng Snapshot của file hoặc upload Ground Truth "
            "tương ứng với Snapshot đang chọn. "
            "Không chỉ đổi snapshot_id trong file vì task, frame và ảnh cũng phải khớp."
        )
    if payload.get("mapping_version") != mapping_version:
        raise ValueError("Mapping class trong file Ground Truth không khớp mapping đã chọn.")
    frames: dict[FrameKey, dict[str, Any]] = {}
    for frame in payload["frames"]:
        if not isinstance(frame, dict):
            raise ValueError("metric GT frame must be an object")
        task, number = frame.get("cvat_task_id"), frame.get("frame_number")
        if any(type(value) is not int or value < 0 for value in (task, number)):
            raise ValueError("metric GT frame identity must contain non-negative integers")
        key = FrameKey(cast(int, task), cast(int, number))
        if key in frames or not isinstance(frame.get("boxes"), list):
            raise ValueError("metric GT duplicate frame or missing boxes")
        slices = frame.get("slices", [])
        if not isinstance(slices, list) or any(not isinstance(s, str) or not s for s in slices):
            raise ValueError("metric GT slices must contain names")
        frames[key] = frame
    return frames


def _truth_boxes(frame: dict[str, Any], minimum_area: float) -> list[BoundingBox]:
    boxes = []
    for box in frame["boxes"]:
        if not isinstance(box, dict) or box.get("label") not in BDD100K_DETECTOR_CLASSES:
            raise ValueError("metric GT box has an unknown class")
        coordinates = box.get("bbox_xyxy")
        if (
            not isinstance(coordinates, list)
            or len(coordinates) != 4
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in coordinates)
            or type(box.get("ignored", False)) is not bool
        ):
            raise ValueError("metric GT box has invalid coordinates/ignore flag")
        box_id = box.get("id")
        if not isinstance(box_id, str):
            raise ValueError("metric GT box id must be a string")
        item = BoundingBox(
            box_id,
            box["label"],
            coordinates[0],
            coordinates[1],
            coordinates[2],
            coordinates[3],
            ignored=box.get("ignored", False),
        )
        if item.area <= 0:
            raise ValueError("metric GT box must have positive area")
        boxes.append(
            BoundingBox(
                item.id,
                item.label,
                coordinates[0],
                coordinates[1],
                coordinates[2],
                coordinates[3],
                ignored=item.ignored or item.area < minimum_area,
            )
        )
    # Validate IDs even when this frame is outside the current shard.
    match_one_to_one(boxes, [])
    return boxes


def run_metric_engine(engine_input: EngineInput) -> EngineOutput:
    units = ordered_frame_units(engine_input.units)
    reference_id = engine_input.config.params.get("reference_id")
    reference = None
    if type(reference_id) is int:
        reference = Reference.objects.filter(
            pk=reference_id,
            snapshot_id=engine_input.snapshot_id,
            status=Reference.Status.LOCKED,
            locked_at__isnull=False,
            snapshot__status="locked",
        ).first()
    if reference is None:
        return EngineOutput(
            engine_input.idempotency_key,
            engine_input.engine,
            engine_input.engine_version,
            (),
            tuple(NotCheckedEngineUnitResult(u, "not_checked", 1, "no_reference") for u in units),
        )
    if (
        reference.algorithm_version != ALGORITHM_VERSION
        or not math.isfinite(reference.matching_threshold)
        or not 0 <= reference.matching_threshold <= 1
        or not math.isfinite(reference.minimum_area)
        or reference.minimum_area < 0
    ):
        raise ValueError("metric reference matching parameters/version are invalid")
    try:
        frames = _gt_frames(reference)
    except FileNotFoundError:
        return EngineOutput(
            engine_input.idempotency_key,
            engine_input.engine,
            engine_input.engine_version,
            (),
            tuple(NotCheckedEngineUnitResult(u, "not_checked", 1, "no_reference") for u in units),
        )
    truth = {key: _truth_boxes(frame, reference.minimum_area) for key, frame in frames.items()}
    available = tuple(unit for unit in units if unit.frame in truth)
    if not available:
        # Omitted frames are missing GT, unlike an explicit empty boxes list.
        return EngineOutput(
            engine_input.idempotency_key,
            engine_input.engine,
            engine_input.engine_version,
            (),
            tuple(NotCheckedEngineUnitResult(u, "not_checked", 1, "no_reference") for u in units),
        )
    predictions, model = predict_frames(replace(engine_input, units=available))
    if model.get("class_mapping_version") != reference.mapping_version:
        raise ValueError("metric model/reference class mapping mismatch")
    results: list[EngineUnitResult] = []
    for unit in units:
        if unit.frame not in truth:
            results.append(NotCheckedEngineUnitResult(unit, "not_checked", 1, "no_reference"))
            continue
        frame, detections = predictions[unit.frame]
        boxes = []
        for index, raw in enumerate(detections):
            evidence = _detection_candidate(engine_input, frame, index, raw).evidence
            box = BoundingBox(str(index), evidence["class_name"], *evidence["prediction_bbox"])
            if box.area <= 0:
                raise ValueError("metric prediction must have positive area")
            boxes.append(box)
        results.append(
            MetricUnitResult(
                unit,
                "completed",
                1,
                {
                    "classes": count_detections(
                        truth[unit.frame], boxes, tau_m=reference.matching_threshold
                    ),
                    "slices": sorted(set(frames[unit.frame].get("slices", []))),
                    "provenance": {
                        "snapshot_id": engine_input.snapshot_id,
                        "reference_id": reference.pk,
                        "gt_checksum": reference.gt_checksum,
                        "mapping_version": reference.mapping_version,
                        "model_checksum": model["sha256"],
                        "algorithm_version": reference.algorithm_version,
                        "matching_threshold": reference.matching_threshold,
                        "minimum_area": reference.minimum_area,
                    },
                },
            )
        )
    return EngineOutput(
        engine_input.idempotency_key,
        engine_input.engine,
        engine_input.engine_version,
        (),
        tuple(results),
    )
