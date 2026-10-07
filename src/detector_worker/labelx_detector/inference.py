"""Batch inference and stable JSON serialization for MMDetection 2.x."""

from __future__ import annotations

import json
import os
import platform
import tempfile
import time
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image
from typing_extensions import Protocol

from .artifact import ArtifactManifest, verify_checkpoint

SUPPORTED_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"})
SCHEMA_VERSION = "labelx.detector.predictions.v1"


class DetectorBackend(Protocol):
    """Minimal backend contract, kept injectable for CPU-only tests."""

    def infer(self, image_paths: Sequence[Path]) -> Sequence[Any]: ...

    def synchronize(self) -> None: ...

    def hardware(self) -> dict[str, Any]: ...


class MMDetectionBackend:
    """Lazy MMDetection 2.x adapter; imports only after checksum verification."""

    def __init__(self, config: Path, checkpoint: Path, device: str, classes: Sequence[str]):
        try:
            import torch
            from mmdet.apis import inference_detector, init_detector
        except ImportError as exc:
            raise RuntimeError(
                "MMDetection runtime is unavailable. Run inside the detector-worker image."
            ) from exc

        self._torch = torch
        self._inference_detector = inference_detector
        self._device = device
        self._model = init_detector(str(config), str(checkpoint), device=device)
        self._model.CLASSES = tuple(classes)

    def infer(self, image_paths: Sequence[Path]) -> Sequence[Any]:
        result = self._inference_detector(self._model, [str(path) for path in image_paths])
        return result if isinstance(result, list) else [result]

    def synchronize(self) -> None:
        if self._device.startswith("cuda") and self._torch.cuda.is_available():
            self._torch.cuda.synchronize()

    def hardware(self) -> dict[str, Any]:
        details: dict[str, Any] = {
            "platform": platform.platform(),
            "processor": platform.processor() or "unknown",
            "python": platform.python_version(),
            "device": self._device,
            "torch": self._torch.__version__,
            "cuda_available": self._torch.cuda.is_available(),
        }
        if self._torch.cuda.is_available():
            index = self._torch.cuda.current_device()
            properties = self._torch.cuda.get_device_properties(index)
            details.update(
                {
                    "cuda_runtime": self._torch.version.cuda,
                    "gpu_name": properties.name,
                    "gpu_memory_bytes": properties.total_memory,
                }
            )
        return details


def collect_images(input_directory: Path, recursive: bool = False) -> list[Path]:
    """Return supported images in deterministic relative-path order."""

    root = input_directory.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Input directory does not exist: {root}")
    candidates: Iterable[Path] = root.rglob("*") if recursive else root.iterdir()
    images = [
        path
        for path in candidates
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
    ]
    return sorted(images, key=lambda path: path.relative_to(root).as_posix().casefold())


def _rows(value: Any) -> Iterable[Sequence[float]]:
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def serialize_detections(
    result: Any,
    classes: Sequence[str],
    image_size: tuple[int, int],
    score_threshold: float,
) -> list[dict[str, Any]]:
    """Convert MMDetection 2.x class-major output to original-pixel boxes."""

    bbox_result = result[0] if isinstance(result, tuple) else result
    if len(bbox_result) != len(classes):
        raise ValueError(
            f"Model returned {len(bbox_result)} class buckets; expected {len(classes)}"
        )
    width, height = image_size
    detections: list[dict[str, Any]] = []
    for class_id, class_rows in enumerate(bbox_result):
        for row in _rows(class_rows):
            if len(row) < 5:
                raise ValueError("A detector row must contain x1, y1, x2, y2, confidence")
            x1, y1, x2, y2, confidence = (float(item) for item in row[:5])
            if confidence < score_threshold:
                continue
            clipped = [
                min(max(x1, 0.0), float(width)),
                min(max(y1, 0.0), float(height)),
                min(max(x2, 0.0), float(width)),
                min(max(y2, 0.0), float(height)),
            ]
            if clipped[0] >= clipped[2] or clipped[1] >= clipped[3]:
                continue
            detections.append(
                {
                    "bbox_xyxy": clipped,
                    "class_id": class_id,
                    "class_name": classes[class_id],
                    "confidence": confidence,
                }
            )
    return sorted(
        detections,
        key=lambda item: (-item["confidence"], item["class_id"], item["bbox_xyxy"]),
    )


def _atomic_json_dump(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def run_batch(
    *,
    input_directory: Path,
    output: Path,
    checkpoint: Path,
    manifest: ArtifactManifest,
    config: Path,
    device: str,
    batch_size: int,
    score_threshold: float,
    recursive: bool = False,
    backend: DetectorBackend | None = None,
) -> dict[str, Any]:
    """Verify, infer, and atomically write the stable prediction document."""

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    if not 0.0 <= score_threshold <= 1.0:
        raise ValueError("score_threshold must be between 0 and 1")
    checksum = verify_checkpoint(checkpoint, manifest)
    images = collect_images(input_directory, recursive=recursive)
    if not images:
        raise ValueError(f"No supported images found in {input_directory.resolve()}")

    detector = backend or MMDetectionBackend(config, checkpoint, device, manifest.classes)
    started = time.perf_counter()
    records: list[dict[str, Any]] = []
    input_root = input_directory.resolve()
    for offset in range(0, len(images), batch_size):
        paths = images[offset : offset + batch_size]
        detector.synchronize()
        batch_started = time.perf_counter()
        results = list(detector.infer(paths))
        detector.synchronize()
        batch_elapsed = time.perf_counter() - batch_started
        if len(results) != len(paths):
            raise ValueError(f"Backend returned {len(results)} results for {len(paths)} images")
        for path, result in zip(paths, results):
            with Image.open(path) as image:
                width, height = image.size
            records.append(
                {
                    "path": path.relative_to(input_root).as_posix(),
                    "width": width,
                    "height": height,
                    "inference_seconds": batch_elapsed / len(paths),
                    "detections": serialize_detections(
                        result, manifest.classes, (width, height), score_threshold
                    ),
                }
            )
    elapsed = time.perf_counter() - started
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model": {
            "name": manifest.name,
            "version": manifest.version,
            "checkpoint_filename": checkpoint.name,
            "sha256": checksum,
            "class_mapping_version": manifest.mapping_version,
            "classes": list(manifest.classes),
        },
        "run": {
            "device": device,
            "batch_size": batch_size,
            "score_threshold": score_threshold,
            "image_count": len(records),
            "elapsed_seconds": elapsed,
            "seconds_per_image": elapsed / len(records),
            "hardware": detector.hardware(),
        },
        "images": records,
    }
    _atomic_json_dump(payload, output.resolve())
    return payload
