"""Checkpoint packaging: manifest, checksum verification and safe loading (M04B-02)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from torch import nn

from .crops import INPUT_SIZE, PAD_FILL
from .model import IMAGENET_MEAN, IMAGENET_STD, PRETRAINED_SOURCE, build_model
from .taxonomy import CLASSES, MAPPING_VERSION

PREPROCESSING = {
    "input_size": INPUT_SIZE,
    "resize": "aspect-preserving fit + centered padding",
    "pad_fill_rgb": list(PAD_FILL),
    "color": "RGB",
    "scale": "1/255",
    "mean": list(IMAGENET_MEAN),
    "std": list(IMAGENET_STD),
}
OUTPUT_SEMANTICS = {
    "top_k": 3,
    "score": "softmax top-1 value; uncalibrated, not a probability of correctness",
    "margin": "top-1 score minus top-2 score",
    "calibrated": False,
    "unknown": "abstention decided by routing policy, not a class",
}
SCHEMA_VERSION = "labelx.classifier.model.v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
STATUSES = ("smoke_only", "trained")


class ManifestError(ValueError):
    """The model manifest is incomplete or inconsistent."""


class ChecksumMismatchError(RuntimeError):
    """Raised before ``torch.load`` when the checkpoint is not the frozen artifact."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ClassifierArtifact:
    path: Path
    raw: dict[str, Any]
    version: str
    checkpoint_filename: str
    sha256: str
    classes: tuple[str, ...]
    status: str

    @property
    def checkpoint_path(self) -> Path:
        return self.path.parent / self.checkpoint_filename

    @classmethod
    def load(cls, path: Path) -> ClassifierArtifact:
        manifest_path = path.resolve()
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            model, mapping = raw["model"], raw["class_mapping"]
            pre = raw["preprocessing"]
            classes = tuple(mapping["classes"])
            sha = str(model["sha256"]).lower()
            filename = str(model["checkpoint_filename"])
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ManifestError(f"Invalid classifier manifest {manifest_path}: {exc}") from exc
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise ManifestError(f"schema_version must be {SCHEMA_VERSION}")
        if not SHA256.fullmatch(sha):
            raise ManifestError("model.sha256 must be 64 lowercase hex characters")
        if classes != CLASSES or mapping.get("version") != MAPPING_VERSION:
            raise ManifestError("class_mapping must be the 10-class bdd100k-det-10-v1 map")
        if pre != PREPROCESSING:
            raise ManifestError("preprocessing does not match what inference actually applies")
        if raw.get("output_semantics") != OUTPUT_SEMANTICS:
            raise ManifestError("output_semantics does not match what inference actually returns")
        if model.get("architecture") != "convnext_tiny":
            raise ManifestError("model.architecture must be convnext_tiny")
        if Path(filename).name != filename:
            raise ManifestError("model.checkpoint_filename must be a bare file name")
        status = str(raw.get("training", {}).get("status", ""))
        if status not in STATUSES:
            raise ManifestError(f"training.status must be one of {STATUSES}")
        return cls(manifest_path, raw, str(model["version"]), filename, sha, classes, status)

    def verify_checkpoint(self) -> None:
        checkpoint = self.checkpoint_path
        if not checkpoint.is_file():
            raise ChecksumMismatchError(f"checkpoint not found: {checkpoint.name}")
        actual = sha256_file(checkpoint)
        if actual != self.sha256:
            raise ChecksumMismatchError(
                f"checkpoint sha256 {actual} does not match manifest {self.sha256}"
            )

    def load_model(self, *, device: str = "cpu") -> nn.Module:
        """Verify the checksum, then load weights only (no pickled code)."""

        self.verify_checkpoint()
        model = build_model(pretrained=False)
        state = torch.load(self.checkpoint_path, map_location=device, weights_only=True)
        model.load_state_dict(state)
        return model.to(device).eval()


def freeze_checkpoint(
    model: nn.Module,
    *,
    out_dir: Path,
    version: str,
    training: dict[str, Any],
    name: str = "ConvNeXt Tiny LabelX 10-class crop classifier",
) -> ClassifierArtifact:
    """Save weights + manifest. ``training['status']`` must say what the run really was."""

    if training.get("status") not in STATUSES:
        raise ManifestError(f"training.status must be one of {STATUSES}")
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"convnext_tiny_{version}.pth"
    checkpoint = out_dir / filename
    torch.save({k: v.detach().cpu() for k, v in model.state_dict().items()}, checkpoint)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model": {
            "name": name,
            "version": version,
            "architecture": "convnext_tiny",
            "checkpoint_filename": filename,
            "sha256": sha256_file(checkpoint),
            "size_bytes": checkpoint.stat().st_size,
            "init": PRETRAINED_SOURCE,
            "torch": torch.__version__,
        },
        "class_mapping": {"version": MAPPING_VERSION, "classes": list(CLASSES)},
        "preprocessing": PREPROCESSING,
        "output_semantics": OUTPUT_SEMANTICS,
        "training": training,
    }
    manifest_path = out_dir / "classifier-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return ClassifierArtifact.load(manifest_path)
