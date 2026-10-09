#!/usr/bin/env python3
"""Audit learner CVAT YOLO exports against official BDD100K image listings."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
BDD100K_CATEGORIES = {
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
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, action="append", required=True)
    parser.add_argument("--bdd100k-images-root", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".cache/cvat/learner-annotation-audit.json"),
    )
    parser.add_argument("--manifest-output", type=Path)
    parser.add_argument("--images-output", type=Path)
    parser.add_argument(
        "--bdd100k-manifest-output",
        type=Path,
        help=(
            "Write a strict manifest that references official train/val images directly; "
            "the audit fails if any image, bbox, or label is not valid BDD100K input"
        ),
    )
    parser.add_argument(
        "--strict-bdd100k",
        action="store_true",
        help="Fail after writing the receipt unless every export is valid BDD100K learner data",
    )
    args = parser.parse_args()
    if bool(args.manifest_output) != bool(args.images_output):
        parser.error("--manifest-output and --images-output must be supplied together")
    if args.bdd100k_manifest_output and (args.manifest_output or args.images_output):
        parser.error(
            "--bdd100k-manifest-output cannot be combined with legacy materialization"
        )
    return args


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def official_listings(images_root: Path) -> dict[str, set[str]]:
    listings = {
        split: {
            path.name.casefold()
            for path in (images_root / split).iterdir()
            if path.is_file()
        }
        for split in ("train", "val")
    }
    overlap = listings["train"] & listings["val"]
    if overlap:
        raise ValueError("official BDD100K train/val filename listings overlap")
    return listings


def _read_text(archive: zipfile.ZipFile, name: str) -> str:
    return archive.read(name).decode("utf-8-sig")


def _class_names(data_yaml: str, source: str) -> dict[int, str]:
    names: dict[int, str] = {}
    inside_names = False
    for line in data_yaml.splitlines():
        if line.strip() == "names:":
            inside_names = True
            continue
        if inside_names and line and not line[0].isspace():
            break
        if inside_names:
            match = re.match(r"^\s+(\d+):\s*['\"]?(.+?)['\"]?\s*$", line)
            if match:
                names[int(match.group(1))] = match.group(2)
    if not names:
        raise ValueError(f"{source}: data.yaml has no supported names mapping")
    return names


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


def _box_inside_image(coordinates: list[float]) -> bool:
    x, y, width, height = coordinates
    return (
        x - width / 2 >= 0
        and x + width / 2 <= 1
        and y - height / 2 >= 0
        and y + height / 2 <= 1
    )


def audit_export(
    path: Path, listings: dict[str, set[str]]
) -> tuple[dict[str, Any], list[str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with zipfile.ZipFile(path) as archive:
        files = {name for name in archive.namelist() if not name.endswith("/")}
        if "data.yaml" not in files or "train.txt" not in files:
            raise ValueError(f"{path.name}: missing data.yaml or train.txt")
        class_names = _class_names(_read_text(archive, "data.yaml"), path.name)
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
        annotated_stems: set[str] = set()
        class_counts: Counter[int] = Counter()
        out_of_bounds: list[dict[str, object]] = []
        for stem, name in label_by_stem.items():
            for line_number, line in enumerate(
                _read_text(archive, name).splitlines(), start=1
            ):
                if not line.strip():
                    continue
                class_id, coordinates = _validate_yolo_line(
                    line, f"{path.name}:{name}:{line_number}"
                )
                if class_id not in class_names:
                    raise ValueError(
                        f"{path.name}:{name}:{line_number}: unknown class id {class_id}"
                    )
                class_counts[class_id] += 1
                boxes += 1
                annotated_stems.add(stem)
                if not _box_inside_image(coordinates):
                    out_of_bounds.append(
                        {
                            "label_file": name,
                            "line": line_number,
                            "image_stem": PurePosixPath(name).stem,
                            "coordinates": coordinates,
                        }
                    )

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

        without_annotations = sorted(
            set(image_by_stem) - annotated_stems,
            key=str.casefold,
        )
        return (
            {
                "file": path.name,
                "sha256": sha256(path),
                "images": len(image_entries),
                "label_files": len(label_entries),
                "boxes": boxes,
                "classes": {
                    str(key): class_counts[key] for key in sorted(class_counts)
                },
                "class_names": {
                    str(key): class_names[key] for key in sorted(class_names)
                },
                "out_of_bounds_boxes": len(out_of_bounds),
                "out_of_bounds": out_of_bounds,
                "annotated_images": len(annotated_stems),
                "without_annotations": len(without_annotations),
                "without_annotation_stems": without_annotations,
                # Backward-compatible aliases used by the T-004 report.
                "empty_or_unlabeled_images": len(without_annotations),
                "empty_or_unlabeled_stems": without_annotations,
                "membership": {
                    key: membership[key] for key in ("train", "val", "not_bdd100k")
                },
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
        raise ValueError(
            "duplicate image names across exports: " + ", ".join(duplicates)
        )

    return {
        "schema_version": "labelx-learner-annotation-audit-v2",
        "format": "Ultralytics YOLO Detection 1.0",
        "exports": results,
        "totals": {
            "exports": len(results),
            "images": sum(int(item["images"]) for item in results),
            "label_files": sum(int(item["label_files"]) for item in results),
            "boxes": sum(int(item["boxes"]) for item in results),
            "out_of_bounds_boxes": sum(
                int(item["out_of_bounds_boxes"]) for item in results
            ),
            "out_of_bounds_images": len(
                {
                    str(detail["image_stem"]).casefold()
                    for item in results
                    for detail in item["out_of_bounds"]
                }
            ),
            "annotated_images": sum(int(item["annotated_images"]) for item in results),
            "without_annotations": sum(
                int(item["without_annotations"]) for item in results
            ),
            "empty_or_unlabeled_images": sum(
                int(item["empty_or_unlabeled_images"]) for item in results
            ),
            "membership": {
                key: sum(int(item["membership"][key]) for item in results)
                for key in ("train", "val", "not_bdd100k")
            },
        },
    }


def bdd100k_validation_errors(receipt: dict[str, Any]) -> list[str]:
    """Return fail-closed reasons for using the exports as T-019 BDD100K input."""

    errors: list[str] = []
    totals = receipt["totals"]
    membership = totals["membership"]
    if int(totals["images"]) < 1:
        errors.append("no learner images were found")
    if int(membership["not_bdd100k"]) > 0:
        errors.append(
            f"{membership['not_bdd100k']} image(s) are not in official BDD100K listings"
        )
    if int(totals["out_of_bounds_boxes"]) > 0:
        errors.append(
            f"{totals['out_of_bounds_boxes']} bbox(es) are outside image bounds"
        )
    for export in receipt["exports"]:
        unsupported = sorted(
            {
                str(name)
                for name in export["class_names"].values()
                if str(name) not in BDD100K_CATEGORIES
            }
        )
        if unsupported:
            errors.append(
                f"{export['file']}: unsupported BDD100K class(es): {', '.join(unsupported)}"
            )
    return errors


def materialize_bdd100k_manifest(
    exports: list[Path],
    receipt: dict[str, Any],
    images_root: Path,
    manifest_output: Path,
) -> dict[str, Any]:
    """Create an import manifest referencing only the official BDD100K image tree."""

    errors = bdd100k_validation_errors(receipt)
    if errors:
        raise ValueError("strict BDD100K validation failed: " + "; ".join(errors))

    listings = official_listings(images_root)
    expected_names: dict[int, str] | None = None
    images: list[dict[str, Any]] = []
    used_splits: set[str] = set()

    for export in exports:
        with zipfile.ZipFile(export) as archive:
            class_names = _class_names(_read_text(archive, "data.yaml"), export.name)
            if expected_names is None:
                expected_names = class_names
            elif class_names != expected_names:
                raise ValueError(
                    f"{export.name}: taxonomy differs across learner exports"
                )
            files = {name for name in archive.namelist() if not name.endswith("/")}
            image_entries = sorted(
                name
                for name in files
                if PurePosixPath(name).parent == PurePosixPath("images/train")
                and PurePosixPath(name).suffix.lower() in IMAGE_SUFFIXES
            )
            label_by_stem = {
                PurePosixPath(name).stem: name
                for name in files
                if PurePosixPath(name).parent == PurePosixPath("labels/train")
                and PurePosixPath(name).suffix.lower() == ".txt"
            }
            for image_entry in image_entries:
                image_name = PurePosixPath(image_entry).name
                folded = image_name.casefold()
                split = "train" if folded in listings["train"] else "val"
                used_splits.add(split)
                official_image = images_root / split / image_name
                with Image.open(official_image) as image:
                    width, height = image.size

                annotations: list[dict[str, Any]] = []
                label_entry = label_by_stem.get(PurePosixPath(image_entry).stem)
                if label_entry:
                    for line_number, line in enumerate(
                        _read_text(archive, label_entry).splitlines(), start=1
                    ):
                        if not line.strip():
                            continue
                        class_id, (x, y, box_width, box_height) = _validate_yolo_line(
                            line, f"{export.name}:{label_entry}:{line_number}"
                        )
                        annotations.append(
                            {
                                "label": class_names[class_id],
                                "bbox": [
                                    (x - box_width / 2) * width,
                                    (y - box_height / 2) * height,
                                    (x + box_width / 2) * width,
                                    (y + box_height / 2) * height,
                                ],
                            }
                        )
                images.append(
                    {
                        "file_name": f"{split}/{image_name}",
                        "split": split,
                        "learner_annotation_status": "annotated"
                        if annotations
                        else "missing",
                        "annotations": annotations,
                    }
                )

    if expected_names is None:
        raise ValueError("no learner export taxonomy found")
    palette = ("#ff6b6b", "#f06595", "#845ef7", "#5c7cfa", "#339af0", "#22b8cf")
    manifest = {
        "schema_version": "labelx-cvat-sample-v1",
        "provenance": {
            "dataset": "bdd100k-learner",
            "split": next(iter(used_splits)) if len(used_splits) == 1 else "mixed",
            "source": "learner CVAT Ultralytics YOLO Detection 1.0 exports",
            "source_exports": [
                {"file": item["file"], "sha256": item["sha256"]}
                for item in receipt["exports"]
            ],
            "bdd100k_membership": receipt["totals"]["membership"],
            "learner_frames": {
                "with_annotations": receipt["totals"]["annotated_images"],
                "without_annotations": receipt["totals"]["without_annotations"],
            },
        },
        "labels": [
            {
                "name": expected_names[class_id],
                "type": "rectangle",
                "color": palette[index % len(palette)],
            }
            for index, class_id in enumerate(sorted(expected_names))
        ],
        "images": sorted(images, key=lambda item: str(item["file_name"]).casefold()),
    }
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def materialize_labelx_manifest(
    exports: list[Path],
    receipt: dict[str, Any],
    images_output: Path,
    manifest_output: Path,
) -> dict[str, Any]:
    if images_output.exists() and any(images_output.iterdir()):
        raise ValueError(f"images output must be empty: {images_output}")
    images_output.mkdir(parents=True, exist_ok=True)
    expected_names: dict[int, str] | None = None
    images: list[dict[str, Any]] = []

    for export in exports:
        with zipfile.ZipFile(export) as archive:
            class_names = _class_names(_read_text(archive, "data.yaml"), export.name)
            if expected_names is None:
                expected_names = class_names
            elif class_names != expected_names:
                raise ValueError(
                    f"{export.name}: taxonomy differs across learner exports"
                )
            files = {name for name in archive.namelist() if not name.endswith("/")}
            image_entries = sorted(
                name
                for name in files
                if PurePosixPath(name).parent == PurePosixPath("images/train")
                and PurePosixPath(name).suffix.lower() in IMAGE_SUFFIXES
            )
            label_by_stem = {
                PurePosixPath(name).stem: name
                for name in files
                if PurePosixPath(name).parent == PurePosixPath("labels/train")
                and PurePosixPath(name).suffix.lower() == ".txt"
            }
            for image_entry in image_entries:
                image_name = PurePosixPath(image_entry).name
                image_bytes = archive.read(image_entry)
                with Image.open(io.BytesIO(image_bytes)) as image:
                    width, height = image.size
                annotations: list[dict[str, Any]] = []
                label_entry = label_by_stem.get(PurePosixPath(image_entry).stem)
                if label_entry:
                    for line_number, line in enumerate(
                        _read_text(archive, label_entry).splitlines(), start=1
                    ):
                        if not line.strip():
                            continue
                        class_id, (x, y, box_width, box_height) = _validate_yolo_line(
                            line, f"{export.name}:{label_entry}:{line_number}"
                        )
                        if class_id not in class_names:
                            raise ValueError(
                                f"{export.name}:{label_entry}:{line_number}: "
                                f"unknown class id {class_id}"
                            )
                        if not _box_inside_image([x, y, box_width, box_height]):
                            annotations = []
                            break
                        annotations.append(
                            {
                                "label": class_names[class_id],
                                "bbox": [
                                    (x - box_width / 2) * width,
                                    (y - box_height / 2) * height,
                                    (x + box_width / 2) * width,
                                    (y + box_height / 2) * height,
                                ],
                            }
                        )
                if label_entry and any(
                    detail["image_stem"] == PurePosixPath(image_entry).stem
                    for item in receipt["exports"]
                    for detail in item["out_of_bounds"]
                ):
                    continue
                (images_output / image_name).write_bytes(image_bytes)
                images.append(
                    {
                        "file_name": image_name,
                        "split": "not-bdd100k",
                        "annotations": annotations,
                    }
                )

    if expected_names is None:
        raise ValueError("no learner export taxonomy found")
    palette = ("#22b8cf", "#ff6b6b", "#845ef7", "#51cf66")
    manifest = {
        "schema_version": "labelx-cvat-sample-v1",
        "provenance": {
            "dataset": "learner-greensm",
            "split": "not-bdd100k",
            "source": "learner CVAT Ultralytics YOLO Detection 1.0 exports",
            "source_exports": [
                {"file": item["file"], "sha256": item["sha256"]}
                for item in receipt["exports"]
            ],
            "bdd100k_membership": receipt["totals"]["membership"],
        },
        "labels": [
            {
                "name": expected_names[class_id],
                "type": "rectangle",
                "color": palette[index % len(palette)],
            }
            for index, class_id in enumerate(sorted(expected_names))
        ],
        "images": sorted(images, key=lambda item: str(item["file_name"]).casefold()),
    }
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    args = parse_args()
    receipt = build_receipt(args.export, args.bdd100k_images_root.resolve())
    validation_errors = bdd100k_validation_errors(receipt)
    receipt["validation"] = {
        "mode": "strict-bdd100k"
        if args.strict_bdd100k or args.bdd100k_manifest_output
        else "audit",
        "status": "failed" if validation_errors else "passed",
        "errors": validation_errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.bdd100k_manifest_output:
        manifest = materialize_bdd100k_manifest(
            [path.resolve() for path in args.export],
            receipt,
            args.bdd100k_images_root.resolve(),
            args.bdd100k_manifest_output.resolve(),
        )
        print(
            json.dumps(
                {
                    "manifest": str(args.bdd100k_manifest_output.resolve()),
                    "images_root": str(args.bdd100k_images_root.resolve()),
                    "images": len(manifest["images"]),
                    "annotated_images": receipt["totals"]["annotated_images"],
                    "without_annotations": receipt["totals"]["without_annotations"],
                    "annotations": sum(
                        len(item["annotations"]) for item in manifest["images"]
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.manifest_output and args.images_output:
        manifest = materialize_labelx_manifest(
            [path.resolve() for path in args.export],
            receipt,
            args.images_output.resolve(),
            args.manifest_output.resolve(),
        )
        print(
            json.dumps(
                {
                    "manifest": str(args.manifest_output.resolve()),
                    "images": len(manifest["images"]),
                    "annotations": sum(
                        len(item["annotations"]) for item in manifest["images"]
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.strict_bdd100k and validation_errors:
        raise ValueError(
            "strict BDD100K validation failed: " + "; ".join(validation_errors)
        )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
