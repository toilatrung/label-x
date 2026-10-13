"""M04B-04 smoke: backend -> worker thật -> checkpoint thật. Mặc định bị bỏ qua.

Chạy khi có hai biến môi trường:
  LABELX_CLASSIFIER_E2E_ROOT  thư mục chứa classifier-manifest.json + checkpoint
  LABELX_CLASSIFIER_E2E_CMD   lệnh worker, vd "uv run --project <dir> labelx-classifier"

Checkpoint smoke_only (fixture tổng hợp) cho kết quả đúng cơ chế, KHÔNG phải kết quả huấn luyện
thật và không nói gì về accuracy.
"""

from __future__ import annotations

import io
import json
import os
import shlex
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from classifier.config import CLASS_MAP_VERSION, CLASSES
from orchestration.classifier_stage import execute_classifier_units
from orchestration.dispatch import run_work_unit
from orchestration.models import ClassifierUnit
from runs.models import ModelArtifact
from tests.classifier.test_stage import _env, make_run  # noqa: F401  (fixture autouse)
from vlm.contract import CropInput

ROOT = os.environ.get("LABELX_CLASSIFIER_E2E_ROOT", "")
CMD = os.environ.get("LABELX_CLASSIFIER_E2E_CMD", "")

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(not (ROOT and CMD), reason="worker/checkpoint thật chưa được cấu hình"),
]


def png(color: tuple[int, int, int], size: tuple[int, int] = (80, 50)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


class RealCrops:
    """Crop PNG thật; candidate thứ ba cố tình hỏng để thấy lý do rõ."""

    def identity(self, candidate: Any) -> str:
        return f"e2e-{candidate.pk}"

    def load(self, candidate: Any) -> CropInput:
        index = candidate.frame_number
        if index == 2:
            return CropInput(b"not an image", "image/png")
        return CropInput(png((200, 30, 30) if index == 0 else (30, 30, 200)), "image/png")


def test_real_worker_and_checkpoint_end_to_end(settings: Any, tmp_path: Path) -> None:
    manifest_path = Path(ROOT) / "classifier-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    settings.CLASSIFIER_ARTIFACT_ROOT = str(Path(ROOT).parent)
    settings.CLASSIFIER_WORKER_COMMAND = shlex.split(CMD)
    settings.CLASSIFIER_TIMEOUT_SECONDS = 600
    settings.VLM_CROP_PROVIDER = "tests.classifier.test_e2e_real_worker.RealCrops"
    settings.ORCHESTRATION_AUTO_DISPATCH = False
    artifact = ModelArtifact.objects.create(
        name=manifest["model"]["name"],
        version=manifest["model"]["version"],
        checksum=manifest["model"]["sha256"],
        class_mapping_version=CLASS_MAP_VERSION,
        class_mapping={"version": CLASS_MAP_VERSION, "classes": list(CLASSES)},
        artifact_key=Path(ROOT).name,
    )
    run = make_run(artifact=artifact)
    for unit in run.work_units.order_by("shard_index"):
        run_work_unit.apply(args=[unit.pk]).get()
    execute_classifier_units(run.pk)  # runner mặc định = SubprocessClassifierRunner thật

    units = list(ClassifierUnit.objects.filter(run_id=run.pk).order_by("candidate__frame_number"))
    assert [u.status for u in units] == ["completed", "completed", "failed"]
    good, bad = units[0], units[2]
    assert len(good.top3) == 3 and 0.0 < good.score <= 1.0 and good.margin >= 0.0
    assert good.predicted_class_name in CLASSES
    assert good.checkpoint_sha256 == manifest["model"]["sha256"]
    assert good.checkpoint_version == manifest["model"]["version"]
    assert good.checkpoint_status == manifest["training"]["status"]
    assert good.class_map_version == CLASS_MAP_VERSION and good.classifier_unknown is False
    assert bad.reason_code == "invalid_crop" and bad.crop_valid is False
