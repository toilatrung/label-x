#!/usr/bin/env python3
"""Audit learner CVAT YOLO exports against official BDD100K image listings."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, action="append", required=True)
    parser.add_argument("--bdd100k-images-root", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".cache/cvat/learner-annotation-audit.json"),
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def official_listings(images_root: Path) -> dict[str, set[str]]:
    listings = {
        split: {path.name.casefold() for path in (images_root / split).iterdir() if path.is_file()}
        for split in ("train", "val")
    }
    overlap = listings["train"] & listings["val"]
    if overlap:
        raise ValueError("official BDD100K train/val filename listings overlap")
    return listings


def _read_text(archive: zipfile.ZipFile, name: str) -> str:
    return archive.read(name).decode("utf-8-sig")


def _validate_yolo_line(line: str, source: str) -> tuple[int, list[float]]:
    parts = line.split()
    if len(parts) != 5:
        raise ValueError(f"{source}: expected 5 YOLO fields")
    try:
        class_id = int(parts[0])
        coordinates = [float(value) for value in parts[1:]]
    except ValueError as error:
        raise ValueError(f"{source}: non-numeric YOLO field") from error
    x, y, width, height = coordinates
    if class_id < 0:
        raise ValueError(f"{source}: class id must be non-negative")
    if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < width <= 1 and 0 < height <= 1):
        raise ValueError(f"{source}: normalized YOLO coordinates are out of range")
    return class_id, coordinates


def audit_export(path: Path, listings: dict[str, set[str]]) -> tuple[dict[str, Any], list[str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with zipfile.ZipFile(path) as archive:
        files = {name for name in archive.namelist() if not name.endswith("/")}
        if "data.yaml" not in files or "train.txt" not in files:
            raise ValueError(f"{path.name}: missing data.yaml or train.txt")
        image_entries = sorted(
            name
            for name in files
            if PurePosixPath(name).parent == PurePosixPath("images/train")
            and PurePosixPath(name).suffix.lower() in IMAGE_SUFFIXES
        )
        label_entries = sorted(
            name
            for name in files
            if PurePosixPath(name).parent == PurePosixPath("labels/train")
            and PurePosixPath(name).suffix.lower() == ".txt"
        )
        if not image_entries:
            raise ValueError(f"{path.name}: no images/train entries")

        image_by_stem = {PurePosixPath(name).stem: name for name in image_entries}
        if len(image_by_stem) != len(image_entries):
            raise ValueError(f"{path.name}: duplicate image stems")
        label_by_stem = {PurePosixPath(name).stem: name for name in label_entries}
        orphan_labels = sorted(set(label_by_stem) - set(image_by_stem))
        if orphan_labels:
            raise ValueError(f"{path.name}: orphan labels: {', '.join(orphan_labels)}")

        train_names = {
            PurePosixPath(line.strip()).name
            for line in _read_text(archive, "train.txt").splitlines()
            if line.strip()
        }
        image_names = {PurePosixPath(name).name for name in image_entries}
        if train_names != image_names:
            raise ValueError(f"{path.name}: train.txt does not match images/train")

        boxes = 0
        class_counts: Counter[int] = Counter()
        for _stem, name in label_by_stem.items():
            for line_number, line in enumerate(_read_text(archive, name).splitlines(), start=1):
                if not line.strip():
                    continue
                class_id, _coordinates = _validate_yolo_line(
                    line, f"{path.name}:{name}:{line_number}"
                )
                class_counts[class_id] += 1
                boxes += 1

        membership: Counter[str] = Counter()
        names = sorted(image_names, key=str.casefold)
        for name in names:
            folded = name.casefold()
            if folded in listings["train"]:
                membership["train"] += 1
            elif folded in listings["val"]:
                membership["val"] += 1
            else:
                membership["not_bdd100k"] += 1

        missing_labels = sorted(set(image_by_stem) - set(label_by_stem), key=str.casefold)
        return (
            {
                "file": path.name,
                "sha256": sha256(path),
                "images": len(image_entries),
                "label_files": len(label_entries),
                "boxes": boxes,
                "classes": {str(key): class_counts[key] for key in sorted(class_counts)},
                "empty_or_unlabeled_images": len(missing_labels),
                "empty_or_unlabeled_stems": missing_labels,
                "membership": {key: membership[key] for key in ("train", "val", "not_bdd100k")},
            },
            names,
        )


def build_receipt(exports: list[Path], images_root: Path) -> dict[str, Any]:
    listings = official_listings(images_root)
    results: list[dict[str, Any]] = []
    all_names: list[str] = []
    for export in exports:
        result, names = audit_export(export.resolve(), listings)
        results.append(result)
        all_names.extend(names)
    duplicates = sorted(
        (
            name
            for name, count in Counter(name.casefold() for name in all_names).items()
            if count > 1
        )
    )
    if duplicates:
        raise ValueError("duplicate image names across exports: " + ", ".join(duplicates))

    return {
        "schema_version": "labelx-learner-annotation-audit-v1",
        "format": "Ultralytics YOLO Detection 1.0",
        "exports": results,
        "totals": {
            "exports": len(results),
            "images": sum(int(item["images"]) for item in results),
            "label_files": sum(int(item["label_files"]) for item in results),
            "boxes": sum(int(item["boxes"]) for item in results),
            "empty_or_unlabeled_images": sum(
                int(item["empty_or_unlabeled_images"]) for item in results
            ),
            "membership": {
                key: sum(int(item["membership"][key]) for item in results)
                for key in ("train", "val", "not_bdd100k")
            },
        },
    }


def main() -> int:
    args = parse_args()
    receipt = build_receipt(args.export, args.bdd100k_images_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
