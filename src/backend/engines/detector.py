"""Adapter backend cho Faster R-CNN worker; backend không import torch/MMDetection."""

from __future__ import annotations

import json
import math
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.files.storage import storages

from engines.interface import (
    Anchor,
    Candidate,
    EngineDescriptor,
    EngineInput,
    EngineOutput,
    EngineUnitOutcome,
    EngineUnitResult,
    FrameKey,
    ObjectRef,
)
from engines.matching import BoundingBox, match_one_to_one
from snapshots.models import SnapshotFrame

DETECTOR_ENGINE_NAME = "detector"
DETECTOR_DESCRIPTOR = EngineDescriptor(
    name=DETECTOR_ENGINE_NAME,
    version="1.0.0",
    unit="frame",
    required=True,
    needs_model=True,
    needs_reference=False,
    applicability_version="1.0.0",
)


def _required_setting(name: str) -> str:
    value = str(getattr(settings, name, "")).strip()
    if not value:
        raise ValueError(f"{name} chưa được cấu hình")
    return value


def _run_worker(input_dir: Path, output: Path, engine_input: EngineInput) -> dict[str, Any]:
    params = engine_input.config.params
    command = str(getattr(settings, "DETECTOR_COMMAND", "labelx-detector"))
    args = [
        command,
        "infer",
        "--input-dir",
        str(input_dir),
        "--output",
        str(output),
        "--checkpoint",
        _required_setting("DETECTOR_CHECKPOINT_PATH"),
        "--manifest",
        _required_setting("DETECTOR_MANIFEST_PATH"),
        "--config",
        _required_setting("DETECTOR_CONFIG_PATH"),
        "--device",
        str(params.get("device", getattr(settings, "DETECTOR_DEVICE", "cuda:0"))),
        "--batch-size",
        str(int(params.get("batch_size", 1))),
        "--score-threshold",
        str(float(params.get("score_threshold", 0.05))),
    ]
    timeout = float(getattr(settings, "DETECTOR_TIMEOUT_SECONDS", 1800))
    completed = subprocess.run(  # noqa: S603 - argv only; no shell, command is trusted setting
        args, capture_output=True, text=True, timeout=timeout, check=False
    )
    if completed.returncode:
        raise RuntimeError(f"detector worker failed (exit={completed.returncode})")
    try:
        payload = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("detector worker không trả JSON hợp lệ") from exc
    if not isinstance(payload, dict):
        raise ValueError("detector worker output phải là object")
    return payload


def _detection_candidate(
    engine_input: EngineInput,
    frame: SnapshotFrame,
    index: int,
    raw: Any,
    *,
    family: str = "E1",
    annotation: dict[str, Any] | None = None,
    iou: float | None = None,
    model: dict[str, Any] | None = None,
) -> Candidate:
    if not isinstance(raw, dict):
        raise ValueError("detection phải là object")
    bbox = raw.get("bbox_xyxy")
    class_id = raw.get("class_id")
    class_name = raw.get("class_name")
    confidence = raw.get("confidence")
    if (
        not isinstance(bbox, list)
        or len(bbox) != 4
        or any(
            isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v)
            for v in bbox
        )
        or isinstance(class_id, bool)
        or not isinstance(class_id, int)
        or not isinstance(class_name, str)
        or isinstance(confidence, bool)
        or not isinstance(confidence, int | float)
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        raise ValueError("detection có bbox/class/confidence không hợp lệ")
    stable_id = f"{frame.snapshot_job.cvat_task_id}:{frame.frame_index}:{index}"
    objects = [ObjectRef(namespace="detector", id=stable_id)]
    annotated_class_id: int | None = None
    if annotation is not None:
        source = annotation.get("source")
        if not isinstance(source, dict) or "kind" not in source or "id" not in source:
            raise ValueError("annotation ghép detector thiếu source")
        objects.append(ObjectRef(namespace=str(source["kind"]), id=str(source["id"])))
        annotated_class_id = annotation.get("label_id")
        if isinstance(annotated_class_id, bool) or not isinstance(annotated_class_id, int):
            raise ValueError("annotation ghép detector có label_id không hợp lệ")
    return Candidate(
        engine=engine_input.engine,
        engine_version=engine_input.engine_version,
        family=family,
        frame=FrameKey(frame.snapshot_job.cvat_task_id, frame.frame_index),
        anchor=Anchor(
            kind="detector_box",
            objects=tuple(objects),
            policy_version="detector-candidate-v1",
            rule_id="faster-rcnn-detection",
        ),
        evidence={
            "engine": DETECTOR_ENGINE_NAME,
            "prediction_bbox": [float(v) for v in bbox],
            "class_id": class_id,
            "class_name": class_name,
            "prediction_class": class_name,
            "confidence": float(confidence),
            "annotated_class_id": annotated_class_id,
            "iou": iou,
            "model_version": (model or {}).get("version"),
            "checkpoint_sha256": (model or {}).get("sha256"),
            "class_mapping_version": (model or {}).get("class_mapping_version"),
        },
    )


def _candidates_for_frame(
    engine_input: EngineInput,
    frame: SnapshotFrame,
    detections: list[Any],
    *,
    model: dict[str, Any] | None = None,
) -> list[Candidate]:
    """E1 = detection không ghép annotation; E2 = ghép hình học nhưng sai lớp."""
    detector_boxes: list[BoundingBox] = []
    raw_by_id: dict[str, tuple[int, Any]] = {}
    for index, raw in enumerate(detections):
        # Dùng cùng validation với candidate để từ chối output worker sai schema.
        probe = _detection_candidate(engine_input, frame, index, raw, model=model)
        bbox = probe.evidence["prediction_bbox"]
        box_id = f"det:{index}"
        detector_boxes.append(
            BoundingBox(
                box_id,
                str(probe.evidence["class_id"]),
                bbox[0],
                bbox[1],
                bbox[2],
                bbox[3],
                score=probe.evidence["confidence"],
            )
        )
        raw_by_id[box_id] = (index, raw)

    annotation_boxes: list[BoundingBox] = []
    annotations: dict[str, dict[str, Any]] = {}
    for index, shape in enumerate(frame.shapes):
        if not isinstance(shape, dict) or shape.get("outside"):
            continue
        points = shape.get("points")
        label_id = shape.get("label_id")
        if (
            not isinstance(points, list)
            or len(points) != 4
            or isinstance(label_id, bool)
            or not isinstance(label_id, int)
        ):
            continue
        ann_id = f"ann:{index}"
        annotation_boxes.append(BoundingBox(ann_id, str(label_id), *points))
        annotations[ann_id] = shape

    params = engine_input.config.params
    result = match_one_to_one(
        detector_boxes,
        annotation_boxes,
        tau_m=float(params.get("match_iou_threshold", 0.5)),
        tau_amb=float(params.get("ambiguous_iou_threshold", 0.3)),
    )
    candidates = [
        _detection_candidate(engine_input, frame, *raw_by_id[box_id], model=model)
        for box_id in result.unmatched_left
    ]
    for pair in result.matches:
        det_index, raw = raw_by_id[pair.left_id]
        annotation = annotations[pair.right_id]
        if raw["class_id"] != annotation["label_id"]:
            candidates.append(
                _detection_candidate(
                    engine_input,
                    frame,
                    det_index,
                    raw,
                    family="E2",
                    annotation=annotation,
                    iou=pair.iou,
                    model=model,
                )
            )
    return candidates


def run_detector_engine(engine_input: EngineInput) -> EngineOutput:
    """Tải ảnh shard, gọi CLI Faster R-CNN và đổi từng detection thành Candidate."""
    wanted = {
        (unit.frame.cvat_task_id, unit.frame.frame_number): unit for unit in engine_input.units
    }
    frames = list(
        SnapshotFrame.objects.filter(
            snapshot_job__snapshot_id=engine_input.snapshot_id,
            snapshot_job__cvat_task_id__in={key[0] for key in wanted},
            frame_index__in={key[1] for key in wanted},
        ).select_related("snapshot_job")
    )
    by_key = {(frame.snapshot_job.cvat_task_id, frame.frame_index): frame for frame in frames}
    if set(by_key) != set(wanted):
        raise ValueError("detector shard thiếu frame trong snapshot")

    with tempfile.TemporaryDirectory(prefix="labelx-detector-") as directory:
        root = Path(directory)
        input_dir = root / "input"
        input_dir.mkdir()
        output = root / "predictions.json"
        path_to_frame: dict[str, SnapshotFrame] = {}
        storage = storages["snapshots"]
        for key in sorted(wanted):
            frame = by_key[key]
            suffix = Path(frame.file_name).suffix.lower() or ".jpg"
            name = f"{key[0]}-{key[1]}{suffix}"
            with storage.open(frame.media_storage_key, "rb") as source:
                (input_dir / name).write_bytes(source.read())
            path_to_frame[name] = frame
        payload = _run_worker(input_dir, output, engine_input)

    from runs.models import QCRun

    artifact = (
        QCRun.objects.filter(pk=engine_input.run_id)
        .values(
            "model_artifact__checksum",
            "model_artifact__version",
            "model_artifact__class_mapping_version",
        )
        .first()
    )
    model = payload.get("model")
    if (
        not artifact
        or not isinstance(model, dict)
        or model.get("sha256") != artifact["model_artifact__checksum"]
        or model.get("version") != artifact["model_artifact__version"]
        or model.get("class_mapping_version") != artifact["model_artifact__class_mapping_version"]
    ):
        raise ValueError("detector output không khớp model artifact của run")

    images = payload.get("images")
    if not isinstance(images, list):
        raise ValueError("detector output thiếu images")
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for image in images:
        if not isinstance(image, dict) or image.get("path") not in path_to_frame:
            raise ValueError("detector output chứa image không thuộc shard")
        path = str(image["path"])
        if path in seen:
            raise ValueError("detector output lặp image")
        seen.add(path)
        detections = image.get("detections")
        if not isinstance(detections, list):
            raise ValueError("detector output thiếu detections")
        candidates.extend(
            _candidates_for_frame(engine_input, path_to_frame[path], detections, model=model)
        )
    if seen != set(path_to_frame):
        raise ValueError("detector output không phủ đủ shard")
    return EngineOutput(
        idempotency_key=engine_input.idempotency_key,
        engine=engine_input.engine,
        engine_version=engine_input.engine_version,
        candidates=tuple(candidates),
        unit_results=tuple(
            EngineUnitResult(unit, EngineUnitOutcome.COMPLETED.value, 1)
            for unit in engine_input.units
        ),
    )
