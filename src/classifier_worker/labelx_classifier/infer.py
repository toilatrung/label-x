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
from .crops import CropError, letterbox_crop
from .model import to_tensor
from .taxonomy import CLASSES

MAX_IMAGE_PIXELS = 64_000_000
PREDICT_CHUNK = 16  # bounds memory: a batch is forwarded in chunks
MAX_BATCH_ITEMS = 1000


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
        out: list[Prediction] = []
        for start in range(0, len(crops), PREDICT_CHUNK):
            out.extend(self._predict_chunk(crops[start : start + PREDICT_CHUNK]))
        return out

    def _predict_chunk(self, crops: Sequence[Image.Image]) -> list[Prediction]:
        batch = torch.stack([to_tensor(crop) for crop in crops]).to(self.device)
        probs = torch.softmax(self.model(batch).float(), dim=1).cpu()
        values, indices = probs.topk(3, dim=1)
        out: list[Prediction] = []
        for row_values, row_indices in zip(values.tolist(), indices.tolist(), strict=True):
            top3 = tuple((i, CLASSES[i], v) for i, v in zip(row_indices, row_values, strict=True))
            out.append(Prediction(top3, row_values[0], row_values[0] - row_values[1]))
        return out


class BatchError(ValueError):
    """The whole batch is unusable (not a single bad item)."""


def _resolve(image_root: Path, value: object) -> Path:
    root = image_root.resolve()
    path = (root / str(value)).resolve()  # follows symlinks, so a link out of root is caught
    if root not in path.parents:
        raise CropError("invalid_crop", "image is outside the allowed root")
    return path


def _prepare(item: Mapping[str, Any], image_root: Path) -> Image.Image:
    """One 224x224 letterboxed image: a whole crop image, or a full image plus a box."""

    path = _resolve(image_root, item["image"])
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as handle:  # reads the header only
            if handle.width * handle.height > MAX_IMAGE_PIXELS:
                raise CropError("invalid_crop", "image is too large")
            image = handle.convert("RGB")
    box = item.get("box")
    if box is None:  # the whole image is the crop: same letterbox as training crops
        return letterbox_crop(image, (0, 0, image.width, image.height))[0]
    if not isinstance(box, list | tuple) or len(box) != 4:
        raise CropError("invalid_crop", "box must be [x1, y1, x2, y2]")
    return letterbox_crop(image, tuple(float(v) for v in box))[0]


def _item_error(reason: str, item_id: str) -> dict[str, Any]:
    return {"id": item_id, "ok": False, "reason": reason}  # stable codes only, never details


def predict_batch(
    classifier: Classifier, items: Sequence[Any], *, image_root: Path
) -> dict[str, Any]:
    """Batch inference in input order. One bad item never fails the others.

    Results carry stable reason codes only (no paths, no raw exception text). Items whose ``id``
    is missing or repeated are rejected, so results can always be matched to the input.
    """

    if len(items) > MAX_BATCH_ITEMS:
        raise BatchError(f"at most {MAX_BATCH_ITEMS} items per batch")
    counts: dict[str, int] = {}
    for item in items:
        if isinstance(item, Mapping) and isinstance(item.get("id"), str) and item["id"]:
            counts[item["id"]] = counts.get(item["id"], 0) + 1
    results: list[dict[str, Any] | None] = [None] * len(items)
    ready: list[tuple[int, Image.Image]] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            results[index] = _item_error("invalid_item", "")
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            results[index] = _item_error("missing_id", "")
        elif counts[item_id] > 1:
            results[index] = _item_error("duplicate_id", item_id)
        else:
            try:
                ready.append((index, _prepare(item, image_root)))
            except CropError as exc:
                results[index] = _item_error(exc.reason, item_id)
            except (
                OSError,
                UnidentifiedImageError,
                Image.DecompressionBombError,
                Warning,
                KeyError,
                TypeError,
                ValueError,
            ):
                results[index] = _item_error("invalid_crop", item_id)
    if ready:
        predictions = classifier.predict([image for _, image in ready])
        for (index, _), prediction in zip(ready, predictions, strict=True):
            results[index] = {
                "id": items[index]["id"],
                "ok": True,
                "prediction": prediction.as_dict(),
            }
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
