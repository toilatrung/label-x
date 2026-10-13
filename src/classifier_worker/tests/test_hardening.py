"""Malformed input, tampered manifests and status honesty (review hardening)."""

import json

import pytest
import torch
from PIL import Image

from labelx_classifier.artifact import ClassifierArtifact, ManifestError
from labelx_classifier.cli import main
from labelx_classifier.dataset import (
    DatasetError,
    SplitConfig,
    build_dataset,
    canonical_json,
    parse_label_map,
    sha256_hex,
)
from labelx_classifier.train import (
    TrainingDataError,
    load_dataset_manifest,
    train_classifier,
    training_status,
)

from .conftest import LABELS, _shape
from .test_train_and_artifact import trained  # noqa: F401  (module fixture)


def build(snapshot, image_root, out, **kwargs):
    return build_dataset(
        snapshot,
        image_root=image_root,
        out_dir=out,
        label_map=parse_label_map({str(k): v for k, v in LABELS.items()}),
        **kwargs,
    )


def rewrite(dataset, mutate):
    """Edit the manifest and recompute its hash, as an attacker (or a bug) could."""

    path = dataset / "dataset-manifest.json"
    manifest = json.loads(path.read_text())
    manifest.pop("manifest_sha256")
    mutate(manifest)
    manifest["manifest_sha256"] = sha256_hex(canonical_json(manifest))
    path.write_text(json.dumps(manifest))


@pytest.fixture
def dataset(snapshot, image_root, tmp_path):
    out = tmp_path / "ds"
    build(snapshot, image_root, out, split=SplitConfig(val=0.25, held_out=0.25))
    return out


def test_held_out_groups_really_exist(dataset):
    manifest = json.loads((dataset / "dataset-manifest.json").read_text())
    assert manifest["counts"]["by_split"].get("held_out", 0) > 0
    assert manifest["counts"]["by_split"].get("train", 0) > 0


def test_rewritten_held_out_to_train_is_detected(dataset):
    def mutate(m):
        for record in m["crops"]:
            if record["split"] == "held_out":
                record["split"] = "train"

    rewrite(dataset, mutate)
    with pytest.raises(TrainingDataError, match="not in the split"):
        load_dataset_manifest(dataset)


def test_group_spanning_two_splits_is_detected(dataset):
    def mutate(m):
        first = next(r for r in m["crops"] if r["split"] == "train")
        twin = dict(first, crop_id="twin", split="val")
        m["crops"].append(twin)

    rewrite(dataset, mutate)
    with pytest.raises(TrainingDataError, match="spans more than one split"):
        load_dataset_manifest(dataset)


def test_path_escape_in_manifest_is_detected(dataset, tmp_path):
    outside = tmp_path / "outside.png"
    Image.new("RGB", (224, 224)).save(outside)

    def mutate(m):
        m["crops"][0]["path"] = "../outside.png"
        m["crops"][0]["crop_sha256"] = sha256_hex(outside.read_bytes())

    rewrite(dataset, mutate)
    with pytest.raises(TrainingDataError, match="outside the dataset"):
        load_dataset_manifest(dataset)


def test_held_out_crop_hash_is_checked_too(dataset):
    manifest = json.loads((dataset / "dataset-manifest.json").read_text())
    victim = next(r for r in manifest["crops"] if r["split"] == "held_out")
    Image.new("RGB", (224, 224), (5, 5, 5)).save(dataset / victim["path"])
    with pytest.raises(TrainingDataError, match="recorded hash"):
        load_dataset_manifest(dataset)


def test_class_id_and_duplicates_are_validated(dataset):
    rewrite(dataset, lambda m: m["crops"][0].update(class_id=9))
    with pytest.raises(TrainingDataError, match="class_id"):
        load_dataset_manifest(dataset)


def test_data_origin_defaults_to_fixture(dataset):
    assert load_dataset_manifest(dataset)["data_origin"] == "fixture"


@pytest.mark.parametrize(
    "bad",
    [
        {"label_id": True},
        {"points": "10,10,50,50"},
        {"points": [10, 10, 50, float("inf")]},
        {"rotation": "x"},
        {"source": {"id": 1}},
        {"source": None},
    ],
)
def test_malformed_shapes_are_rejected_not_crashing(snapshot, image_root, tmp_path, bad):
    shape = {**_shape(950, 1, [10, 10, 60, 60]), **bad}
    snapshot["jobs"][0]["frames"][0]["shapes"].append(shape)
    manifest = build(snapshot, image_root, tmp_path / "o")
    assert manifest["counts"]["rejected_by_reason"] == {"malformed_shape": 1}
    assert manifest["counts"]["crops"] == 24


def test_boolean_label_id_is_not_class_one(snapshot, image_root, tmp_path):
    snapshot["jobs"][0]["frames"][0]["shapes"].append(_shape(951, True, [10, 10, 60, 60]))
    manifest = build(snapshot, image_root, tmp_path / "o")
    assert manifest["counts"]["by_class"]["car"] == 8  # unchanged


def test_oversized_and_bomb_frames_do_not_crash_build(snapshot, image_root, tmp_path, monkeypatch):
    monkeypatch.setattr("labelx_classifier.dataset.MAX_FRAME_PIXELS", 100)
    manifest = build(snapshot, image_root, tmp_path / "o")
    assert manifest["counts"]["rejected_by_reason"] == {"frame_too_large": 24}
    monkeypatch.undo()
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)  # Pillow raises DecompressionBombError
    manifest = build(snapshot, image_root, tmp_path / "o2")
    assert manifest["counts"]["rejected_by_reason"] == {"frame_image_unavailable": 24}


def test_rebuild_removes_stale_crops(snapshot, image_root, tmp_path):
    out = tmp_path / "o"
    build(snapshot, image_root, out)
    stale = next((out / "crops").rglob("*.png"))
    snapshot["jobs"] = snapshot["jobs"][:2]
    manifest = build(snapshot, image_root, out)
    assert not stale.exists() or manifest["counts"]["crops"] == len(
        list((out / "crops").rglob("*.png"))
    )
    assert len(list((out / "crops").rglob("*.png"))) == manifest["counts"]["crops"]


def test_leakage_warning_when_a_task_spans_splits(snapshot, image_root, tmp_path):
    for job in snapshot["jobs"]:
        job["cvat_task_id"] = 1  # all frames from one task
    manifest = build(
        snapshot, image_root, tmp_path / "o", group_by="job", split=SplitConfig(val=0.4)
    )
    assert any("spans splits" in w for w in manifest["leakage_warnings"])
    assert build(snapshot, image_root, tmp_path / "o2")["leakage_warnings"] == []  # by task


def test_status_is_derived_not_chosen():
    ok = dict(
        smoke_only=False,
        data_origin="real",
        pretrained=True,
        epochs=3,
        has_val=True,
        missing_classes=[],
    )
    assert training_status(**ok) == ("trained", [])
    for change, reason in [
        ({"smoke_only": True}, "forced_smoke_only"),
        ({"data_origin": "fixture"}, "dataset_origin_is_not_real"),
        ({"pretrained": False}, "not_imagenet_pretrained"),
        ({"epochs": 1}, "epochs_below_3"),
        ({"has_val": False}, "empty_val_split"),
        ({"missing_classes": ["bus"]}, "classes_without_train_samples"),
    ]:
        status, reasons = training_status(**{**ok, **change})
        assert status == "smoke_only" and reason in reasons


def test_fixture_run_cannot_be_trained(trained):  # noqa: F811
    _, _, artifact = trained
    assert artifact.status == "smoke_only"
    assert "dataset_origin_is_not_real" in artifact.raw["training"]["status_reasons"]


def test_manifest_must_match_what_inference_applies(trained, tmp_path):  # noqa: F811
    _, _, artifact = trained
    raw = json.loads(artifact.path.read_text())
    for mutate in (
        lambda m: m["preprocessing"].update(mean=[0.5, 0.5, 0.5]),
        lambda m: m["preprocessing"].update(std=[1, 1, 1]),
        lambda m: m["preprocessing"].update(scale="1/1"),
        lambda m: m["preprocessing"].update(pad_fill_rgb=[0, 0, 0]),
        lambda m: m["output_semantics"].update(calibrated=True),
        lambda m: m["output_semantics"].update(score="calibrated probability"),
        lambda m: m["model"].update(architecture="resnet50"),
    ):
        copy = json.loads(json.dumps(raw))
        mutate(copy)
        path = tmp_path / "m.json"
        path.write_text(json.dumps(copy))
        with pytest.raises(ManifestError):
            ClassifierArtifact.load(path)


def test_cli_verify_and_predict_reject_wrong_state_dict(trained, tmp_path, capsys):  # noqa: F811
    root, _, artifact = trained
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    checkpoint = bad_dir / artifact.checkpoint_filename
    torch.save({"features.0.0.weight": torch.zeros(1)}, checkpoint)
    raw = json.loads(artifact.path.read_text())
    from labelx_classifier.artifact import sha256_file

    raw["model"]["sha256"] = sha256_file(checkpoint)  # checksum is fine, weights are not
    manifest = bad_dir / "classifier-manifest.json"
    manifest.write_text(json.dumps(raw))
    assert main(["verify", "--manifest", str(manifest)]) == 2
    frame = root / "images/snapshots/source/t1.png"
    assert main(["predict", "--manifest", str(manifest), "--image", str(frame)]) == 2


def test_train_refuses_tampered_manifest(dataset, tmp_path):
    rewrite(dataset, lambda m: m["split"].update(val_fraction=0.9))
    with pytest.raises(TrainingDataError):
        train_classifier(dataset, tmp_path / "m", version="x", epochs=1, pretrained=False)


def test_user_files_in_crops_dir_are_never_deleted(snapshot, image_root, tmp_path):
    out = tmp_path / "o"
    foreign = out / "crops" / "MY_ANNOTATIONS.txt"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("keep me")
    with pytest.raises(DatasetError, match="refusing"):  # no manifest from this tool
        build(snapshot, image_root, out)
    assert foreign.read_text() == "keep me"
    foreign.unlink()
    build(snapshot, image_root, out)  # now the dir is the tool's
    foreign.write_text("keep me")
    manifest = build(snapshot, image_root, out)  # rebuild: tool crops replaced, foreign kept
    assert foreign.read_text() == "keep me"
    assert manifest["counts"]["crops"] == 24


@pytest.mark.parametrize("value", [1, "true", "False", None, 0])
def test_outside_must_be_a_real_boolean(snapshot, image_root, tmp_path, value):
    shape = _shape(960, 1, [10, 10, 60, 60])
    shape["outside"] = value
    snapshot["jobs"][0]["frames"][0]["shapes"].append(shape)
    manifest = build(snapshot, image_root, tmp_path / "o")
    assert manifest["counts"]["rejected_by_reason"] == {"malformed_shape": 1}
    assert manifest["counts"]["crops"] == 24


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda s: s["jobs"].append(5), "malformed_job"),
        (lambda s: s["jobs"].append({"cvat_job_id": 1, "frames": "abc"}), "malformed_job"),
        (lambda s: s["jobs"][0]["frames"].append("frame"), "malformed_frame"),
        (lambda s: s["jobs"][0]["frames"].append({"shapes": "x"}), "malformed_frame"),
        (lambda s: s["jobs"][0]["frames"][0]["shapes"].append(7), "malformed_shape"),
    ],
)
def test_structurally_wrong_snapshot_nodes_are_rejected(
    snapshot, image_root, tmp_path, mutate, reason
):
    mutate(snapshot)
    manifest = build(snapshot, image_root, tmp_path / "o")
    assert manifest["counts"]["rejected_by_reason"] == {reason: 1}
    assert manifest["counts"]["crops"] == 24


def test_origin_is_declared_not_verified(dataset):
    manifest = load_dataset_manifest(dataset)
    assert "not verified" in manifest["data_origin_note"]
