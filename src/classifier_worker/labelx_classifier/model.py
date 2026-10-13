"""ConvNeXt Tiny with a 10-class head and the preprocessing it was fine-tuned with."""

from __future__ import annotations

import numpy as np
import torch
from PIL import Image
from torch import nn
from torchvision.models import ConvNeXt_Tiny_Weights, convnext_tiny

from .crops import INPUT_SIZE
from .taxonomy import CLASSES

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
PRETRAINED_SOURCE = "torchvision ConvNeXt_Tiny_Weights.IMAGENET1K_V1"


def build_model(*, pretrained: bool) -> nn.Module:
    """``pretrained=True`` downloads ImageNet weights; ``False`` gives a random init (tests)."""

    weights = ConvNeXt_Tiny_Weights.IMAGENET1K_V1 if pretrained else None
    model = convnext_tiny(weights=weights)
    in_features = model.classifier[2].in_features
    model.classifier[2] = nn.Linear(in_features, len(CLASSES))
    return model


def to_tensor(image: Image.Image) -> torch.Tensor:
    """224x224 RGB crop -> normalized CHW float tensor."""

    if image.size != (INPUT_SIZE, INPUT_SIZE):
        raise ValueError(f"crop must be {INPUT_SIZE}x{INPUT_SIZE}, got {image.size}")
    array = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    tensor = torch.from_numpy(array).permute(2, 0, 1)
    mean = torch.tensor(IMAGENET_MEAN).view(3, 1, 1)
    std = torch.tensor(IMAGENET_STD).view(3, 1, 1)
    return (tensor - mean) / std
