import pytest
from PIL import Image

from labelx_classifier.crops import INPUT_SIZE, CropError, letterbox_crop


def test_wide_box_is_padded_not_stretched():
    image = Image.new("RGB", (400, 300), (255, 0, 0))
    crop, geometry = letterbox_crop(image, (100, 100, 300, 150))  # 200x50
    assert crop.size == (INPUT_SIZE, INPUT_SIZE)
    assert geometry.resized_width == INPUT_SIZE and geometry.resized_height == 56
    assert geometry.pad_top == (INPUT_SIZE - 56) // 2 and geometry.pad_left == 0
    assert crop.getpixel((10, 2)) == (114, 114, 114)  # padding row
    assert crop.getpixel((10, INPUT_SIZE // 2)) == (255, 0, 0)  # content row


def test_geometry_maps_back_to_source():
    image = Image.new("RGB", (400, 300))
    _, geometry = letterbox_crop(image, (100, 100, 300, 150))
    x, y = geometry.to_source(geometry.pad_left, geometry.pad_top)
    assert (round(x, 3), round(y, 3)) == (100.0, 100.0)
    x, y = geometry.to_source(
        geometry.pad_left + geometry.resized_width, geometry.pad_top + geometry.resized_height
    )
    assert abs(x - 300) < 1 and abs(y - 150) < 1


def test_box_is_clipped_to_image():
    image = Image.new("RGB", (100, 100))
    _, geometry = letterbox_crop(image, (-20, -20, 60, 60))
    assert geometry.source_box == (0, 0, 60, 60)


@pytest.mark.parametrize(
    ("box", "reason"),
    [
        ((10, 10, 12, 80), "box_too_small"),
        ((200, 200, 300, 300), "box_too_small"),  # fully outside the 100x100 image
        ((50, 50, 10, 80), "invalid_box"),
        ((float("nan"), 0, 10, 10), "invalid_box"),
    ],
)
def test_unusable_boxes_have_stable_reason(box, reason):
    with pytest.raises(CropError) as excinfo:
        letterbox_crop(Image.new("RGB", (100, 100)), box)
    assert excinfo.value.reason == reason


def test_crop_is_deterministic():
    image = Image.effect_noise((200, 200), 40).convert("RGB")
    first, _ = letterbox_crop(image, (10, 10, 150, 90))
    second, _ = letterbox_crop(image, (10, 10, 150, 90))
    assert first.tobytes() == second.tobytes()
