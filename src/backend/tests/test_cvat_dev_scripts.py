import importlib.util
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]


def load_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / "development" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bdd100k_membership_uses_official_filenames_not_learner_folders(tmp_path: Path) -> None:
    module = load_script("cvat_sample")
    official = tmp_path / "official"
    (official / "train").mkdir(parents=True)
    (official / "val").mkdir()
    (official / "train" / "train.jpg").touch()
    (official / "val" / "val.jpg").touch()
    learner = tmp_path / "learner" / "misleading-train-folder"
    learner.mkdir(parents=True)
    paths = [learner / "val.jpg", learner / "other.jpg"]

    assert module.bdd100k_membership(paths, official) == {
        "train": 0,
        "val": 1,
        "not_bdd100k": 1,
    }


def test_sample_validation_rejects_duplicate_upload_filenames(tmp_path: Path) -> None:
    module = load_script("cvat_sample")
    for split in ("train", "val"):
        directory = tmp_path / split
        directory.mkdir()
        Image.new("RGB", (10, 10)).save(directory / "same.jpg")
    manifest = {
        "labels": [{"name": "car"}],
        "images": [
            {"file_name": "train/same.jpg", "annotations": []},
            {"file_name": "val/same.jpg", "annotations": []},
        ],
    }

    with pytest.raises(ValueError, match="duplicate upload filenames"):
        module.validate_sample(tmp_path, manifest)


def test_provisioner_token_cannot_equal_backend_service_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_script("cvat_sample")
    monkeypatch.setenv("CVAT_SERVICE_TOKEN", "same-secret")
    monkeypatch.setenv("CVAT_PROVISIONER_TOKEN", "same-secret")
    monkeypatch.setattr(
        sys,
        "argv",
        ["cvat_sample.py", "--images", ".", "--annotations", "manifest.json"],
    )

    with pytest.raises(SystemExit):
        module.parse_args()


def test_existing_project_taxonomy_must_match(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_script("cvat_sample")
    client = object.__new__(module.ProvisioningClient)

    def fake_json(method: str, endpoint: str, **_kwargs: object) -> dict[str, object]:
        if endpoint == "api/projects":
            return {"results": [{"id": 4, "name": "labelx-dev"}]}
        return {"id": 4, "labels": [{"name": "person", "type": "rectangle"}]}

    monkeypatch.setattr(client, "_json", fake_json)
    with pytest.raises(ValueError, match="taxonomy differs"):
        client.find_or_create_project("labelx-dev", [{"name": "car", "type": "rectangle"}])


def test_existing_project_taxonomy_follows_cvat_labels_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_script("cvat_sample")
    client = object.__new__(module.ProvisioningClient)
    calls: list[tuple[str, str, object]] = []

    def fake_json(method: str, endpoint: str, **kwargs: object) -> dict[str, object]:
        calls.append((method, endpoint, kwargs.get("params")))
        if endpoint == "api/projects":
            return {"results": [{"id": 5, "name": "labelx-dev-bdd100k"}]}
        if endpoint == "api/projects/5":
            return {"id": 5, "labels": {"url": "http://cvat/api/labels?project_id=5"}}
        if endpoint == "api/labels":
            return {
                "results": [
                    {
                        "name": "car",
                        "type": "rectangle",
                        "color": "#845ef7",
                        "attributes": [],
                    }
                ]
            }
        raise AssertionError(endpoint)

    monkeypatch.setattr(client, "_json", fake_json)

    assert (
        client.find_or_create_project(
            "labelx-dev-bdd100k",
            [{"name": "car", "type": "rectangle", "color": "#845ef7"}],
        )
        == 5
    )
    assert (
        "GET",
        "api/labels",
        {"project_id": 5, "page_size": 100},
    ) in calls


def write_yolo_export(
    path: Path,
    images: list[str],
    labels: dict[str, str],
    *,
    class_name: str = "GreenSM",
) -> None:
    image_buffer = BytesIO()
    Image.new("RGB", (10, 10)).save(image_buffer, format="JPEG")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("data.yaml", f"names:\n  0: {class_name}\npath: .\ntrain: train.txt\n")
        archive.writestr("train.txt", "".join(f"./images/train/{name}\n" for name in images))
        for name in images:
            archive.writestr(f"images/train/{name}", image_buffer.getvalue())
        for stem, content in labels.items():
            archive.writestr(f"labels/train/{stem}.txt", content)


def write_annotations_only_yolo_export(
    path: Path,
    images: list[str],
    labels: dict[str, str],
) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "data.yaml",
            "names:\n  0: car\npath: .\nval: val.txt\n",
        )
        archive.writestr(
            "val.txt",
            "".join(f"data/images/val/{name}\n" for name in images),
        )
        for stem, content in labels.items():
            archive.writestr(f"labels/val/{stem}.txt", content)


def test_learner_audit_classifies_by_official_bdd100k_names(tmp_path: Path) -> None:
    module = load_script("learner_annotation_audit")
    official = tmp_path / "bdd100k"
    (official / "train").mkdir(parents=True)
    (official / "val").mkdir()
    (official / "train" / "official-train.jpg").touch()
    (official / "val" / "official-val.jpg").touch()
    export = tmp_path / "learner.zip"
    write_yolo_export(
        export,
        ["official-val.jpg", "greensm-1.jpg"],
        {"official-val": "0 0.5 0.5 0.2 0.3\n"},
    )

    receipt = module.build_receipt([export], official)

    assert receipt["totals"] == {
        "exports": 1,
        "images": 2,
        "label_files": 1,
        "boxes": 1,
        "out_of_bounds_boxes": 0,
        "out_of_bounds_images": 0,
        "annotated_images": 1,
        "without_annotations": 1,
        "empty_or_unlabeled_images": 1,
        "membership": {"train": 0, "val": 1, "not_bdd100k": 1},
    }
    manifest = module.materialize_labelx_manifest(
        [export], receipt, tmp_path / "images", tmp_path / "manifest.json"
    )
    assert len(manifest["images"]) == 2
    annotated = next(item for item in manifest["images"] if item["file_name"] == "official-val.jpg")
    assert annotated["annotations"][0]["bbox"] == pytest.approx([4.0, 3.5, 6.0, 6.5])


def test_learner_audit_rejects_invalid_yolo_coordinates(tmp_path: Path) -> None:
    module = load_script("learner_annotation_audit")
    official = tmp_path / "bdd100k"
    (official / "train").mkdir(parents=True)
    (official / "val").mkdir()
    export = tmp_path / "learner.zip"
    write_yolo_export(export, ["greensm.jpg"], {"greensm": "0 1.2 0.5 0.2 0.3\n"})

    with pytest.raises(ValueError, match="out of range"):
        module.build_receipt([export], official)


def test_learner_audit_reports_and_excludes_out_of_bounds_image(tmp_path: Path) -> None:
    module = load_script("learner_annotation_audit")
    official = tmp_path / "bdd100k"
    (official / "train").mkdir(parents=True)
    (official / "val").mkdir()
    export = tmp_path / "learner.zip"
    write_yolo_export(export, ["greensm.jpg"], {"greensm": "0 0.05 0.5 0.2 0.3\n"})

    receipt = module.build_receipt([export], official)
    manifest = module.materialize_labelx_manifest(
        [export], receipt, tmp_path / "images", tmp_path / "manifest.json"
    )

    assert receipt["totals"]["out_of_bounds_boxes"] == 1
    assert receipt["totals"]["out_of_bounds_images"] == 1
    assert manifest["images"] == []


def test_learner_audit_rejects_cross_export_duplicates(tmp_path: Path) -> None:
    module = load_script("learner_annotation_audit")
    official = tmp_path / "bdd100k"
    (official / "train").mkdir(parents=True)
    (official / "val").mkdir()
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    write_yolo_export(first, ["same.jpg"], {})
    write_yolo_export(second, ["same.jpg"], {})

    with pytest.raises(ValueError, match="duplicate image names"):
        module.build_receipt([first, second], official)


def test_strict_bdd100k_validation_rejects_non_bdd_and_foreign_taxonomy(tmp_path: Path) -> None:
    module = load_script("learner_annotation_audit")
    official = tmp_path / "bdd100k"
    (official / "train").mkdir(parents=True)
    (official / "val").mkdir()
    export = tmp_path / "learner.zip"
    write_yolo_export(export, ["greensm.jpg"], {"greensm": "0 0.5 0.5 0.2 0.3\n"})

    receipt = module.build_receipt([export], official)

    assert module.bdd100k_validation_errors(receipt) == [
        "1 image(s) are not in official BDD100K listings",
        "learner.zip: unsupported BDD100K class(es): GreenSM",
    ]


def test_bdd100k_manifest_uses_official_image_and_reports_missing_annotations(
    tmp_path: Path,
) -> None:
    module = load_script("learner_annotation_audit")
    official = tmp_path / "bdd100k"
    (official / "train").mkdir(parents=True)
    (official / "val").mkdir()
    Image.new("RGB", (20, 10)).save(official / "val" / "official-val.jpg")
    Image.new("RGB", (30, 20)).save(official / "val" / "missing-val.jpg")
    export = tmp_path / "learner.zip"
    write_yolo_export(
        export,
        ["official-val.jpg", "missing-val.jpg"],
        {"official-val": "0 0.5 0.5 0.2 0.4\n", "missing-val": ""},
        class_name="car",
    )

    receipt = module.build_receipt([export], official)
    manifest = module.materialize_bdd100k_manifest(
        [export], receipt, official, tmp_path / "manifest.json"
    )
    importer = load_script("cvat_sample")

    assert module.bdd100k_validation_errors(receipt) == []
    assert receipt["totals"]["annotated_images"] == 1
    assert receipt["totals"]["without_annotations"] == 1
    annotated = next(
        item for item in manifest["images"] if item["file_name"] == "val/official-val.jpg"
    )
    missing = next(
        item for item in manifest["images"] if item["file_name"] == "val/missing-val.jpg"
    )
    assert annotated["annotations"][0]["bbox"] == pytest.approx([8.0, 3.0, 12.0, 7.0])
    assert annotated["learner_annotation_status"] == "annotated"
    assert missing["learner_annotation_status"] == "missing"
    assert missing["annotations"] == []
    assert importer.validate_sample(official, manifest) == [
        official / "val" / "missing-val.jpg",
        official / "val" / "official-val.jpg",
    ]


def test_annotations_only_export_uses_official_bdd100k_images(tmp_path: Path) -> None:
    audit_module = load_script("learner_annotation_audit")
    cvat_module = load_script("cvat_sample")
    official = tmp_path / "bdd100k"
    (official / "train").mkdir(parents=True)
    (official / "val").mkdir()
    Image.new("RGB", (20, 10)).save(official / "val" / "official-val.jpg")
    export = tmp_path / "learner-annotations.zip"
    write_annotations_only_yolo_export(
        export,
        ["official-val.jpg"],
        {"official-val": "0 0.090988 0.505083 0.181977 0.322806\n"},
    )

    receipt = audit_module.build_receipt([export], official)
    assert receipt["totals"]["membership"] == {
        "train": 0,
        "val": 1,
        "not_bdd100k": 0,
    }
    assert receipt["totals"]["boxes"] == 1
    assert receipt["totals"]["out_of_bounds_boxes"] == 0
    manifest = audit_module.materialize_bdd100k_manifest(
        [export], receipt, official, tmp_path / "manifest.json"
    )
    assert manifest["images"][0]["file_name"] == "val/official-val.jpg"
    assert manifest["images"][0]["learner_annotation_status"] == "annotated"
    assert manifest["images"][0]["annotations"][0]["label"] == "car"
    assert manifest["images"][0]["annotations"][0]["bbox"][0] == 0.0
    assert cvat_module.validate_sample(official, manifest) == [
        official / "val" / "official-val.jpg"
    ]
