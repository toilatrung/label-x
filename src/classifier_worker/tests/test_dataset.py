import hashlib
import json
from pathlib import Path

import pytest

from labelx_classifier.dataset import (
    DatasetError,
    SplitConfig,
    build_dataset,
    parse_label_map,
)
from labelx_classifier.taxonomy import CLASSES

from .conftest import LABELS, _shape


def build(snapshot, image_root, tmp_path, **kwargs):
    return build_dataset(
        snapshot,
        image_root=image_root,
        out_dir=tmp_path / "out",
        label_map=parse_label_map({str(k): v for k, v in LABELS.items()}),
        **kwargs,
    )


def test_every_crop_traces_to_snapshot_and_annotation(snapshot, image_root, tmp_path):
    manifest = build(snapshot, image_root, tmp_path, snapshot_revision_sha256="a" * 64)
    assert manifest["counts"]["crops"] == 24
    record = manifest["crops"][0]
    prov = record["provenance"]
    assert prov["snapshot_revision_sha256"] == "a" * 64
    assert prov["snapshot_sha256"] == manifest["snapshot"]["sha256"]
    assert {"cvat_task_id", "cvat_job_id", "frame_index", "annotation_source", "box"} <= set(prov)
    assert record["crop_id"].startswith(manifest["snapshot"]["sha256"][:12])
    path = tmp_path / "out" / record["path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record["crop_sha256"]
    assert record["class_name"] in CLASSES


def test_labels_outside_class_map_are_rejected_not_unknown_class(snapshot, image_root, tmp_path):
    frame = snapshot["jobs"][0]["frames"][0]
    frame["shapes"] += [
        _shape(901, 7, [10, 10, 60, 60]),  # mapped name "person" is not in the taxonomy
        _shape(902, 99, [10, 10, 60, 60]),  # label_id absent from the map
    ]
    manifest = build(snapshot, image_root, tmp_path)
    reasons = manifest["counts"]["rejected_by_reason"]
    assert reasons == {"class_outside_taxonomy": 1, "label_not_in_label_map": 1}
    assert {r["class_name"] for r in manifest["crops"]} <= set(CLASSES)
    assert len(manifest["crops"]) == 24  # rejected shapes produce no crop and no 11th class


def test_unusable_shapes_are_rejected_with_reason(snapshot, image_root, tmp_path):
    frame = snapshot["jobs"][1]["frames"][0]
    frame["shapes"] += [
        _shape(911, 1, [10, 10, 12, 12]),  # too small
        _shape(912, 1, [0, 0, 5, 5, 9, 9]),  # polygon
        _shape(913, 1, [10, 10, 80, 80], outside=True),
        _shape(914, 1, [10, 10, 80, 80], rotation=15.0),
    ]
    reasons = build(snapshot, image_root, tmp_path)["counts"]["rejected_by_reason"]
    assert reasons == {"box_too_small": 1, "not_axis_aligned_rectangle": 2, "outside_shape": 1}


def test_group_never_spans_two_splits(snapshot, image_root, tmp_path):
    manifest = build(snapshot, image_root, tmp_path, split=SplitConfig(val=0.3, held_out=0.2))
    seen: dict[str, str] = {}
    for record in manifest["crops"]:
        assert seen.setdefault(record["source_group"], record["split"]) == record["split"]
    assert set(seen.values()) <= {"train", "val", "held_out"}
    assert "task" == manifest["split"]["group_by"]


def test_split_is_independent_of_order_and_stable(snapshot, image_root, tmp_path):
    first = build(snapshot, image_root, tmp_path)
    snapshot["jobs"].reverse()
    second = build_dataset(
        snapshot,
        image_root=image_root,
        out_dir=tmp_path / "out2",
        label_map=parse_label_map({str(k): v for k, v in LABELS.items()}),
    )
    split_of = lambda m: {r["source_group"]: r["split"] for r in m["crops"]}  # noqa: E731
    assert split_of(first) == split_of(second)


def test_rebuild_is_idempotent(snapshot, image_root, tmp_path):
    first = build(snapshot, image_root, tmp_path)
    text = (tmp_path / "out" / "dataset-manifest.json").read_text()
    again = build(snapshot, image_root, tmp_path)
    assert again["manifest_sha256"] == first["manifest_sha256"]
    assert (tmp_path / "out" / "dataset-manifest.json").read_text() == text


def test_manifest_hash_covers_content(snapshot, image_root, tmp_path):
    manifest = build(snapshot, image_root, tmp_path)
    snapshot["jobs"][0]["frames"][0]["shapes"][0]["points"] = [10, 20, 100, 70]
    changed = build(snapshot, image_root, tmp_path)
    assert changed["manifest_sha256"] != manifest["manifest_sha256"]


def test_frame_with_wrong_media_hash_is_not_cropped(snapshot, image_root, tmp_path):
    snapshot["jobs"][2]["frames"][0]["media"]["sha256"] = "0" * 64
    manifest = build(snapshot, image_root, tmp_path)
    assert manifest["counts"]["rejected_by_reason"] == {"frame_image_unavailable": 3}
    assert all(r["provenance"]["cvat_job_id"] != 103 for r in manifest["crops"])


def test_storage_key_cannot_escape_image_root(snapshot, image_root, tmp_path):
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"not an image")
    snapshot["jobs"][0]["frames"][0]["media"]["storage_key"] = "../secret.png"
    snapshot["jobs"][0]["frames"][0]["media"].pop("sha256")
    manifest = build(snapshot, image_root, tmp_path)
    assert manifest["counts"]["rejected_by_reason"] == {"frame_image_unavailable": 3}


def test_held_out_defaults_to_empty(snapshot, image_root, tmp_path):
    manifest = build(snapshot, image_root, tmp_path)
    assert "held_out" not in manifest["counts"]["by_split"]
    assert manifest["split"]["fit_allowed_splits"] == ["train", "val"]
    assert "calibration" in manifest["split"]["note"]


def test_invalid_inputs():
    with pytest.raises(DatasetError):
        SplitConfig(val=0.6, held_out=0.5)
    with pytest.raises(DatasetError):
        parse_label_map({"abc": "car"})
    with pytest.raises(DatasetError):
        build_dataset(
            {"schema_version": "other"}, image_root=Path("."), out_dir=Path("."), label_map={}
        )
    assert json.dumps(sorted(CLASSES))  # taxonomy stays the fixed 10 names
    assert len(CLASSES) == 10
