import importlib.util
import sys
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
