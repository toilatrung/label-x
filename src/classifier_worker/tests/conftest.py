"""Synthetic snapshot/image helpers. Everything here is fixture data, not real annotations."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PIL import Image

LABELS = {1: "car", 2: "traffic sign", 3: "pedestrian", 7: "person", 8: "bus"}
COLORS = {
    1: (200, 30, 30),
    2: (30, 200, 30),
    3: (30, 30, 200),
    7: (200, 200, 30),
    8: (30, 200, 200),
}


def make_snapshot(root: Path, *, tasks: int = 8) -> dict:
    jobs = []
    for task in range(1, tasks + 1):
        key = f"snapshots/source/t{task}.png"
        image = Image.new("RGB", (320, 240), (90, 90, 90))
        shapes = []
        for index, (label, box) in enumerate(
            [(1, (10, 20, 110, 80)), (2, (150, 30, 190, 150)), (3, (200, 100, 260, 200))]
        ):
            image.paste(
                Image.new("RGB", (box[2] - box[0], box[3] - box[1]), COLORS[label]), box[:2]
            )
            shapes.append(_shape(task * 10 + index, label, list(box)))
        path = root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        jobs.append(
            {
                "cvat_job_id": 100 + task,
                "cvat_task_id": task,
                "frames": [
                    {
                        "file_name": f"t{task}.png",
                        "frame_index": 0,
                        "height": 240,
                        "width": 320,
                        "source_frame_id": 5000 + task,
                        "media": {
                            "mime_type": "image/png",
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "size_bytes": path.stat().st_size,
                            "storage_key": key,
                        },
                        "shapes": shapes,
                    }
                ],
            }
        )
    return {
        "schema_version": "labelx.snapshot.v1",
        "dataset_id": 42,
        "taxonomy_version": "bdd100k-10-v1",
        "guideline_version": "bdd100k-guideline-v1",
        "jobs": jobs,
    }


def _shape(source_id: int, label: int, points: list[float], **extra: object) -> dict:
    return {
        "attributes": [],
        "frame_index": 0,
        "label_id": label,
        "occluded": False,
        "outside": False,
        "points": points,
        "rotation": 0.0,
        "source": {"id": source_id, "kind": "shape"},
        "z_order": 0,
        **extra,
    }


@pytest.fixture
def image_root(tmp_path: Path) -> Path:
    return tmp_path / "images"


@pytest.fixture
def snapshot(image_root: Path) -> dict:
    return make_snapshot(image_root)
