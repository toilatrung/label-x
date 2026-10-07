import hashlib
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from PIL import Image

from labelx_detector.artifact import ArtifactManifest
from labelx_detector.inference import (
    SCHEMA_VERSION,
    MMDetectionBackend,
    run_batch,
    serialize_detections,
)

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


class FakeBackend:
    def infer(self, image_paths):
        results = []
        for _ in image_paths:
            buckets = [[] for _ in CLASSES]
            buckets[2] = [[-2, 4, 80, 60, 0.95], [1, 1, 2, 2, 0.01]]
            results.append(buckets)
        return results

    def synchronize(self):
        return None

    def hardware(self):
        return {"device": "cpu", "processor": "test"}


def frozen_fixture(tmp_path: Path):
    checkpoint = tmp_path / "model.pth"
    checkpoint.write_bytes(b"checkpoint")
    digest = hashlib.sha256(b"checkpoint").hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "model": {
                    "name": "test-model",
                    "version": "v1",
                    "checkpoint_filename": checkpoint.name,
                    "sha256": digest,
                },
                "class_mapping": {"version": "bdd-v1", "classes": CLASSES},
            }
        ),
        encoding="utf-8",
    )
    return checkpoint, ArtifactManifest.load(manifest_path)


def test_serialize_detections_uses_original_pixel_bounds():
    buckets = [[] for _ in CLASSES]
    buckets[0] = [[-5, -7, 140, 90, 0.8]]

    detections = serialize_detections(buckets, CLASSES, (128, 72), 0.05)

    assert detections == [
        {
            "bbox_xyxy": [0.0, 0.0, 128.0, 72.0],
            "class_id": 0,
            "class_name": "pedestrian",
            "confidence": 0.8,
        }
    ]


def test_backend_refuses_checkpoint_class_order_mismatch(monkeypatch, tmp_path):
    torch = ModuleType("torch")
    mmdet = ModuleType("mmdet")
    apis = ModuleType("mmdet.apis")
    torch.load = lambda checkpoint, map_location: {"meta": {"CLASSES": tuple(reversed(CLASSES))}}
    apis.inference_detector = lambda model, paths: []
    apis.init_detector = lambda config, checkpoint, device: SimpleNamespace()
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "mmdet", mmdet)
    monkeypatch.setitem(sys.modules, "mmdet.apis", apis)

    with pytest.raises(ValueError, match="class order does not match"):
        MMDetectionBackend(
            tmp_path / "config.py",
            tmp_path / "model.pth",
            "cpu",
            CLASSES,
        )


def test_backend_uses_manifest_classes_when_checkpoint_metadata_is_missing(monkeypatch, tmp_path):
    torch = ModuleType("torch")
    mmdet = ModuleType("mmdet")
    apis = ModuleType("mmdet.apis")
    torch.load = lambda checkpoint, map_location: {"meta": {}}
    apis.inference_detector = lambda model, paths: []
    apis.init_detector = lambda config, checkpoint, device: SimpleNamespace()
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "mmdet", mmdet)
    monkeypatch.setitem(sys.modules, "mmdet.apis", apis)

    backend = MMDetectionBackend(
        tmp_path / "config.py",
        tmp_path / "model.pth",
        "cpu",
        CLASSES,
    )

    assert backend._model.CLASSES == CLASSES


def test_batch_of_ten_images_writes_stable_json(tmp_path):
    checkpoint, manifest = frozen_fixture(tmp_path)
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    for index in range(10):
        Image.new("RGB", (64, 48), color=(index, index, index)).save(
            image_dir / f"sample-{index:02}.jpg"
        )
    output = tmp_path / "predictions.json"

    payload = run_batch(
        input_directory=image_dir,
        output=output,
        checkpoint=checkpoint,
        manifest=manifest,
        config=tmp_path / "unused.py",
        device="cpu",
        batch_size=4,
        score_threshold=0.05,
        backend=FakeBackend(),
    )

    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["schema_version"] == SCHEMA_VERSION
    assert written["run"]["image_count"] == 10
    assert written["model"]["classes"] == list(CLASSES)
    assert len(written["images"]) == 10
    assert written["images"][0]["path"] == "sample-00.jpg"
    assert written["images"][0]["detections"][0]["bbox_xyxy"] == [0.0, 4.0, 64.0, 48.0]
    assert payload["run"]["seconds_per_image"] >= 0
