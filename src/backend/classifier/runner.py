"""Chạy worker classifier tách tiến trình (backend không import torch).

Lệnh và thư mục artifact chỉ lấy từ settings (`CLASSIFIER_WORKER_COMMAND`,
`CLASSIFIER_ARTIFACT_ROOT`), không bao giờ từ config/FE. Không dùng shell, có timeout cứng, và
stdout/stderr của worker không đi qua API (chỉ log sau khi cắt ngắn).
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import re
import signal
import subprocess  # noqa: S404  (lệnh cố định từ settings, không shell)
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from django.conf import settings

from classifier.config import CLASS_MAP_VERSION, CLASSES
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


_DEFAULT_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "UV_CACHE_DIR",
    "UV_PYTHON_INSTALL_DIR",
    "XDG_CACHE_HOME",
    "TORCH_HOME",
)
_VERSION = re.compile(r"^[A-Za-z0-9._+\-]{1,64}$")
_CHECKPOINT_STATUSES = frozenset({"smoke_only", "trained"})
_CROP_REASONS = frozenset(
    {"invalid_crop", "invalid_box", "duplicate_id", "missing_id", "invalid_item"}
)
_TOLERANCE = 1e-6


def worker_environment() -> dict[str, str]:
    """Môi trường tối thiểu cho worker: không thừa kế secret của backend (DB, secret key...)."""
    allow = getattr(settings, "CLASSIFIER_WORKER_ENV_ALLOWLIST", _DEFAULT_ENV_ALLOWLIST)
    env = {key: os.environ[key] for key in allow if key in os.environ}
    env.update({str(k): str(v) for k, v in getattr(settings, "CLASSIFIER_WORKER_ENV", {}).items()})
    return env


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
            argv = [
                *command,
                "predict-batch",
                "--manifest",
                str(manifest),
                "--input",
                str(batch_file),
                "--image-root",
                str(workdir),
            ]
            returncode, stdout, stderr = _run_in_own_group(argv, timeout=timeout)
        if returncode != 0:
            logger.warning(
                "classifier worker failed rc=%s stderr=%s", returncode, stderr[-_LOG_LIMIT:]
            )
            if returncode == EXIT_CHECKSUM_MISMATCH:
                raise ClassifierRunError(ClassifierReason.CHECKSUM_MISMATCH)
            if returncode == EXIT_BAD_MANIFEST:
                raise ClassifierRunError(ClassifierReason.CHECKPOINT_UNAVAILABLE)
            raise ClassifierRunError(ClassifierReason.INFERENCE_ERROR)
        return parse_batch_output(stdout, expected_sha256=expected_sha256)


def _run_in_own_group(argv: list[str], *, timeout: float) -> tuple[int, str, str]:
    """Chạy lệnh (không shell) trong process group riêng; hết hạn thì giết cả nhóm."""
    try:
        process = subprocess.Popen(  # noqa: S603
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=worker_environment(),
            shell=False,
            start_new_session=True,
        )
    except OSError as exc:
        logger.warning("classifier worker could not start: %s", type(exc).__name__)
        raise ClassifierRunError(ClassifierReason.NOT_CONFIGURED) from exc
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise ClassifierRunError(ClassifierReason.TIMEOUT) from exc
    return process.returncode, stdout, stderr


def _finite_unit(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("number")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError("range")
    return number


def validate_prediction(prediction: Any) -> dict[str, Any]:
    """Dựng lại dự đoán từ dữ liệu worker đã kiểm: không tin tên lớp/thứ tự/margin của worker."""
    top3 = prediction["top3"]
    if not isinstance(top3, list) or not 1 <= len(top3) <= 3:
        raise ValueError("top3")
    entries: list[dict[str, Any]] = []
    for entry in top3:
        class_id = entry["class_id"]
        if isinstance(class_id, bool) or not isinstance(class_id, int) or not 0 <= class_id < 10:
            raise ValueError("class_id")
        entries.append(
            {
                "class_id": class_id,
                "class_name": CLASSES[class_id],
                "score": _finite_unit(entry["score"]),
            }
        )
    if len({e["class_id"] for e in entries}) != len(entries):
        raise ValueError("duplicate class")
    scores = [e["score"] for e in entries]
    if scores != sorted(scores, reverse=True):
        raise ValueError("top3 order")
    score, margin = _finite_unit(prediction["score"]), _finite_unit(prediction["margin"])
    expected_margin = scores[0] - (scores[1] if len(scores) > 1 else 0.0)
    if abs(score - scores[0]) > _TOLERANCE or abs(margin - expected_margin) > _TOLERANCE:
        raise ValueError("score/margin")
    return {"top3": entries, "score": scores[0], "margin": expected_margin}


def _stable_item_reason(reason: object) -> str:
    """Chỉ nhận mã lý do đã biết; chuỗi lạ của worker không bao giờ đi tiếp."""
    if reason == "box_too_small":
        return ClassifierReason.BOX_TOO_SMALL.value
    if reason in _CROP_REASONS:
        return ClassifierReason.INVALID_CROP.value
    return ClassifierReason.INFERENCE_ERROR.value


def parse_batch_output(stdout: str, *, expected_sha256: str) -> BatchResult:
    """Kiểm kỹ đầu ra worker; sai hình dạng hoặc checkpoint lạ → lỗi ổn định, không tin."""
    try:
        data = json.loads(stdout)
        checkpoint = data["checkpoint"]
        rows = data["results"]
        if checkpoint["sha256"] != expected_sha256:
            raise ClassifierRunError(ClassifierReason.CHECKSUM_MISMATCH)
        version, status = checkpoint["version"], checkpoint["status"]
        if not isinstance(version, str) or not _VERSION.fullmatch(version):
            raise ValueError("version")
        if (
            status not in _CHECKPOINT_STATUSES
            or checkpoint["class_map_version"] != CLASS_MAP_VERSION
        ):
            raise ValueError("checkpoint")
        clean_checkpoint = {
            "version": version,
            "sha256": expected_sha256,
            "status": status,
            "class_map_version": CLASS_MAP_VERSION,
        }
        items: dict[str, ItemResult] = {}
        for row in rows:
            item_id = str(row["id"])
            if row["ok"] is True:
                try:
                    items[item_id] = ItemResult(
                        item_id, True, prediction=validate_prediction(row["prediction"])
                    )
                except (ValueError, KeyError, TypeError):
                    items[item_id] = ItemResult(
                        item_id, False, reason=ClassifierReason.INFERENCE_ERROR.value
                    )
            else:
                items[item_id] = ItemResult(
                    item_id, False, reason=_stable_item_reason(row["reason"])
                )
    except ClassifierRunError:
        raise
    except (ValueError, KeyError, TypeError) as exc:
        raise ClassifierRunError(ClassifierReason.INFERENCE_ERROR) from exc
    return BatchResult(checkpoint=clean_checkpoint, items=items)


def default_runner() -> ClassifierRunner:
    from django.utils.module_loading import import_string

    path = getattr(settings, "CLASSIFIER_RUNNER", "classifier.runner.SubprocessClassifierRunner")
    runner: ClassifierRunner = import_string(path)()
    return runner
