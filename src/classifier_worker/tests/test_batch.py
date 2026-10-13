import json

import pytest
from PIL import Image

from labelx_classifier.cli import main
from labelx_classifier.infer import Classifier, predict_batch

from .test_train_and_artifact import trained  # noqa: F401  (module fixture)


@pytest.fixture
def items(trained, tmp_path):  # noqa: F811
    root, _, _ = trained
    ready = tmp_path / "ready.png"
    Image.new("RGB", (224, 224), (10, 200, 10)).save(ready)
    small = tmp_path / "small.png"
    Image.new("RGB", (100, 100)).save(small)
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image")
    frame = str(root / "images/snapshots/source/t1.png")
    return [
        {"id": "b-box", "image": frame, "box": [10, 20, 110, 80]},
        {"id": "a-ready", "image": str(ready)},
        {"id": "c-wrong-size", "image": str(small)},
        {"id": "d-missing", "image": str(tmp_path / "nope.png")},
        {"id": "e-broken", "image": str(broken)},
        {"id": "f-tiny-box", "image": frame, "box": [10, 10, 12, 12]},
        {"id": "g-bad-box", "image": frame, "box": [1, 2, 3]},
        {"id": "h-no-image"},
    ]


def test_one_bad_item_does_not_fail_the_others(trained, items):  # noqa: F811
    _, _, artifact = trained
    out = predict_batch(Classifier.load(artifact.path), items)
    by_id = {row["id"]: row for row in out["results"]}
    assert [row["id"] for row in out["results"]] == sorted(by_id)
    assert by_id["a-ready"]["ok"] and by_id["b-box"]["ok"]
    for bad in ("c-wrong-size", "d-missing", "e-broken", "g-bad-box", "h-no-image"):
        assert by_id[bad]["ok"] is False and by_id[bad]["reason"] == "invalid_crop"
    assert by_id["f-tiny-box"] == {
        "id": "f-tiny-box",
        "ok": False,
        "reason": "box_too_small",
        "detail": by_id["f-tiny-box"]["detail"],
    }
    assert len(by_id["a-ready"]["prediction"]["top3"]) == 3


def test_output_carries_checkpoint_identity(trained, items):  # noqa: F811
    _, _, artifact = trained
    out = predict_batch(Classifier.load(artifact.path), items[:1])
    assert out["checkpoint"] == {
        "version": artifact.version,
        "sha256": artifact.sha256,
        "status": "smoke_only",
        "class_map_version": "bdd100k-det-10-v1",
    }


def test_cli_predict_batch(trained, items, tmp_path, capsys):  # noqa: F811
    _, _, artifact = trained
    path = tmp_path / "in.json"
    path.write_text(json.dumps(items))
    assert main(["predict-batch", "--manifest", str(artifact.path), "--input", str(path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert sum(1 for r in out["results"] if r["ok"]) == 2
    path.write_text(json.dumps({"id": "x"}))
    assert main(["predict-batch", "--manifest", str(artifact.path), "--input", str(path)]) == 2


def test_empty_batch_is_valid(trained):  # noqa: F811
    _, _, artifact = trained
    assert predict_batch(Classifier.load(artifact.path), [])["results"] == []
