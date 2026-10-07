import hashlib
import json
from pathlib import Path

import pytest

from labelx_detector.artifact import (
    ArtifactManifest,
    ChecksumMismatchError,
    ManifestError,
    freeze_checkpoint,
    verify_checkpoint,
)

CLASSES = [
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
]


def write_manifest(path: Path, sha256=None):
    path.write_text(
        json.dumps(
            {
                "model": {
                    "name": "test-model",
                    "version": "v1",
                    "checkpoint_filename": "model.pth",
                    "sha256": sha256,
                },
                "class_mapping": {"version": "bdd-v1", "classes": CLASSES},
            }
        ),
        encoding="utf-8",
    )


def test_manifest_refuses_unfrozen_checkpoint(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path)

    with pytest.raises(ManifestError, match="not frozen"):
        ArtifactManifest.load(manifest_path)


def test_checkpoint_checksum_is_verified_before_use(tmp_path):
    checkpoint = tmp_path / "model.pth"
    checkpoint.write_bytes(b"frozen detector")
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path, digest)

    manifest = ArtifactManifest.load(manifest_path)
    assert verify_checkpoint(checkpoint, manifest) == digest

    checkpoint.write_bytes(b"tampered detector")
    with pytest.raises(ChecksumMismatchError, match="Model loading was refused"):
        verify_checkpoint(checkpoint, manifest)


def test_freeze_records_sha_size_and_filename(tmp_path):
    checkpoint = tmp_path / "recovered.pth"
    checkpoint.write_bytes(b"official artifact")
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path)

    digest = freeze_checkpoint(checkpoint, manifest_path)
    manifest = ArtifactManifest.load(manifest_path)

    assert digest == hashlib.sha256(b"official artifact").hexdigest()
    assert manifest.sha256 == digest
    assert manifest.checkpoint_filename == "recovered.pth"
    assert manifest.raw["model"]["size_bytes"] == len(b"official artifact")
    assert manifest.raw["model"]["artifact_state"] == "frozen"


def test_manifest_requires_exactly_ten_unique_classes(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path, "0" * 64)
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["class_mapping"]["classes"] = ["car"] * 10
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ManifestError, match="10 unique"):
        ArtifactManifest.load(manifest_path)
