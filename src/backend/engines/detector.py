"""Adapter backend cho Faster R-CNN worker; backend không import torch/MMDetection."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import tempfile
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
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
from engines.worker_adapter.client import request_json
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


# Taxonomy BDD100K 10 lớp; chỉ số = class_id mà worker trả (khớp manifest class_mapping.classes).
BDD100K_DETECTOR_CLASSES: tuple[str, ...] = (
    "pedestrian",
    "rider",
    "car",
    "truck",
    "bus",
    "train",
    "motorcycle",
    "bicycle",
    "traffic light",
    "traffic sign",
)
MANIFEST_SCHEMA_VERSION = "labelx.detector.model.v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")

MATCHED = "matched"
UNMATCHED_DETECTION = "unmatched_detection"
UNMATCHED_ANNOTATION = "unmatched_annotation"


class DetectorProvenanceError(ValueError):
    """Manifest/checksum/class-map không xác minh được; engine fail closed, không tạo candidate."""


@lru_cache(maxsize=4)
def _checkpoint_sha256(path: str, size: int, mtime_ns: int) -> str:
    # size/mtime chỉ là khoá cache; mỗi khi file đổi sẽ băm lại.
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifact(model: Any, artifact: Mapping[str, Any] | None) -> dict[str, Any]:
    """Xác minh đồng thời manifest, checksum checkpoint và class map; sai/thiếu → raise.

    Nguồn tin cậy duy nhất là cấu hình server (đường dẫn setting) và ModelArtifact đã đăng ký của
    run; không nhận đường dẫn hay lệnh từ request. Trả provenance đã xác minh để ghi vào evidence.
    """
    if not artifact or not isinstance(model, dict):
        raise DetectorProvenanceError("detector thiếu ModelArtifact hoặc provenance của worker")
    try:
        manifest = json.loads(
            Path(_required_setting("DETECTOR_MANIFEST_PATH")).read_text(encoding="utf-8")
        )
        manifest_model = manifest["model"]
        mapping = manifest["class_mapping"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DetectorProvenanceError("manifest detector thiếu hoặc không hợp lệ") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise DetectorProvenanceError("manifest detector sai schema_version")
    if not isinstance(manifest_model, dict) or not isinstance(mapping, dict):
        raise DetectorProvenanceError("manifest detector sai cấu trúc")
    checksum = str(manifest_model.get("sha256") or "")
    if not _SHA256.fullmatch(checksum):
        raise DetectorProvenanceError("manifest detector chưa đóng băng checkpoint sha256")
    if tuple(mapping.get("classes") or ()) != BDD100K_DETECTOR_CLASSES:
        raise DetectorProvenanceError("class map manifest không khớp taxonomy BDD100K 10 lớp")
    class_map_version = str(mapping.get("version") or "")
    registered = artifact["model_artifact__class_mapping"]
    if registered and (
        not isinstance(registered, dict)
        or tuple(registered.get("classes") or ()) != BDD100K_DETECTOR_CLASSES
    ):
        raise DetectorProvenanceError("class map của ModelArtifact không khớp manifest")
    try:
        checkpoint = Path(_required_setting("DETECTOR_CHECKPOINT_PATH"))
        stat = checkpoint.stat()
        actual = _checkpoint_sha256(str(checkpoint), stat.st_size, stat.st_mtime_ns)
    except OSError as exc:
        raise DetectorProvenanceError("không đọc được checkpoint detector") from exc
    expected = {
        "sha256": artifact["model_artifact__checksum"],
        "version": artifact["model_artifact__version"],
        "class_mapping_version": artifact["model_artifact__class_mapping_version"],
    }
    if not (actual == checksum == expected["sha256"] == model.get("sha256")):
        raise DetectorProvenanceError("checksum checkpoint không khớp manifest/ModelArtifact")
    if (
        manifest_model.get("version") != expected["version"]
        or model.get("version") != expected["version"]
        or class_map_version != expected["class_mapping_version"]
        or model.get("class_mapping_version") != expected["class_mapping_version"]
    ):
        raise DetectorProvenanceError("version/class map worker không khớp artifact của run")
    return {
        "version": expected["version"],
        "sha256": actual,
        "class_mapping_version": class_map_version,
        "verified": True,
    }


def _required_setting(name: str) -> str:
    value = str(getattr(settings, name, "")).strip()
    if not value:
        raise ValueError(f"{name} chưa được cấu hình")
    return value


def _run_worker(input_dir: Path, engine_input: EngineInput) -> dict[str, Any]:
    """Host Celery sends image bytes, never host paths, to the warm GPU container."""
    params = engine_input.config.params
    from runs.gpu_worker import WorkerUnavailable, config_for_run, probe, request_worker
    from runs.models import QCRun

    remote = config_for_run(engine_input.run_id)
    if remote is None:
        model = registered_model(engine_input.run_id)
    else:
        run = QCRun.objects.select_related("model_artifact").get(pk=engine_input.run_id)
        if run.model_artifact is None:
            raise DetectorProvenanceError("detector run thiếu ModelArtifact")
        readiness = probe(remote, run.model_artifact)
        if readiness["state"] != "ready":
            raise WorkerUnavailable("GPU Worker chưa sẵn sàng cho shard detector.")
        model = readiness["model"]
    images = []
    for path in sorted(input_dir.iterdir()):
        raw = path.read_bytes()
        images.append(
            {
                "path": path.name,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "image_base64": base64.b64encode(raw).decode("ascii"),
            }
        )
    body = {
        "model_sha256": model["sha256"],
        "images": images,
        "batch_size": int(params.get("batch_size", 1)),
        "score_threshold": float(params.get("score_threshold", 0.05)),
    }
    payload = (
        request_worker(remote, "/infer", body)
        if remote is not None
        else worker_request("POST", "/infer", body)
    )
    if payload.get("schema_version") != "labelx.detector.predictions.v1":
        raise ValueError("detector worker prediction schema mismatch")
    verified_run_model(payload, engine_input.run_id)
    return payload


def worker_request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = _required_setting("DETECTOR_WORKER_URL")
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("unsafe detector worker URL")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("remote detector worker requires HTTPS/mTLS")
    token = _required_setting("DETECTOR_SERVICE_TOKEN")
    if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("detector service token must be at least 32 ASCII characters")
    try:
        result = request_json(
            method,
            url.rstrip("/") + path,
            token=token,
            timeout=settings.DETECTOR_TIMEOUT_SECONDS,
            body=body,
        )
    except (httpx.HTTPError, ValueError):
        raise RuntimeError("detector worker unavailable or invalid response") from None
    if not isinstance(result, dict):
        raise ValueError("detector worker response must be an object")
    return result


def artifact_for_run(run_id: int) -> Mapping[str, Any] | None:
    from runs.models import QCRun

    return (
        QCRun.objects.filter(pk=run_id)
        .values(
            "model_artifact__checksum",
            "model_artifact__version",
            "model_artifact__class_mapping_version",
            "model_artifact__class_mapping",
        )
        .first()
    )


def verified_run_model(payload: dict[str, Any], run_id: int) -> dict[str, Any]:
    from runs.gpu_worker import config_for_run, verify_remote
    from runs.models import QCRun

    if config_for_run(run_id) is not None:
        run = QCRun.objects.select_related("model_artifact").get(pk=run_id)
        if run.model_artifact is None:
            raise DetectorProvenanceError("detector run thiếu artifact")
        return verify_remote(payload, run.model_artifact)
    return verify_artifact(payload.get("model"), artifact_for_run(run_id))


def registered_model(run_id: int) -> dict[str, Any]:
    artifact = artifact_for_run(run_id)
    if not artifact:
        raise DetectorProvenanceError("detector run does not exist")
    model = {
        "sha256": artifact["model_artifact__checksum"],
        "version": artifact["model_artifact__version"],
        "class_mapping_version": artifact["model_artifact__class_mapping_version"],
    }
    return verify_artifact(model, artifact)


def _detection_candidate(
    engine_input: EngineInput,
    frame: SnapshotFrame,
    index: int,
    raw: Any,
    *,
    family: str = "E1",
    match_status: str = UNMATCHED_DETECTION,
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
        or not 0 <= class_id < len(BDD100K_DETECTOR_CLASSES)
        or class_name != BDD100K_DETECTOR_CLASSES[class_id]
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
            "source": "detector",
            "prediction_bbox": [float(v) for v in bbox],
            "class_id": class_id,
            "class_name": class_name,
            "prediction_class": class_name,
            "confidence": float(confidence),
            "match_status": match_status,
            "annotated_class_id": annotated_class_id,
            "iou": iou,
            "model_version": (model or {}).get("version"),
            "checkpoint_sha256": (model or {}).get("sha256"),
            "class_mapping_version": (model or {}).get("class_mapping_version"),
            "artifact_verified": (model or {}).get("verified") is True,
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
                    match_status=MATCHED,
                    annotation=annotation,
                    iou=pair.iou,
                    model=model,
                )
            )
    for ann_id in result.unmatched_right:
        candidates.append(
            _annotation_candidate(engine_input, frame, annotations[ann_id], model=model)
        )
    return candidates


def _annotation_candidate(
    engine_input: EngineInput,
    frame: SnapshotFrame,
    annotation: dict[str, Any],
    *,
    model: dict[str, Any] | None,
) -> Candidate:
    """Annotation không có detection ghép: không có prediction, chỉ bằng chứng phía annotation."""
    source = annotation.get("source")
    if not isinstance(source, dict) or "kind" not in source or "id" not in source:
        raise ValueError("annotation không ghép được thiếu source")
    return Candidate(
        engine=engine_input.engine,
        engine_version=engine_input.engine_version,
        family="E3",
        frame=FrameKey(frame.snapshot_job.cvat_task_id, frame.frame_index),
        anchor=Anchor(
            kind="annotation_box",
            objects=(ObjectRef(namespace=str(source["kind"]), id=str(source["id"])),),
            policy_version="detector-candidate-v1",
            rule_id="faster-rcnn-unmatched-annotation",
        ),
        evidence={
            "engine": DETECTOR_ENGINE_NAME,
            "source": "detector",
            "match_status": UNMATCHED_ANNOTATION,
            "annotation_bbox": [float(v) for v in annotation["points"]],
            "annotated_class_id": annotation["label_id"],
            "model_version": (model or {}).get("version"),
            "checkpoint_sha256": (model or {}).get("sha256"),
            "class_mapping_version": (model or {}).get("class_mapping_version"),
            "artifact_verified": (model or {}).get("verified") is True,
        },
    )


def run_detector_engine(engine_input: EngineInput) -> EngineOutput:
    """Tải ảnh shard, gọi HTTP Faster R-CNN và đổi từng detection thành Candidate."""
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
        path_to_frame: dict[str, SnapshotFrame] = {}
        storage = storages["snapshots"]
        for key in sorted(wanted):
            frame = by_key[key]
            suffix = Path(frame.file_name).suffix.lower() or ".jpg"
            name = f"{key[0]}-{key[1]}{suffix}"
            with storage.open(frame.media_storage_key, "rb") as source:
                raw = source.read()
            if hashlib.sha256(raw).hexdigest() != frame.media_sha256:
                raise ValueError("detector media không khớp snapshot đã khoá")
            (input_dir / name).write_bytes(raw)
            path_to_frame[name] = frame
        payload = _run_worker(input_dir, engine_input)

    model = verified_run_model(payload, engine_input.run_id)

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
