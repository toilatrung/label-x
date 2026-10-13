"""Deterministic 224x224 crop with aspect-preserving resize and padding."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from PIL import Image

INPUT_SIZE = 224
PAD_FILL = (114, 114, 114)
MIN_SIDE_PX = 4


class CropError(ValueError):
    """Raised with a stable ``reason`` when a box cannot produce a usable crop."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class CropGeometry:
    """Maps crop pixels back to the original image (``x_src = x_crop / scale + x0 - pad``)."""

    source_box: tuple[int, int, int, int]  # integer region actually cut (x1, y1, x2, y2)
    scale: float
    pad_left: int
    pad_top: int
    resized_width: int
    resized_height: int
    size: int

    def to_source(self, x: float, y: float) -> tuple[float, float]:
        x1, y1, _, _ = self.source_box
        return (x - self.pad_left) / self.scale + x1, (y - self.pad_top) / self.scale + y1

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["source_box"] = list(self.source_box)
        return data


def letterbox_crop(
    image: Image.Image,
    box: tuple[float, float, float, float],
    *,
    size: int = INPUT_SIZE,
    min_side: int = MIN_SIDE_PX,
) -> tuple[Image.Image, CropGeometry]:
    """Cut ``box`` (x1, y1, x2, y2 in image pixels), resize to fit ``size`` and pad."""

    if not all(math.isfinite(value) for value in box):
        raise CropError("invalid_box", "box coordinates must be finite")
    x1, y1, x2, y2 = box
    if x2 < x1 or y2 < y1:
        raise CropError("invalid_box", "box must have x2>=x1 and y2>=y1")
    width, height = image.size
    left = max(0, math.floor(x1))
    top = max(0, math.floor(y1))
    right = min(width, math.ceil(x2))
    bottom = min(height, math.ceil(y2))
    if right - left < min_side or bottom - top < min_side:
        raise CropError("box_too_small", f"clipped box is smaller than {min_side}px")
    region = image.convert("RGB").crop((left, top, right, bottom))
    scale = size / max(region.width, region.height)
    new_w = max(1, min(size, round(region.width * scale)))
    new_h = max(1, min(size, round(region.height * scale)))
    resized = region.resize((new_w, new_h), Image.Resampling.BICUBIC)
    canvas = Image.new("RGB", (size, size), PAD_FILL)
    pad_left = (size - new_w) // 2
    pad_top = (size - new_h) // 2
    canvas.paste(resized, (pad_left, pad_top))
    return canvas, CropGeometry(
        source_box=(left, top, right, bottom),
        scale=scale,
        pad_left=pad_left,
        pad_top=pad_top,
        resized_width=new_w,
        resized_height=new_h,
        size=size,
    )
