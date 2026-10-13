"""M04A-04: SnapshotCropProvider cắt đúng vùng annotation từ ảnh snapshot (storage giả)."""

from __future__ import annotations

import hashlib
import io
from typing import Any

import pytest
from PIL import Image

from orchestration.models import CandidateRecord
from orchestration.vlm_crops import SnapshotCropProvider, pad_box, union_box
from snapshots.models import SnapshotFrame
from tests.orchestration.test_vlm_stage import (  # noqa: F401  (fixture _env tái sử dụng)
    _env,
    _make_run,
    _run_shards,
)
from vlm.contract import validate_crop
from vlm.errors import VlmInvalidCropError

pytestmark = pytest.mark.django_db(transaction=True)

W, H = 200, 120


def _frame_png() -> bytes:
    image = Image.new("RGB", (W, H), (255, 0, 0))
    for x in range(60, 100):  # vùng xanh: bbox annotation (60,40)-(100,80)
        for y in range(40, 80):
            image.putpixel((x, y), (0, 255, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class FakeStorage:
    def __init__(self, blobs: dict[str, bytes]) -> None:
        self.blobs = blobs
        self.reads: list[str] = []

    def head(self, key: str) -> Any:
        blob = self.blobs.get(key)
        return None if blob is None else type("Head", (), {"size": len(blob)})()

    def get(self, key: str) -> bytes:
        self.reads.append(key)
        if key not in self.blobs:
            raise OSError("không có object")
        return self.blobs[key]


def _setup(
    shapes: list[tuple[int, list[float]]],
    png: bytes | None = None,
    size: tuple[int, int] = (W, H),
) -> tuple[Any, FakeStorage]:
    data = png if png is not None else _frame_png()
    raw = [
        {"id": sid, "type": "rectangle", "frame": 0, "label_id": 1, "points": points}
        for sid, points in shapes
    ]
    run = _make_run(frame_media={0: data}, frame_size=size, raw_shapes=raw)
    _run_shards(run)
    frame = SnapshotFrame.objects.filter(snapshot_job__snapshot_id=run.snapshot_id).get(
        frame_index=0
    )
    return run, FakeStorage({frame.media_storage_key: data})


def _candidate(run: Any, object_ids: list[str]) -> CandidateRecord:
    candidate = CandidateRecord.objects.filter(run_id=run.pk, frame_number=0).first()
    CandidateRecord.objects.filter(pk=candidate.pk).update(
        anchor={"objects": [{"namespace": "cvat_shape", "id": i} for i in object_ids]}
    )
    candidate.refresh_from_db()
    return candidate


def _provider(storage: FakeStorage) -> SnapshotCropProvider:
    return SnapshotCropProvider(storage)  # type: ignore[arg-type]


def test_crop_covers_annotation_with_padding_and_records_origin() -> None:
    run, storage = _setup([(7, [60, 40, 100, 80])])
    crop = _provider(storage).load(_candidate(run, ["shape:7"]))
    validate_crop(crop)
    assert crop.mime_type == "image/png"
    origin = crop.origin
    assert origin is not None
    assert origin["box"] == [60.0, 40.0, 100.0, 80.0]
    assert origin["padded_box"] == [56.0, 36.0, 104.0, 84.0]  # lề max(4, 10% * 40) = 4
    assert origin["objects"] == ["shape:7"]
    assert origin["frame"]["media_sha256"] == hashlib.sha256(_frame_png()).hexdigest()
    image = Image.open(io.BytesIO(crop.data))
    assert image.size == (48, 48) and origin["output_size"] == [48, 48]
    assert image.getpixel((24, 24)) == (0, 255, 0)  # tâm là vùng annotation
    assert image.getpixel((1, 1)) == (255, 0, 0)  # viền là lề


def test_union_of_multiple_anchor_objects_and_clamp() -> None:
    run, storage = _setup([(1, [0, 0, 20, 20]), (2, [180, 100, 200, 120])])
    crop = _provider(storage).load(_candidate(run, ["shape:2", "shape:1"]))
    assert crop.origin is not None
    assert crop.origin["box"] == [0.0, 0.0, 200.0, 120.0]
    assert crop.origin["padded_box"] == [0.0, 0.0, 200.0, 120.0]  # kẹp trong ảnh
    assert crop.origin["objects"] == ["shape:1", "shape:2"]


def test_identity_is_deterministic_cheap_and_sensitive() -> None:
    run, storage = _setup([(7, [60, 40, 100, 80])])
    candidate = _candidate(run, ["shape:7"])
    provider = _provider(storage)
    first = provider.identity(candidate)
    assert len(first) == 64 and provider.identity(candidate) == first
    assert storage.reads == []  # identity không tải ảnh
    run2, storage2 = _setup([(7, [60, 40, 101, 80])])
    assert _provider(storage2).identity(_candidate(run2, ["shape:7"])) != first


@pytest.mark.parametrize("case", ["no_object", "unknown_object", "one_missing"])
def test_unresolvable_anchor_is_invalid_crop_never_whole_frame(case: str) -> None:
    ids = {
        "no_object": [],
        "unknown_object": ["shape:99"],
        "one_missing": ["shape:7", "shape:8"],
    }[case]
    run, storage = _setup([(7, [60, 40, 100, 80])])
    candidate = _candidate(run, ids)
    provider = _provider(storage)
    assert provider.identity(candidate) == ""
    with pytest.raises(VlmInvalidCropError):
        provider.load(candidate)
    assert storage.reads == []  # không tải ảnh khi anchor không phân giải được


def test_tiny_region_is_rejected() -> None:
    run, storage = _setup([(7, [10, 10, 10.2, 10.2])])
    candidate = _candidate(run, ["shape:7"])
    # lề tối thiểu 4px làm vùng ~8px: vẫn hợp lệ; vùng 0x0 mới bị loại
    assert _provider(storage).load(candidate).origin is not None
    degenerate = [{"source": {"kind": "shape", "id": 1}, "points": [5, 5, 5, 5]}]
    assert union_box(degenerate, ["shape:1"]) == (5.0, 5.0, 5.0, 5.0)


def test_media_integrity_and_storage_failures() -> None:
    run, storage = _setup([(7, [60, 40, 100, 80])])
    candidate = _candidate(run, ["shape:7"])
    key = next(iter(storage.blobs))
    original = _frame_png()
    storage.blobs[key] = bytes([original[0] ^ 1]) + original[1:]  # cùng kích thước, sha256 khác
    with pytest.raises(VlmInvalidCropError, match="sha256"):
        _provider(storage).load(candidate)
    with pytest.raises(VlmInvalidCropError, match="object ảnh gốc"):
        _provider(FakeStorage({})).load(candidate)

    class BrokenStorage(FakeStorage):
        def head(self, key: str) -> Any:
            raise OSError("mất kết nối")

    with pytest.raises(VlmInvalidCropError, match="storage"):
        _provider(BrokenStorage({})).load(candidate)


def test_not_an_image_and_size_mismatch_are_rejected() -> None:
    run, storage = _setup([(7, [60, 40, 100, 80])], png=b"not an image")
    with pytest.raises(VlmInvalidCropError, match="giải mã"):
        _provider(storage).load(_candidate(run, ["shape:7"]))
    small = io.BytesIO()
    Image.new("RGB", (50, 50)).save(small, format="PNG")
    run2, storage2 = _setup([(7, [10, 10, 40, 40])], png=small.getvalue())  # khai báo 200x120
    with pytest.raises(VlmInvalidCropError, match="kích thước"):
        _provider(storage2).load(_candidate(run2, ["shape:7"]))


def test_helpers_union_pad_and_bad_points() -> None:
    assert union_box([], ["a"]) is None
    assert union_box([{"source": {"kind": "s", "id": 1}, "points": [5, 6, 1, 2]}], ["s:1"]) == (
        1.0,
        2.0,
        5.0,
        6.0,
    )
    assert union_box([{"source": {"kind": "s", "id": 1}, "points": [1, 2, 3]}], ["s:1"]) is None
    assert (
        union_box([{"source": {"kind": "s", "id": 1}, "points": [1, 2, 3, "x"]}], ["s:1"]) is None
    )
    assert pad_box((50, 50, 150, 100), 200, 120) == (40.0, 40.0, 160.0, 110.0)


def test_size_is_checked_before_reading_object() -> None:
    run, storage = _setup([(7, [60, 40, 100, 80])])
    candidate = _candidate(run, ["shape:7"])
    key = next(iter(storage.blobs))
    storage.blobs[key] = _frame_png() + b"x" * 1000  # lớn hơn media_size_bytes của snapshot
    with pytest.raises(VlmInvalidCropError, match="kích thước"):
        _provider(storage).load(candidate)
    assert storage.reads == [key] or storage.reads == []  # get() không được gọi
    assert all(r != "get" for r in storage.reads[1:])
    missing = FakeStorage({})
    with pytest.raises(VlmInvalidCropError):
        _provider(missing).load(candidate)
    assert missing.reads == []  # head None: không đọc object
