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
from .dataset import FIT_SPLITS, HELD_OUT, canonical_json, file_sha256, sha256_hex
from .model import build_model, to_tensor
from .taxonomy import CLASSES


class TrainingDataError(ValueError):
    """The dataset manifest is inconsistent or has no fit data."""


def load_dataset_manifest(dataset_dir: Path) -> dict[str, Any]:
    """Load and integrity-check ``dataset-manifest.json`` and every crop file."""

    path = dataset_dir / "dataset-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    claimed = manifest.pop("manifest_sha256", None)
    if claimed != sha256_hex(canonical_json(manifest)):
        raise TrainingDataError("dataset manifest hash mismatch")
    manifest["manifest_sha256"] = claimed
    for record in manifest["crops"]:
        if record["split"] == HELD_OUT:
            continue
        if file_sha256(dataset_dir / record["path"]) != record["crop_sha256"]:
            raise TrainingDataError(f"crop {record['crop_id']} does not match its recorded hash")
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


def train_classifier(
    dataset_dir: Path,
    out_dir: Path,
    *,
    version: str,
    status: str,
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
    training = {
        "status": status,
        "dataset_manifest_sha256": manifest["manifest_sha256"],
        "snapshot_sha256": manifest["snapshot"]["sha256"],
        "fit_split": "train",
        "train_samples": len(train_records),
        "train_class_counts": dict(sorted(train_classes.items())),
        "classes_without_train_samples": [c for c in CLASSES if c not in train_classes],
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
