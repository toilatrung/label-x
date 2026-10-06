#!/usr/bin/env python3
"""Provision a development-only CVAT project/task from local sample images.

This script is intentionally outside ``src/backend/cvat_adapter``: it writes to
CVAT, while the product adapter is a read-only boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import time
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_PROJECT = "labelx-dev"
DEFAULT_TASK = "labelx-dev__review__custom__unknown__v1"


def convention_tags(manifest: dict[str, Any]) -> dict[str, str]:
    """Derive the LabelX naming tags from manifest provenance."""
    provenance = manifest.get("provenance", {})
    return {
        "labelx.role": "review",
        "labelx.dataset": str(provenance.get("dataset", "custom")),
        "labelx.split": str(provenance.get("split", "unknown")),
        "labelx.schema": "v1",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument(
        "--annotations",
        type=Path,
        default=Path("infrastructure/cvat/sample-annotations.json"),
    )
    parser.add_argument("--base-url", default=os.getenv("CVAT_BASE_URL", "http://localhost:8080"))
    parser.add_argument("--token", default=os.getenv("CVAT_SERVICE_TOKEN", ""))
    parser.add_argument(
        "--token-file",
        type=Path,
        help="Ignored JSON file containing a 'provisioner' token; the value is never logged",
    )
    parser.add_argument("--project-name", default=DEFAULT_PROJECT)
    parser.add_argument("--task-name", default=DEFAULT_TASK)
    parser.add_argument("--receipt", type=Path, default=Path(".cache/cvat/import-receipt.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.token_file:
        token_payload = json.loads(args.token_file.read_text(encoding="utf-8"))
        args.token = str(token_payload["provisioner"])
    return args


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "labelx-cvat-sample-v1":
        raise ValueError("unsupported annotation manifest schema")
    if not isinstance(payload.get("labels"), list) or not isinstance(payload.get("images"), list):
        raise ValueError("manifest must contain labels and images arrays")
    return payload


def inventory_counts(images_dir: Path) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for path in images_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        parts = {part.lower() for part in path.relative_to(images_dir).parts[:-1]}
        split = (
            "train"
            if "train" in parts
            else "val"
            if "val" in parts
            else "test"
            if "test" in parts
            else "unknown"
        )
        counts[split] += 1
    return {name: counts[name] for name in ("train", "val", "test", "unknown")}


def validate_sample(images_dir: Path, manifest: dict[str, Any]) -> list[Path]:
    selected: list[Path] = []
    labels = {str(label["name"]) for label in manifest["labels"]}
    for image_entry in manifest["images"]:
        path = images_dir / str(image_entry["file_name"])
        if not path.is_file():
            raise FileNotFoundError(f"sample image not found: {path}")
        with Image.open(path) as image:
            width, height = image.size
        for annotation in image_entry.get("annotations", []):
            if annotation.get("label") not in labels:
                raise ValueError(f"unknown label in {path.name}: {annotation.get('label')}")
            bbox = annotation.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                raise ValueError(f"invalid bbox in {path.name}")
            left, top, right, bottom = (float(value) for value in bbox)
            if not (0 <= left < right <= width and 0 <= top < bottom <= height):
                raise ValueError(f"bbox outside {width}x{height} image: {path.name}")
        selected.append(path)
    return selected


class ProvisioningClient:
    """Write-capable client used only by this explicit dev provisioning script."""

    def __init__(self, base_url: str, token: str) -> None:
        if not token:
            raise ValueError("--token or CVAT_SERVICE_TOKEN is required unless --dry-run is used")
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.cvat+json"},
            timeout=120,
        )

    def close(self) -> None:
        self._client.close()

    def _url(self, endpoint: str) -> str:
        return f"{self._base_url}/{endpoint.lstrip('/')}"

    def _json(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        response = self._client.request(method, self._url(endpoint), **kwargs)
        response.raise_for_status()
        if not response.content:
            return {}
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError(f"CVAT response for {endpoint} must be an object")
        return payload

    def find_or_create_project(self, name: str, labels: list[dict[str, Any]]) -> int:
        payload = self._json("GET", "api/projects", params={"search": name, "page_size": 100})
        for project in payload.get("results", []):
            if project.get("name") == name:
                return int(project["id"])
        created = self._json("POST", "api/projects", json={"name": name, "labels": labels})
        return int(created["id"])

    def ensure_task_absent(self, name: str) -> None:
        payload = self._json("GET", "api/tasks", params={"search": name, "page_size": 100})
        if any(task.get("name") == name for task in payload.get("results", [])):
            raise ValueError(f"CVAT task already exists: {name}")

    def create_task(self, name: str, project_id: int, subset: str) -> int:
        payload = self._json(
            "POST",
            "api/tasks",
            json={"name": name, "project_id": project_id, "subset": subset},
        )
        return int(payload["id"])

    def upload_images(self, task_id: int, paths: list[Path]) -> None:
        url = self._url(f"api/tasks/{task_id}/data")
        start = self._client.post(url, headers={"Upload-Start": ""})
        start.raise_for_status()

        with ExitStack() as stack:
            files = [
                (
                    f"client_files[{index}]",
                    (
                        path.name,
                        stack.enter_context(path.open("rb")),
                        mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                    ),
                )
                for index, path in enumerate(paths)
            ]
            upload = self._client.post(
                url,
                data={"image_quality": "70"},
                files=files,
                headers={"Upload-Multiple": ""},
            )
        upload.raise_for_status()

        response = self._client.post(
            url,
            json={
                "image_quality": 70,
                "sorting_method": "predefined",
                "upload_file_order": [path.name for path in paths],
            },
            headers={"Upload-Finish": ""},
        )
        response.raise_for_status()
        payload = response.json() if response.content else {}
        request_id = payload.get("rq_id") or payload.get("request_id")
        if request_id:
            self._wait_for_request(str(request_id))

    def _wait_for_request(self, request_id: str) -> None:
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            payload = self._json("GET", f"api/requests/{request_id}")
            status = str(payload.get("status", "")).lower()
            if status == "finished":
                return
            if status == "failed":
                raise RuntimeError(
                    f"CVAT request failed: {payload.get('message', 'unknown error')}"
                )
            time.sleep(2)
        raise TimeoutError("CVAT image import did not finish within 10 minutes")

    def label_ids(self, task_id: int) -> dict[str, int]:
        payload = self._json("GET", "api/labels", params={"task_id": task_id, "page_size": 100})
        raw_labels = payload.get("results", payload)
        if isinstance(raw_labels, dict):
            raw_labels = raw_labels.get("results", [])
        return {str(label["name"]): int(label["id"]) for label in raw_labels}

    def upload_annotations(
        self, task_id: int, manifest: dict[str, Any], label_ids: dict[str, int]
    ) -> None:
        shapes: list[dict[str, Any]] = []
        for frame, image_entry in enumerate(manifest["images"]):
            for annotation in image_entry.get("annotations", []):
                shapes.append(
                    {
                        "type": "rectangle",
                        "frame": frame,
                        "label_id": label_ids[str(annotation["label"])],
                        "points": annotation["bbox"],
                        "occluded": False,
                        "outside": False,
                        "z_order": 0,
                        "rotation": 0,
                        "attributes": [],
                        "source": "manual",
                    }
                )
        self._json(
            "PUT",
            f"api/tasks/{task_id}/annotations",
            json={"version": 0, "tags": [], "shapes": shapes, "tracks": []},
        )


def receipt(
    args: argparse.Namespace,
    manifest: dict[str, Any],
    selected: list[Path],
    task_id: int | None,
) -> dict[str, Any]:
    annotation_bytes = args.annotations.read_bytes()
    return {
        "schema_version": "labelx-cvat-import-receipt-v1",
        "dry_run": bool(args.dry_run),
        "cvat": {
            "project_name": args.project_name,
            "task_name": args.task_name,
            "task_id": task_id,
        },
        "tags": convention_tags(manifest),
        "source": {
            "images_dir": str(args.images.resolve()),
            "annotation_manifest": str(args.annotations.resolve()),
            "annotation_manifest_sha256": hashlib.sha256(annotation_bytes).hexdigest(),
            "inventory_by_split": inventory_counts(args.images),
            "selected_images": len(selected),
            "selected_annotations": sum(
                len(item.get("annotations", [])) for item in manifest["images"]
            ),
        },
    }


def main() -> int:
    args = parse_args()
    manifest = load_manifest(args.annotations)
    selected = validate_sample(args.images, manifest)
    task_id: int | None = None

    if not args.dry_run:
        client = ProvisioningClient(args.base_url, args.token)
        try:
            client.ensure_task_absent(args.task_name)
            project_id = client.find_or_create_project(args.project_name, manifest["labels"])
            task_id = client.create_task(
                args.task_name,
                project_id,
                convention_tags(manifest)["labelx.split"],
            )
            client.upload_images(task_id, selected)
            client.upload_annotations(task_id, manifest, client.label_ids(task_id))
        finally:
            client.close()

    result = receipt(args, manifest, selected, task_id)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, httpx.HTTPError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
