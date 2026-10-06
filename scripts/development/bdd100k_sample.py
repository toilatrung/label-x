#!/usr/bin/env python3
"""Build a small deterministic CVAT manifest from official BDD100K Detection 2020."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CATEGORIES = (
    "pedestrian",
    "rider",
    "car",
    "truck",
    "bus",
    "train",
    "motorcycle",
    "bicycle",
    "traffic light",
    "traffic sign",
)
COLORS = (
    "#ff6b6b",
    "#f06595",
    "#845ef7",
    "#5c7cfa",
    "#339af0",
    "#22b8cf",
    "#20c997",
    "#51cf66",
    "#fcc419",
    "#ff922b",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument(
        "--fiftyone-samples",
        type=Path,
        help="Optional FiftyOne samples.json mirror to materialize det_val.json",
    )
    parser.add_argument("--per-split", type=int, default=5)
    parser.add_argument(
        "--splits",
        nargs="+",
        choices=("train", "val"),
        default=("train", "val"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".cache/cvat/bdd100k-sample.json"),
    )
    args = parser.parse_args()
    if args.per_split < 1:
        parser.error("--per-split must be at least 1")
    return args


def resolve_layout(root: Path) -> tuple[Path, Path]:
    candidates = (root, root / "bdd100k")
    for base in candidates:
        images = base / "images" / "100k"
        labels = base / "labels" / "det_20"
        if images.is_dir() and labels.is_dir():
            return images, labels
    raise FileNotFoundError(
        "expected images/100k and labels/det_20 under the dataset root or bdd100k/"
    )


def materialize_val_labels(samples_path: Path, root: Path) -> Path:
    """Convert a public FiftyOne BDD100K mirror into official Scalabel JSON."""
    payload = json.loads(samples_path.read_text(encoding="utf-8"))
    frames = []
    for sample in payload.get("samples", []):
        metadata = sample.get("metadata", {})
        width = float(metadata.get("width", 0))
        height = float(metadata.get("height", 0))
        labels = []
        for index, detection in enumerate(sample.get("detections", {}).get("detections", [])):
            normalized = detection.get("bounding_box", [])
            if len(normalized) != 4 or width <= 0 or height <= 0:
                continue
            x, y, box_width, box_height = (float(value) for value in normalized)
            labels.append(
                {
                    "id": str(detection.get("_id", {}).get("$oid", index)),
                    "category": str(detection.get("label", "")),
                    "attributes": {
                        "occluded": bool(detection.get("occluded", False)),
                        "truncated": bool(detection.get("truncated", False)),
                        "trafficLightColor": str(detection.get("trafficLightColor", "unknown")),
                    },
                    "box2d": {
                        "x1": x * width,
                        "y1": y * height,
                        "x2": (x + box_width) * width,
                        "y2": (y + box_height) * height,
                    },
                }
            )
        frames.append(
            {
                "name": Path(str(sample["filepath"])).name,
                "attributes": {
                    name: str(sample.get(name, {}).get("label", "unknown"))
                    for name in ("weather", "timeofday", "scene")
                },
                "labels": labels,
            }
        )

    base = root / "bdd100k" if not (root / "images").is_dir() else root
    output = base / "labels" / "det_20" / "det_val.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(frames, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


def valid_box(annotation: dict[str, Any]) -> list[float] | None:
    box = annotation.get("box2d")
    if not isinstance(box, dict):
        return None
    try:
        coords = [float(box[key]) for key in ("x1", "y1", "x2", "y2")]
    except (KeyError, TypeError, ValueError):
        return None
    if coords[0] >= coords[2] or coords[1] >= coords[3]:
        return None
    return coords


def select_split(
    images_root: Path, labels_root: Path, split: str, limit: int
) -> list[dict[str, Any]]:
    label_path = labels_root / f"det_{split}.json"
    frames = json.loads(label_path.read_text(encoding="utf-8"))
    selected: list[dict[str, Any]] = []
    allowed = set(CATEGORIES)
    for frame in frames:
        name = str(frame.get("name", ""))
        image_path = images_root / split / name
        if not image_path.is_file():
            continue
        annotations = []
        for label in frame.get("labels", []):
            category = str(label.get("category", ""))
            box = valid_box(label)
            if category in allowed and box is not None:
                annotations.append({"label": category, "bbox": box})
        if not annotations:
            continue
        selected.append(
            {
                "file_name": f"{split}/{name}",
                "split": split,
                "annotations": annotations,
            }
        )
        if len(selected) == limit:
            return selected
    raise ValueError(f"only found {len(selected)} usable {split} images; need {limit}")


def main() -> int:
    args = parse_args()
    if args.fiftyone_samples:
        materialized = materialize_val_labels(
            args.fiftyone_samples.resolve(), args.dataset_root.resolve()
        )
        print(f"Materialized {materialized}")
    images_root, labels_root = resolve_layout(args.dataset_root.resolve())
    images = []
    for split in args.splits:
        images.extend(select_split(images_root, labels_root, split, args.per_split))
    split_tag = "-".join(args.splits)
    manifest = {
        "schema_version": "labelx-cvat-sample-v1",
        "provenance": {
            "dataset": "bdd100k",
            "split": split_tag,
            "source": "BDD100K Detection 2020 official release",
        },
        "labels": [
            {"name": name, "type": "rectangle", "color": color}
            for name, color in zip(CATEGORIES, COLORS, strict=True)
        ],
        "images": images,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "manifest": str(args.output.resolve()),
                "images_root": str(images_root),
                "splits": {split: args.per_split for split in args.splits},
                "annotations": sum(len(item["annotations"]) for item in images),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
