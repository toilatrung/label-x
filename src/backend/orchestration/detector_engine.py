"""Snapshot -> authenticated warm detector worker -> immutable EngineOutput."""

from __future__ import annotations

import base64
import hashlib
from typing import Any
from urllib.parse import urlsplit

import httpx
from django.conf import settings

from engines.detector import DETECTOR_DESCRIPTOR, match_candidates
from engines.interface import Candidate, EngineInput, EngineOutput, EngineUnitResult
from engines.registration import taxonomy_from_params
from orchestration.registry import EngineRegistry, registry
from runs.models import QCRun
from snapshots.models import Snapshot, SnapshotFrame
from storage.client import ObjectStorage

FROZEN_SHA256 = "ba1be4c41669969ff89083a9ac9355a5fdd81505786d9b5eb3a5126a4d053540"
CLASSES = (
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
MAPPING_VERSION = "bdd100k-det-10-v1"
MAX_FRAME_BYTES = 50 * 1024 * 1024


def artifact_binding(run: QCRun) -> dict[str, str]:
    artifact = run.model_artifact
    if artifact is None or artifact.checksum != FROZEN_SHA256:
        raise ValueError("detector requires the frozen verified model artifact")
    if (
        artifact.class_mapping_version != MAPPING_VERSION
        or not isinstance(artifact.class_mapping, dict)
        or artifact.class_mapping.get("classes") != list(CLASSES)
    ):
        raise ValueError("detector artifact class mapping version mismatch")
    return {
        "model_sha256": artifact.checksum,
        "model_version": artifact.version,
        "class_mapping_version": artifact.class_mapping_version,
    }


def taxonomy_mapping(run: QCRun) -> dict[str, str]:
    engines = run.config_version.engines or (run.config_version.payload or {}).get("engines", {})
    schema = engines.get("schema", {})
    taxonomy = taxonomy_from_params(
        schema.get("params", {}), expected_version=run.snapshot.taxonomy_version
    )
    labels = {label.name: str(label.label_id) for label in taxonomy.labels}
    if (
        len(labels) != len(CLASSES)
        or set(labels) != set(CLASSES)
        or len(set(labels.values())) != len(CLASSES)
    ):
        raise ValueError("detector requires exactly the frozen ten-class taxonomy")
    return labels


class HttpDetector:
    def predict(self, frame: dict[str, Any], raw: bytes) -> dict[str, Any]:
        url = getattr(settings, "DETECTOR_WORKER_URL", "")
        token = getattr(settings, "DETECTOR_SERVICE_TOKEN", "")
        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not token
        ):
            raise ValueError("detector worker URL/token is not configured safely")
        if parsed.scheme == "http" and parsed.hostname not in (
            "127.0.0.1",
            "localhost",
            "detector",
        ):
            raise ValueError("remote detector worker requires HTTPS")
        try:
            with httpx.Client(timeout=120, trust_env=False, follow_redirects=False) as client:
                response = client.post(
                    url.rstrip("/") + "/infer",
                    json={
                        "frame": frame,
                        "image_base64": base64.b64encode(raw).decode("ascii"),
                        "model_sha256": FROZEN_SHA256,
                    },
                    headers={"Authorization": "Bearer " + token},
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                return data
        except (httpx.HTTPError, ValueError):
            raise RuntimeError("detector worker request failed") from None


def run_detector(
    engine_input: EngineInput, *, backend: Any = None, storage: Any = None
) -> EngineOutput:
    run = QCRun.objects.select_related("snapshot", "config_version", "model_artifact").get(
        pk=engine_input.run_id, snapshot_id=engine_input.snapshot_id
    )
    if run.snapshot.status != Snapshot.Status.LOCKED:
        raise ValueError("detector snapshot must be locked")
    binding = artifact_binding(run)
    labels = taxonomy_mapping(run)
    provider = backend or HttpDetector()
    objects = storage or ObjectStorage.from_django_settings("snapshots")
    candidates: list[Candidate] = []
    results: list[EngineUnitResult] = []
    for unit in sorted(engine_input.units, key=lambda u: u.frame):
        frames = SnapshotFrame.objects.filter(
            snapshot_job__snapshot_id=run.snapshot_id,
            snapshot_job__cvat_task_id=unit.frame.cvat_task_id,
            frame_index=unit.frame.frame_number,
        ).order_by("pk")
        frame = frames.first()
        if frame is None:
            raise ValueError("detector frame missing from snapshot")
        if any((f.media_sha256, f.shapes) != (frame.media_sha256, frame.shapes) for f in frames):
            raise ValueError("ambiguous snapshot frame across jobs")
        if not 0 < frame.media_size_bytes <= MAX_FRAME_BYTES:
            raise ValueError("detector frame exceeds byte limit")
        head = objects.head(frame.media_storage_key)
        if head is None or head.size != frame.media_size_bytes:
            raise ValueError("detector media size mismatch")
        raw = objects.get(frame.media_storage_key)
        if (
            len(raw) != frame.media_size_bytes
            or hashlib.sha256(raw).hexdigest() != frame.media_sha256
        ):
            raise ValueError("detector media checksum mismatch")
        identity = {
            "snapshot_id": run.snapshot_id,
            "snapshot_revision": run.snapshot.revision_sha256,
            "cvat_task_id": unit.frame.cvat_task_id,
            "frame_number": unit.frame.frame_number,
            "media_sha256": frame.media_sha256,
            "width": frame.width,
            "height": frame.height,
        }
        prediction = provider.predict(identity, raw)
        if (
            prediction.get("schema_version") != "labelx.detector.frame.v1"
            or prediction.get("frame") != identity
            or prediction.get("model_sha256") != FROZEN_SHA256
            or prediction.get("class_mapping_version") != MAPPING_VERSION
            or prediction.get("classes") != list(CLASSES)
            or not isinstance(prediction.get("detections"), list)
        ):
            raise ValueError("detector output provenance/schema mismatch")
        candidates.extend(
            match_candidates(
                frame=unit.frame,
                width=frame.width,
                height=frame.height,
                shapes=frame.shapes,
                detections=prediction["detections"],
                classes=CLASSES,
                label_ids=labels,
                provenance={**binding, "frame": identity, "class_map": labels, "run_id": run.pk},
                params=engine_input.config.params,
            )
        )
        results.append(EngineUnitResult(unit, "completed", 1))
    return EngineOutput(
        engine_input.idempotency_key, "detector", "1.0.0", tuple(candidates), tuple(results)
    )


def register_detector_engine(target: EngineRegistry = registry) -> None:
    try:
        existing = target.descriptor("detector", "1.0.0")
    except LookupError:
        target.register(DETECTOR_DESCRIPTOR, run_detector)
    else:
        if existing != DETECTOR_DESCRIPTOR:
            raise ValueError("conflicting detector descriptor")
