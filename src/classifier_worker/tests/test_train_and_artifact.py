"""Training, packaging and inference on synthetic crops (random init: no download, no real data).

These prove the pipeline mechanics only. They say nothing about accuracy on real BDD100K/LabelX
data and the produced checkpoints are ``smoke_only``.
"""

import json

import pytest
import torch
from PIL import Image

from labelx_classifier import artifact as artifact_module
from labelx_classifier.artifact import ChecksumMismatchError, ClassifierArtifact, ManifestError
from labelx_classifier.cli import main
from labelx_classifier.dataset import SplitConfig, build_dataset, parse_label_map
from labelx_classifier.infer import Classifier
from labelx_classifier.taxonomy import CLASSES
from labelx_classifier.train import (
    TrainingDataError,
    _records,
    load_dataset_manifest,
    train_classifier,
)

from .conftest import LABELS, make_snapshot


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    root = tmp_path_factory.mktemp("w")
    snapshot = make_snapshot(root / "images")
    dataset = root / "dataset"
    build_dataset(
        snapshot,
        image_root=root / "images",
        out_dir=dataset,
        label_map=parse_label_map({str(k): v for k, v in LABELS.items()}),
        split=SplitConfig(val=0.25),
    )
    artifact = train_classifier(
        dataset,
        root / "model",
        version="smoke-test",
        status="smoke_only",
        epochs=1,
        batch_size=8,
        device="cpu",
        pretrained=False,
    )
    return root, dataset, artifact


def test_manifest_records_what_was_really_done(trained):
    _, dataset, artifact = trained
    training = artifact.raw["training"]
    assert artifact.status == "smoke_only"
    assert training["fit_split"] == "train" and training["held_out_used"] is False
    assert (
        training["dataset_manifest_sha256"]
        == json.loads((dataset / "dataset-manifest.json").read_text())["manifest_sha256"]
    )
    assert training["pretrained_init"] is False and len(training["epoch_train_loss"]) == 1
    assert artifact.raw["output_semantics"]["calibrated"] is False
    assert artifact.raw["preprocessing"]["input_size"] == 224
    assert list(artifact.classes) == list(CLASSES)


def test_load_verifies_checksum_and_infers_top3(trained):
    root, _, artifact = trained
    artifact.verify_checkpoint()
    classifier = Classifier.load(artifact.path)
    crops = [Image.new("RGB", (224, 224), color) for color in [(200, 30, 30), (30, 200, 30)]]
    predictions = classifier.predict(crops)
    assert len(predictions) == 2
    for prediction in predictions:
        scores = [score for _, _, score in prediction.top3]
        assert len(prediction.top3) == 3
        assert scores == sorted(scores, reverse=True)
        assert prediction.score == scores[0]
        assert prediction.margin == pytest.approx(scores[0] - scores[1])
        assert 0.0 < sum(scores) <= 1.0 + 1e-6
        assert prediction.top3[0][1] == CLASSES[prediction.top3[0][0]]
        assert prediction.as_dict()["calibrated"] is False


def test_tampered_checkpoint_is_rejected_before_loading(trained, monkeypatch):
    _, _, artifact = trained
    corrupt = artifact.checkpoint_path.read_bytes()
    original = corrupt
    try:
        artifact.checkpoint_path.write_bytes(corrupt[:-1] + bytes([corrupt[-1] ^ 1]))
        monkeypatch.setattr(
            torch, "load", lambda *a, **k: pytest.fail("torch.load ran on an unverified file")
        )
        with pytest.raises(ChecksumMismatchError):
            artifact.load_model()
        with pytest.raises(ChecksumMismatchError):
            Classifier.load(artifact.path)
    finally:
        artifact.checkpoint_path.write_bytes(original)


def test_checkpoint_is_loaded_weights_only(trained, monkeypatch):
    _, _, artifact = trained
    seen = {}
    real_load = torch.load

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real_load(*args, **kwargs)

    monkeypatch.setattr(artifact_module.torch, "load", spy)
    artifact.load_model()
    assert seen.get("weights_only") is True


def test_manifest_validation(trained, tmp_path):
    _, _, artifact = trained
    raw = json.loads(artifact.path.read_text())

    def write(mutate):
        copy = json.loads(json.dumps(raw))
        mutate(copy)
        path = tmp_path / "m.json"
        path.write_text(json.dumps(copy))
        return path

    for mutate in (
        lambda m: m["model"].update(sha256="xyz"),
        lambda m: m["model"].pop("sha256"),
        lambda m: m["class_mapping"].update(classes=list(CLASSES[:9])),
        lambda m: m["class_mapping"].update(classes=[*CLASSES[:9], "unknown"]),
        lambda m: m["preprocessing"].update(input_size=256),
        lambda m: m["training"].update(status="validated"),
        lambda m: m["model"].update(checkpoint_filename="../evil.pth"),
        lambda m: m.update(schema_version="other"),
    ):
        with pytest.raises(ManifestError):
            ClassifierArtifact.load(write(mutate))


def test_training_refuses_empty_train_split(tmp_path):
    snapshot = make_snapshot(tmp_path / "images", tasks=2)
    build_dataset(
        snapshot,
        image_root=tmp_path / "images",
        out_dir=tmp_path / "d",
        label_map=parse_label_map({str(k): v for k, v in LABELS.items()}),
        split=SplitConfig(val=0.9999, held_out=0.0),
    )
    with pytest.raises(TrainingDataError):
        train_classifier(
            tmp_path / "d",
            tmp_path / "m",
            version="x",
            status="smoke_only",
            epochs=1,
            pretrained=False,
        )


def test_held_out_split_cannot_be_read():
    with pytest.raises(TrainingDataError):
        _records({"crops": []}, "held_out")


def test_dataset_integrity_is_checked(trained):
    _, dataset, _ = trained
    manifest = load_dataset_manifest(dataset)
    victim = next(dataset / r["path"] for r in manifest["crops"] if r["split"] == "train")
    data = victim.read_bytes()
    try:
        Image.new("RGB", (224, 224), (1, 2, 3)).save(victim)
        with pytest.raises(TrainingDataError):
            load_dataset_manifest(dataset)
    finally:
        victim.write_bytes(data)
    path = dataset / "dataset-manifest.json"
    text = path.read_text()
    try:
        path.write_text(text.replace('"crops": 24', '"crops": 25', 1))
        with pytest.raises(TrainingDataError):
            load_dataset_manifest(dataset)
    finally:
        path.write_text(text)


def test_cli_verify_and_predict(trained, capsys):
    root, _, artifact = trained
    assert main(["verify", "--manifest", str(artifact.path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["verified"] is True and out["status"] == "smoke_only"
    frame = root / "images/snapshots/source/t1.png"
    assert (
        main(
            [
                "predict",
                "--manifest",
                str(artifact.path),
                "--image",
                str(frame),
                "--box",
                "10",
                "20",
                "110",
                "80",
            ]
        )
        == 0
    )
    assert len(json.loads(capsys.readouterr().out)["top3"]) == 3
    assert main(["verify", "--manifest", str(root / "missing.json")]) == 2
