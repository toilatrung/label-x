"""Chạy worker classifier tách tiến trình (backend không import torch).

Lệnh và thư mục artifact chỉ lấy từ settings (`CLASSIFIER_WORKER_COMMAND`,
`CLASSIFIER_ARTIFACT_ROOT`), không bao giờ từ config/FE. Không dùng shell, có timeout cứng, và
stdout/stderr của worker không đi qua API (chỉ log sau khi cắt ngắn).
"""

from __future__ import annotations

import json
import logging
import subprocess  # noqa: S404  (lệnh cố định từ settings, không shell)
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from django.conf import settings

from classifier.errors import ClassifierReason, ClassifierRunError

logger = logging.getLogger("labelx.classifier")
MANIFEST_NAME = "classifier-manifest.json"
EXIT_CHECKSUM_MISMATCH = 3  # khớp labelx_classifier.cli
EXIT_BAD_MANIFEST = 4
DEFAULT_TIMEOUT_SECONDS = 300.0
_LOG_LIMIT = 500


@dataclass(frozen=True)
class CropItem:
    item_id: str
    data: bytes = field(repr=False)  # bytes ảnh crop: không vào repr/log


@dataclass(frozen=True)
class ItemResult:
    item_id: str
    ok: bool
    reason: str = ""
    prediction: dict[str, Any] | None = None


@dataclass(frozen=True)
class BatchResult:
    checkpoint: dict[str, Any]  # version, sha256, status, class_map_version
    items: dict[str, ItemResult]


class ClassifierRunner(Protocol):
    def run(
        self, *, artifact_key: str, expected_sha256: str, crops: Sequence[CropItem]
    ) -> BatchResult:
        """Chạy batch; ném ClassifierRunError nếu cả batch không chạy được."""
        ...


def artifact_manifest_path(artifact_key: str) -> Path | None:
    """Manifest trong thư mục artifact, kẹp trong CLASSIFIER_ARTIFACT_ROOT (chặn path escape)."""
    root = getattr(settings, "CLASSIFIER_ARTIFACT_ROOT", "")
    if not root or not artifact_key:
        return None
    base = Path(root).resolve()
    manifest = (base / artifact_key / MANIFEST_NAME).resolve()
    if base not in manifest.parents or not manifest.is_file():
        return None
    return manifest


class SubprocessClassifierRunner:
    def run(
        self, *, artifact_key: str, expected_sha256: str, crops: Sequence[CropItem]
    ) -> BatchResult:
        command = list(getattr(settings, "CLASSIFIER_WORKER_COMMAND", []) or [])
        if not command:
            raise ClassifierRunError(ClassifierReason.NOT_CONFIGURED)
        manifest = artifact_manifest_path(artifact_key)
        if manifest is None:
            raise ClassifierRunError(ClassifierReason.CHECKPOINT_UNAVAILABLE)
        timeout = float(getattr(settings, "CLASSIFIER_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
        with tempfile.TemporaryDirectory(prefix="labelx-clf-") as tmp:
            workdir = Path(tmp)
            items = []
            for index, crop in enumerate(crops):
                path = workdir / f"{index}.img"
                path.write_bytes(crop.data)
                items.append({"id": crop.item_id, "image": path.name})  # relative to --image-root
            batch_file = workdir / "batch.json"
            batch_file.write_text(json.dumps(items), encoding="utf-8")
            try:
                completed = subprocess.run(  # noqa: S603
                    [
                        *command,
                        "predict-batch",
                        "--manifest",
                        str(manifest),
                        "--input",
                        str(batch_file),
                        "--image-root",
                        str(workdir),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                    shell=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise ClassifierRunError(ClassifierReason.TIMEOUT) from exc
            except OSError as exc:
                logger.warning("classifier worker could not start: %s", type(exc).__name__)
                raise ClassifierRunError(ClassifierReason.NOT_CONFIGURED) from exc
        if completed.returncode != 0:
            logger.warning(
                "classifier worker failed rc=%s stderr=%s",
                completed.returncode,
                completed.stderr[-_LOG_LIMIT:],
            )
            if completed.returncode == EXIT_CHECKSUM_MISMATCH:
                raise ClassifierRunError(ClassifierReason.CHECKSUM_MISMATCH)
            if completed.returncode == EXIT_BAD_MANIFEST:
                raise ClassifierRunError(ClassifierReason.CHECKPOINT_UNAVAILABLE)
            raise ClassifierRunError(ClassifierReason.INFERENCE_ERROR)
        return parse_batch_output(completed.stdout, expected_sha256=expected_sha256)


def parse_batch_output(stdout: str, *, expected_sha256: str) -> BatchResult:
    """Kiểm kỹ đầu ra worker; sai hình dạng hoặc checkpoint lạ → lỗi ổn định, không tin."""
    try:
        data = json.loads(stdout)
        checkpoint = data["checkpoint"]
        rows = data["results"]
        if checkpoint["sha256"] != expected_sha256:
            raise ClassifierRunError(ClassifierReason.CHECKSUM_MISMATCH)
        items: dict[str, ItemResult] = {}
        for row in rows:
            item_id = str(row["id"])
            if row["ok"] is True:
                prediction = row["prediction"]
                _check_prediction(prediction)
                items[item_id] = ItemResult(item_id, True, prediction=prediction)
            else:
                items[item_id] = ItemResult(item_id, False, reason=str(row["reason"]))
    except ClassifierRunError:
        raise
    except (ValueError, KeyError, TypeError) as exc:
        raise ClassifierRunError(ClassifierReason.INFERENCE_ERROR) from exc
    return BatchResult(checkpoint=checkpoint, items=items)


def _check_prediction(prediction: dict[str, Any]) -> None:
    top3 = prediction["top3"]
    if not isinstance(top3, list) or not 1 <= len(top3) <= 3:
        raise ValueError("top3")
    for entry in top3:
        if not (0 <= int(entry["class_id"]) < 10) or not isinstance(entry["class_name"], str):
            raise ValueError("class")
        if not 0.0 <= float(entry["score"]) <= 1.0:
            raise ValueError("score")
    float(prediction["score"])
    float(prediction["margin"])


def default_runner() -> ClassifierRunner:
    from django.utils.module_loading import import_string

    path = getattr(settings, "CLASSIFIER_RUNNER", "classifier.runner.SubprocessClassifierRunner")
    runner: ClassifierRunner = import_string(path)()
    return runner
