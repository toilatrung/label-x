"""Top-3 inference with uncalibrated scores and margin."""

from __future__ import annotations

import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from PIL import Image, UnidentifiedImageError
from torch import nn

from .artifact import ClassifierArtifact
from .crops import INPUT_SIZE, CropError, letterbox_crop
from .model import to_tensor
from .taxonomy import CLASSES

MAX_IMAGE_PIXELS = 64_000_000


@dataclass(frozen=True)
class Prediction:
    top3: tuple[tuple[int, str, float], ...]  # (class_id, class_name, score)
    score: float
    margin: float

    def as_dict(self) -> dict[str, object]:
        return {
            "top3": [
                {"class_id": cid, "class_name": name, "score": score}
                for cid, name, score in self.top3
            ],
            "score": self.score,
            "margin": self.margin,
            "calibrated": False,
        }


class Classifier:
    def __init__(self, artifact: ClassifierArtifact, model: nn.Module, device: str) -> None:
        self.artifact = artifact
        self.model = model
        self.device = device

    @classmethod
    def load(cls, manifest_path: Path, *, device: str = "cpu") -> Classifier:
        artifact = ClassifierArtifact.load(manifest_path)
        return cls(artifact, artifact.load_model(device=device), device)

    @torch.inference_mode()
    def predict(self, crops: Sequence[Image.Image]) -> list[Prediction]:
        if not crops:
            return []
        batch = torch.stack([to_tensor(crop) for crop in crops]).to(self.device)
        probs = torch.softmax(self.model(batch).float(), dim=1).cpu()
        values, indices = probs.topk(3, dim=1)
        out: list[Prediction] = []
        for row_values, row_indices in zip(values.tolist(), indices.tolist(), strict=True):
            top3 = tuple((i, CLASSES[i], v) for i, v in zip(row_indices, row_values, strict=True))
            out.append(Prediction(top3, row_values[0], row_values[0] - row_values[1]))
        return out


def _prepare(item: Mapping[str, Any]) -> Image.Image:
    """One crop-ready 224x224 image: either a ready crop or a full image plus a box."""

    path = Path(str(item["image"]))
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as handle:
            if handle.width * handle.height > MAX_IMAGE_PIXELS:
                raise CropError("invalid_crop", "image is too large")
            image = handle.convert("RGB")
    box = item.get("box")
    if box is None:
        if image.size != (INPUT_SIZE, INPUT_SIZE):
            raise CropError("invalid_crop", f"a ready crop must be {INPUT_SIZE}x{INPUT_SIZE}")
        return image
    if not isinstance(box, list | tuple) or len(box) != 4:
        raise CropError("invalid_crop", "box must be [x1, y1, x2, y2]")
    return letterbox_crop(image, tuple(float(v) for v in box))[0]


def predict_batch(classifier: Classifier, items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Batch inference where one bad item never fails the others (stable reason per item)."""

    prepared: list[tuple[str, Image.Image]] = []
    results: list[dict[str, Any]] = []
    for item in items:
        item_id = str(item.get("id", ""))
        try:
            prepared.append((item_id, _prepare(item)))
        except CropError as exc:
            results.append({"id": item_id, "ok": False, "reason": exc.reason, "detail": str(exc)})
        except (OSError, UnidentifiedImageError, Warning, KeyError, TypeError, ValueError) as exc:
            results.append(
                {"id": item_id, "ok": False, "reason": "invalid_crop", "detail": str(exc)}
            )
    if prepared:
        predictions = classifier.predict([image for _, image in prepared])
        for (item_id, _), prediction in zip(prepared, predictions, strict=True):
            results.append({"id": item_id, "ok": True, "prediction": prediction.as_dict()})
    results.sort(key=lambda row: row["id"])
    artifact = classifier.artifact
    return {
        "checkpoint": {
            "version": artifact.version,
            "sha256": artifact.sha256,
            "status": artifact.status,
            "class_map_version": artifact.raw["class_mapping"]["version"],
        },
        "results": results,
    }
