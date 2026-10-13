"""Fine-tune ConvNeXt Tiny on a crop dataset built by ``dataset.build_dataset`` (M04B-02).

Only the ``train`` split is used for fitting; ``val`` is only measured. ``held_out`` is never read.
Measured numbers are recorded as-is in the manifest; nothing here is a calibration or a KPI.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset

from .artifact import ClassifierArtifact, freeze_checkpoint
from .dataset import (
    ALL_SPLITS,
    DATA_ORIGINS,
    FIT_SPLITS,
    SCHEMA_VERSION,
    SplitConfig,
    canonical_json,
    file_sha256,
    sha256_hex,
)
from .model import build_model, to_tensor
from .taxonomy import CLASS_INDEX, CLASSES, MAPPING_VERSION

MIN_EPOCHS_FOR_TRAINED = 3


class TrainingDataError(ValueError):
    """The dataset manifest is inconsistent or has no fit data."""


def load_dataset_manifest(dataset_dir: Path) -> dict[str, Any]:
    """Load ``dataset-manifest.json`` and re-validate every invariant, not just the hash.

    A self-consistent hash proves nothing about a manifest someone rewrote, so the split
    assignment, group integrity, file locations and per-crop hashes are checked again here.
    """

    root = dataset_dir.resolve()
    manifest = json.loads((root / "dataset-manifest.json").read_text(encoding="utf-8"))
    claimed = manifest.pop("manifest_sha256", None)
    if claimed != sha256_hex(canonical_json(manifest)):
        raise TrainingDataError("dataset manifest hash mismatch")
    manifest["manifest_sha256"] = claimed
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise TrainingDataError(f"dataset schema_version must be {SCHEMA_VERSION}")
    mapping = manifest.get("class_mapping", {})
    if mapping.get("version") != MAPPING_VERSION or tuple(mapping.get("classes", ())) != CLASSES:
        raise TrainingDataError("dataset class mapping is not the 10-class bdd100k-det-10-v1 map")
    if manifest.get("data_origin") not in DATA_ORIGINS:
        raise TrainingDataError(f"dataset data_origin must be one of {DATA_ORIGINS}")
    try:
        config = SplitConfig(
            val=manifest["split"]["val_fraction"],
            held_out=manifest["split"]["held_out_fraction"],
            seed=manifest["split"]["seed"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TrainingDataError(f"dataset split configuration is invalid: {exc}") from exc
    group_split: dict[str, str] = {}
    seen_ids: set[str] = set()
    for record in manifest["crops"]:
        crop_id, split = record["crop_id"], record["split"]
        if crop_id in seen_ids:
            raise TrainingDataError(f"duplicate crop_id {crop_id}")
        seen_ids.add(crop_id)
        if split not in ALL_SPLITS:
            raise TrainingDataError(f"crop {crop_id} has unknown split {split!r}")
        if CLASS_INDEX.get(record["class_name"]) != record["class_id"]:
            raise TrainingDataError(f"crop {crop_id} class_id does not match its class_name")
        group = record["source_group"]
        if group_split.setdefault(group, split) != split:
            raise TrainingDataError(f"source group {group} spans more than one split")
        if config.assign(group) != split:
            raise TrainingDataError(f"crop {crop_id} is not in the split its group maps to")
        path = (root / record["path"]).resolve()
        if root not in path.parents or not path.is_file():
            raise TrainingDataError(f"crop {crop_id} path is outside the dataset directory")
        if file_sha256(path) != record["crop_sha256"]:
            raise TrainingDataError(f"crop {crop_id} does not match its recorded hash")
    return manifest


class CropDataset(Dataset):
    def __init__(self, dataset_dir: Path, records: list[dict[str, Any]]) -> None:
        self.dataset_dir = dataset_dir
        self.records = records

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        record = self.records[index]
        with Image.open(self.dataset_dir / record["path"]) as image:
            return to_tensor(image.convert("RGB")), int(record["class_id"])


def _records(manifest: dict[str, Any], split: str) -> list[dict[str, Any]]:
    if split not in FIT_SPLITS:
        raise TrainingDataError(f"split {split!r} may not be read for fitting or validation")
    return [record for record in manifest["crops"] if record["split"] == split]


@torch.inference_mode()
def _evaluate(model: nn.Module, loader: DataLoader, device: str) -> dict[str, Any]:
    model.eval()
    correct = total = 0
    for inputs, targets in loader:
        predicted = model(inputs.to(device)).argmax(dim=1).cpu()
        correct += int((predicted == targets).sum())
        total += len(targets)
    return {"samples": total, "top1_accuracy": (correct / total) if total else None}


def training_status(
    *,
    smoke_only: bool,
    data_origin: str,
    pretrained: bool,
    epochs: int,
    has_val: bool,
    missing_classes: list[str],
) -> tuple[str, list[str]]:
    """``trained`` only when every condition for a real run holds; never chosen by the caller."""

    blockers = {
        "forced_smoke_only": smoke_only,
        "dataset_origin_is_not_real": data_origin != "real",
        "not_imagenet_pretrained": not pretrained,
        f"epochs_below_{MIN_EPOCHS_FOR_TRAINED}": epochs < MIN_EPOCHS_FOR_TRAINED,
        "empty_val_split": not has_val,
        "classes_without_train_samples": bool(missing_classes),
    }
    reasons = [name for name, hit in blockers.items() if hit]
    return ("smoke_only" if reasons else "trained"), reasons


def train_classifier(
    dataset_dir: Path,
    out_dir: Path,
    *,
    version: str,
    smoke_only: bool = False,
    epochs: int = 5,
    batch_size: int = 32,
    lr: float = 1e-4,
    seed: int = 0,
    device: str | None = None,
    pretrained: bool = True,
    git_commit: str | None = None,
) -> ClassifierArtifact:
    manifest = load_dataset_manifest(dataset_dir)
    train_records = _records(manifest, "train")
    if not train_records:
        raise TrainingDataError("no crops in the train split; refusing to produce a checkpoint")
    val_records = _records(manifest, "val")
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    random.seed(seed)
    torch.manual_seed(seed)

    model = build_model(pretrained=pretrained).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    loss_fn = nn.CrossEntropyLoss()
    generator = torch.Generator().manual_seed(seed)
    train_loader = DataLoader(
        CropDataset(dataset_dir, train_records),
        batch_size=batch_size,
        shuffle=True,
        generator=generator,
    )
    losses: list[float] = []
    for _ in range(epochs):
        model.train()
        running = count = 0
        for inputs, targets in train_loader:
            optimizer.zero_grad()
            loss = loss_fn(model(inputs.to(device)), targets.to(device))
            loss.backward()
            optimizer.step()
            running += loss.item() * len(targets)
            count += len(targets)
        losses.append(running / count)

    val = {"samples": 0, "top1_accuracy": None}
    if val_records:
        val = _evaluate(
            model, DataLoader(CropDataset(dataset_dir, val_records), batch_size=batch_size), device
        )
    train_classes = Counter(r["class_name"] for r in train_records)
    missing = [c for c in CLASSES if c not in train_classes]
    status, status_reasons = training_status(
        smoke_only=smoke_only,
        data_origin=manifest["data_origin"],
        pretrained=pretrained,
        epochs=epochs,
        has_val=bool(val_records),
        missing_classes=missing,
    )
    training = {
        "status": status,
        "status_reasons": status_reasons,
        "data_origin": manifest["data_origin"],
        "dataset_manifest_sha256": manifest["manifest_sha256"],
        "snapshot_sha256": manifest["snapshot"]["sha256"],
        "fit_split": "train",
        "train_samples": len(train_records),
        "train_class_counts": dict(sorted(train_classes.items())),
        "classes_without_train_samples": missing,
        "val_split_measurement": val,
        "held_out_used": False,
        "epochs": epochs,
        "batch_size": batch_size,
        "lr": lr,
        "optimizer": "AdamW",
        "seed": seed,
        "device": device,
        "pretrained_init": pretrained,
        "epoch_train_loss": losses,
        "git_commit": git_commit,
        "note": (
            "val_split_measurement is measured on the technical val split only; it is not a "
            "calibration, KPI or held-out result."
        ),
    }
    return freeze_checkpoint(model.cpu(), out_dir=out_dir, version=version, training=training)
