import json
import os
import shutil

import pytest
from PIL import Image

from labelx_classifier import infer
from labelx_classifier.cli import main
from labelx_classifier.infer import BatchError, Classifier, predict_batch

from .test_train_and_artifact import trained  # noqa: F401  (module fixture)


@pytest.fixture
def workdir(trained, tmp_path):  # noqa: F811
    """A root directory holding every image the batch may read."""
    root, _, _ = trained
    shutil.copy(root / "images/snapshots/source/t1.png", tmp_path / "frame.png")
    Image.new("RGB", (224, 224), (10, 200, 10)).save(tmp_path / "ready.png")
    Image.new("RGB", (100, 40), (200, 10, 10)).save(tmp_path / "wide.png")
    Image.new("RGB", (2, 2)).save(tmp_path / "tiny.png")
    (tmp_path / "broken.png").write_bytes(b"not an image")
    return tmp_path


@pytest.fixture
def items():
    return [
        {"id": "b-box", "image": "frame.png", "box": [10, 20, 110, 80]},
        {"id": "a-ready", "image": "ready.png"},
        {"id": "c-other-size", "image": "wide.png"},
        {"id": "d-missing", "image": "nope.png"},
        {"id": "e-broken", "image": "broken.png"},
        {"id": "f-tiny-box", "image": "frame.png", "box": [10, 10, 12, 12]},
        {"id": "g-bad-box", "image": "frame.png", "box": [1, 2, 3]},
        {"id": "h-no-image"},
        {"id": "i-tiny", "image": "tiny.png"},
    ]


def clf(trained):  # noqa: F811
    return Classifier.load(trained[2].path)


def test_one_bad_item_does_not_fail_the_others(trained, items, workdir):  # noqa: F811
    out = predict_batch(clf(trained), items, image_root=workdir)
    by_id = {row["id"]: row for row in out["results"]}
    assert [row["id"] for row in out["results"]] == [item["id"] for item in items]  # input order
    for good in ("a-ready", "b-box", "c-other-size"):
        assert by_id[good]["ok"] and len(by_id[good]["prediction"]["top3"]) == 3
    for bad in ("d-missing", "e-broken", "g-bad-box", "h-no-image"):
        assert by_id[bad] == {"id": bad, "ok": False, "reason": "invalid_crop"}
    assert by_id["f-tiny-box"]["reason"] == by_id["i-tiny"]["reason"] == "box_too_small"


def test_output_never_contains_paths_or_raw_errors(trained, items, workdir):  # noqa: F811
    text = json.dumps(predict_batch(clf(trained), items, image_root=workdir))
    assert str(workdir) not in text and "Errno" not in text and "Traceback" not in text
    assert "detail" not in text


def test_output_carries_checkpoint_identity(trained, items, workdir):  # noqa: F811
    out = predict_batch(clf(trained), items[:1], image_root=workdir)
    assert out["checkpoint"] == {
        "version": trained[2].version,
        "sha256": trained[2].sha256,
        "status": "smoke_only",
        "class_map_version": "bdd100k-det-10-v1",
    }


def test_non_object_items_and_bad_ids_do_not_crash_the_batch(trained, workdir):  # noqa: F811
    batch = [
        "abc",
        None,
        7,
        {"id": 5, "image": "ready.png"},
        {"image": "ready.png"},
        {"id": "", "image": "ready.png"},
        {"id": "ok", "image": "ready.png"},
    ]
    results = predict_batch(clf(trained), batch, image_root=workdir)["results"]
    assert [r.get("reason") for r in results] == [
        "invalid_item",
        "invalid_item",
        "invalid_item",
        "missing_id",
        "missing_id",
        "missing_id",
        None,
    ]
    assert results[-1]["ok"] and results[-1]["id"] == "ok"


def test_duplicate_ids_are_rejected_and_order_is_kept(trained, workdir):  # noqa: F811
    batch = [
        {"id": "z", "image": "ready.png"},
        {"id": "dup", "image": "ready.png"},
        {"id": "a", "image": "ready.png"},
        {"id": "dup", "image": "wide.png"},
    ]
    results = predict_batch(clf(trained), batch, image_root=workdir)["results"]
    assert [r["id"] for r in results] == ["z", "dup", "a", "dup"]  # not sorted by id
    assert [r["ok"] for r in results] == [True, False, True, False]
    assert results[1]["reason"] == results[3]["reason"] == "duplicate_id"


def test_decompression_bomb_fails_only_that_item(trained, workdir, monkeypatch):  # noqa: F811
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)  # wide.png (4000 px) trips the guard
    batch = [{"id": "ok", "image": "tiny.png"}, {"id": "bomb", "image": "frame.png"}]
    results = predict_batch(clf(trained), batch, image_root=workdir)["results"]
    assert results[1] == {"id": "bomb", "ok": False, "reason": "invalid_crop"}
    assert results[0]["reason"] == "box_too_small"  # processed normally, not crashed


def test_declared_huge_png_does_not_crash_batch(trained, workdir):  # noqa: F811
    import struct
    import zlib

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    bomb = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 20000, 20000, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00"))
        + chunk(b"IEND", b"")
    )
    (workdir / "bomb.png").write_bytes(bomb)
    batch = [{"id": "bomb", "image": "bomb.png"}, {"id": "ok", "image": "ready.png"}]
    results = predict_batch(clf(trained), batch, image_root=workdir)["results"]
    assert results[0] == {"id": "bomb", "ok": False, "reason": "invalid_crop"}
    assert results[1]["ok"]


def test_paths_outside_root_are_rejected_including_symlinks(trained, workdir, tmp_path_factory):  # noqa: F811
    outside = tmp_path_factory.mktemp("outside")
    Image.new("RGB", (224, 224)).save(outside / "secret.png")
    os.symlink(outside / "secret.png", workdir / "link.png")
    os.symlink(outside, workdir / "linkdir")
    batch = [
        {"id": "abs", "image": str(outside / "secret.png")},
        {"id": "dots", "image": "../" + outside.name + "/secret.png"},
        {"id": "link", "image": "link.png"},
        {"id": "linkdir", "image": "linkdir/secret.png"},
        {"id": "inside", "image": "ready.png"},
    ]
    results = predict_batch(clf(trained), batch, image_root=workdir)["results"]
    assert [r["ok"] for r in results] == [False, False, False, False, True]
    assert {r["reason"] for r in results[:4]} == {"invalid_crop"}


def test_large_batches_are_forwarded_in_chunks(trained, workdir, monkeypatch):  # noqa: F811
    sizes = []
    real = Classifier._predict_chunk

    def spy(self, crops):
        sizes.append(len(crops))
        return real(self, crops)

    monkeypatch.setattr(infer, "PREDICT_CHUNK", 2)
    monkeypatch.setattr(Classifier, "_predict_chunk", spy)
    batch = [{"id": str(i), "image": "ready.png"} for i in range(5)]
    results = predict_batch(clf(trained), batch, image_root=workdir)["results"]
    assert sizes == [2, 2, 1] and all(r["ok"] for r in results)


def test_batch_size_is_capped(trained, workdir, monkeypatch):  # noqa: F811
    monkeypatch.setattr(infer, "MAX_BATCH_ITEMS", 3)
    with pytest.raises(BatchError):
        predict_batch(clf(trained), [{"id": str(i)} for i in range(4)], image_root=workdir)


def test_cli_predict_batch(trained, items, workdir, capsys):  # noqa: F811
    path = workdir / "in.json"
    path.write_text(json.dumps(items))
    args = ["predict-batch", "--manifest", str(trained[2].path), "--input", str(path)]
    assert main([*args, "--image-root", str(workdir)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert sum(1 for r in out["results"] if r["ok"]) == 3
    path.write_text(json.dumps({"id": "x"}))
    assert main([*args, "--image-root", str(workdir)]) == 2
    path.write_text(json.dumps([{"id": str(i)} for i in range(infer.MAX_BATCH_ITEMS + 1)]))
    assert main([*args, "--image-root", str(workdir)]) == 2  # over the cap


def test_cli_batch_with_bomb_still_prints_json(trained, workdir, capsys):  # noqa: F811
    path = workdir / "in.json"
    path.write_text(
        json.dumps([{"id": "a", "image": "broken.png"}, {"id": "b", "image": "ready.png"}])
    )
    code = main(
        [
            "predict-batch",
            "--manifest",
            str(trained[2].path),
            "--input",
            str(path),
            "--image-root",
            str(workdir),
        ]
    )
    assert code == 0 and [r["ok"] for r in json.loads(capsys.readouterr().out)["results"]] == [
        False,
        True,
    ]


def test_empty_batch_is_valid(trained, workdir):  # noqa: F811
    assert predict_batch(clf(trained), [], image_root=workdir)["results"] == []


def test_cli_exit_codes_distinguish_checksum_and_manifest_errors(trained, tmp_path):  # noqa: F811
    artifact = trained[2]
    original = artifact.checkpoint_path.read_bytes()
    try:
        artifact.checkpoint_path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        assert main(["verify", "--manifest", str(artifact.path)]) == 3
    finally:
        artifact.checkpoint_path.write_bytes(original)
    bad = tmp_path / "bad.json"
    raw = json.loads(artifact.path.read_text())
    raw["model"]["sha256"] = "nope"
    bad.write_text(json.dumps(raw))
    assert main(["verify", "--manifest", str(bad)]) == 4
