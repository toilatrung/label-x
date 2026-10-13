"""Top-3 inference with uncalibrated scores and margin."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import torch
from PIL import Image
from torch import nn

from .artifact import ClassifierArtifact
from .model import to_tensor
from .taxonomy import CLASSES


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
