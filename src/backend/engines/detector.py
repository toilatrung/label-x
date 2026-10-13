"""Adapter backend cho Faster R-CNN worker; backend không import torch/MMDetection."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
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


def distribution_evidence(raw: Mapping[str, Any], *, required: bool = False) -> dict[str, Any]:
    """Original ROI probabilities: ten foreground classes followed by background."""
    values = raw.get("class_scores")
    if values is None and not required:
        return {}  # historical detector evidence has no margin; never invent one
    if not isinstance(values, list) or len(values) != 11:
        raise ValueError("detector requires all eleven ROI class scores")
    if any(
        isinstance(v, bool)
        or not isinstance(v, int | float)
        or not math.isfinite(v)
        or not 0 <= v <= 1
        for v in values
    ):
        raise ValueError("detector class scores must be finite probabilities")
    scores = [float(v) for v in values]
    if abs(sum(scores) - 1.0) > 1e-4:
        raise ValueError("detector class scores must sum to one")
    class_id = raw.get("class_id")
    confidence = raw.get("confidence")
    if (
        isinstance(class_id, bool)
        or not isinstance(class_id, int)
        or not 0 <= class_id < 10
        or isinstance(confidence, bool)
        or not isinstance(confidence, int | float)
        or not math.isfinite(confidence)
        or abs(scores[class_id] - confidence) > 1e-4
    ):
        raise ValueError("detector confidence does not match its ROI class score")
    ranked = sorted(range(10), key=lambda i: (-scores[i], i))
    return {
        "class_scores": scores,
        "score": scores[ranked[0]],
        "margin": scores[ranked[0]] - scores[ranked[1]],
        "background_score": scores[10],
        "unknown": scores[10] >= scores[ranked[0]],
        "top3": [
            {"class_id": i, "class_name": BDD100K_DETECTOR_CLASSES[i], "score": scores[i]}
            for i in ranked[:3]
        ],
    }


def _run_worker(frame: dict[str, Any], raw: bytes, model: Mapping[str, Any]) -> dict[str, Any]:
    """One authenticated HTTP adapter; never executes a CLI or follows redirects."""
    url = _required_setting("DETECTOR_WORKER_URL")
    token = _required_setting("DETECTOR_SERVICE_TOKEN")
    parsed = urlsplit(url)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("unsafe detector worker URL")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("remote detector worker requires HTTPS")
    try:
        with httpx.Client(
            timeout=float(getattr(settings, "DETECTOR_TIMEOUT_SECONDS", 120)),
            trust_env=False,
            follow_redirects=False,
        ) as client:
            response = client.post(
                url.rstrip("/") + "/infer",
                json={
                    "frame": frame,
                    "image_base64": base64.b64encode(raw).decode("ascii"),
                    "model_sha256": model["sha256"],
                },
                headers={"Authorization": "Bearer " + token},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise RuntimeError("detector worker request failed") from None
    if not isinstance(payload, dict):
        raise ValueError("detector output must be an object")
    return payload


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
    score_evidence = distribution_evidence(raw)
    stable_id = (
        f"{engine_input.run_id}:{frame.snapshot_job.cvat_task_id}:{frame.frame_index}:{index}"
    )
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
            **score_evidence,
        },
    )


def _candidates_for_frame(
    engine_input: EngineInput,
    frame: SnapshotFrame,
    detections: list[Any],
    *,
    model: dict[str, Any] | None = None,
    label_ids: Mapping[str, int] | None = None,
    routing_thresholds: Mapping[str, Any] | None = None,
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
    from orchestration.routing_policy import RoutingPolicy

    policy = RoutingPolicy.from_config(routing_thresholds)
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
        scores = distribution_evidence(raw)
        predicted_label_id = (label_ids or {}).get(raw["class_name"], raw["class_id"])
        if (
            predicted_label_id != annotation["label_id"]
            or scores.get("unknown") is True
            or (
                scores
                and (
                    scores["score"] < policy.score_threshold
                    or scores["margin"] < policy.margin_threshold
                )
            )
        ):
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
            candidates[-1].evidence["predicted_label_id"] = predicted_label_id
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
    """Verify artifact before HTTP inference, then match immutable snapshot annotations."""
    from runs.models import QCRun
    from snapshots.models import Snapshot

    run = QCRun.objects.select_related("snapshot", "model_artifact", "config_version").get(
        pk=engine_input.run_id, snapshot_id=engine_input.snapshot_id
    )
    if run.snapshot.status != Snapshot.Status.LOCKED or run.model_artifact is None:
        raise DetectorProvenanceError("detector requires a locked snapshot and ModelArtifact")
    artifact = run.model_artifact
    from engines.registration import taxonomy_from_params

    engine_configs = run.config_version.engines or (run.config_version.payload or {}).get(
        "engines", {}
    )
    taxonomy = taxonomy_from_params(
        engine_configs.get("schema", {}).get("params", {}),
        expected_version=run.snapshot.taxonomy_version,
    )
    labels = {label.name: label.label_id for label in taxonomy.labels}
    if set(labels) != set(BDD100K_DETECTOR_CLASSES) or len(labels) != 10:
        raise DetectorProvenanceError("snapshot taxonomy must match the verified ten-class mapping")
    artifact_row = {
        "model_artifact__checksum": artifact.checksum,
        "model_artifact__version": artifact.version,
        "model_artifact__class_mapping_version": artifact.class_mapping_version,
        "model_artifact__class_mapping": artifact.class_mapping,
    }
    # Preflight uses the same verify_artifact implementation as PR #315.
    model = verify_artifact(
        {
            "sha256": artifact.checksum,
            "version": artifact.version,
            "class_mapping_version": artifact.class_mapping_version,
        },
        artifact_row,
    )
    candidates: list[Candidate] = []
    storage = storages["snapshots"]
    for unit in sorted(engine_input.units, key=lambda u: u.frame):
        frames = list(
            SnapshotFrame.objects.filter(
                snapshot_job__snapshot_id=engine_input.snapshot_id,
                snapshot_job__cvat_task_id=unit.frame.cvat_task_id,
                frame_index=unit.frame.frame_number,
            )
            .select_related("snapshot_job")
            .order_by("pk")
        )
        if not frames:
            raise ValueError("detector shard missing snapshot frame")
        frame = frames[0]
        if any(
            (f.media_sha256, f.shapes, f.width, f.height)
            != (frame.media_sha256, frame.shapes, frame.width, frame.height)
            for f in frames
        ):
            raise ValueError("ambiguous snapshot frame across jobs")
        if not 0 < frame.media_size_bytes <= 50 * 1024 * 1024:
            raise ValueError("detector frame exceeds byte limit")
        with storage.open(frame.media_storage_key, "rb") as source:
            raw = source.read(50 * 1024 * 1024 + 1)
        if (
            len(raw) != frame.media_size_bytes
            or hashlib.sha256(raw).hexdigest() != frame.media_sha256
        ):
            raise ValueError("detector media integrity mismatch")
        identity = {
            "snapshot_id": engine_input.snapshot_id,
            "snapshot_revision": run.snapshot.revision_sha256,
            "cvat_task_id": unit.frame.cvat_task_id,
            "frame_number": unit.frame.frame_number,
            "media_sha256": frame.media_sha256,
            "width": frame.width,
            "height": frame.height,
        }
        payload = _run_worker(identity, raw, model)
        if (
            payload.get("schema_version") != "labelx.detector.frame.v1"
            or payload.get("frame") != identity
            or payload.get("model_sha256") != model["sha256"]
            or payload.get("classes") != list(BDD100K_DETECTOR_CLASSES)
            or payload.get("class_mapping_version") != model["class_mapping_version"]
        ):
            raise DetectorProvenanceError("detector output provenance/schema mismatch")
        verify_artifact(payload.get("model"), artifact_row)
        detections = payload.get("detections")
        if not isinstance(detections, list):
            raise ValueError("detector output missing detections")
        for detection in detections:
            if not isinstance(detection, dict):
                raise ValueError("detector detection must be an object")
            distribution_evidence(detection, required=True)
        candidates.extend(
            _candidates_for_frame(
                engine_input,
                frame,
                detections,
                model=model,
                label_ids=labels,
                routing_thresholds=(run.config_version.thresholds or {}).get(
                    "classification_routing"
                ),
            )
        )
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
