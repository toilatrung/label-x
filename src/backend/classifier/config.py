"""Cấu hình classifier ConvNeXt Tiny (M04B-03): `models.classifier` + kiểm ModelArtifact.

`models.classifier = {"model_artifact_id": <int>}` trỏ tới `runs.ModelArtifact` đã đăng ký
(name/version/checksum/class_mapping). Không có đường dẫn, lệnh hay secret trong config: vị trí
checkpoint và lệnh worker chỉ lấy từ settings của máy chạy.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

CLASSIFIER_ENGINE = "classifier"
CLASS_MAP_VERSION = "bdd100k-det-10-v1"
CLASSES: tuple[str, ...] = (
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
KNOWN_KEYS = frozenset({"model_artifact_id"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def validate_classifier_model_config(raw: object) -> list[str]:
    """Lỗi hình dạng của `models.classifier` (dùng khi tạo config → 400)."""
    if not isinstance(raw, Mapping):
        return ["models.classifier phải là object."]
    errors: list[str] = []
    unknown = sorted(set(raw) - KNOWN_KEYS)
    if unknown:
        errors.append(f"models.classifier có khoá không hỗ trợ: {', '.join(unknown)}.")
    artifact_id = raw.get("model_artifact_id")
    if isinstance(artifact_id, bool) or not isinstance(artifact_id, int) or artifact_id <= 0:
        errors.append("models.classifier.model_artifact_id phải là số nguyên dương.")
    return errors


def artifact_errors(artifact: Any) -> list[str]:
    """Lỗi sẵn sàng của ModelArtifact (dùng khi publish → 422): thiếu manifest/class map."""
    errors: list[str] = []
    if not _SHA256.fullmatch(str(artifact.checksum or "")):
        errors.append("ModelArtifact của classifier thiếu checksum sha256 hợp lệ.")
    if not artifact.artifact_key:
        errors.append("ModelArtifact của classifier thiếu artifact_key (vị trí manifest).")
    mapping = artifact.class_mapping
    if (
        artifact.class_mapping_version != CLASS_MAP_VERSION
        or not isinstance(mapping, Mapping)
        or mapping.get("version") != CLASS_MAP_VERSION
        or tuple(mapping.get("classes") or ()) != CLASSES
    ):
        errors.append(
            f"ModelArtifact của classifier phải có class map {CLASS_MAP_VERSION} đúng 10 lớp."
        )
    return errors


def classifier_enabled(engines: object) -> bool:
    cfg = engines.get(CLASSIFIER_ENGINE) if isinstance(engines, Mapping) else None
    return isinstance(cfg, Mapping) and cfg.get("enabled") is True


def classifier_models_ready(config_version: Any) -> bool:
    """`models.classifier` hợp lệ và ModelArtifact tồn tại với manifest/class map đúng."""
    from runs.models import ModelArtifact

    models_cfg = config_version.models or (config_version.payload or {}).get("models", {})
    raw = models_cfg.get(CLASSIFIER_ENGINE) if isinstance(models_cfg, Mapping) else None
    if not isinstance(raw, Mapping) or validate_classifier_model_config(raw):
        return False
    artifact = ModelArtifact.objects.filter(pk=raw["model_artifact_id"]).first()
    return artifact is not None and not artifact_errors(artifact)


def classifier_publish_errors(config_version: Any) -> list[str]:
    """Lỗi chặn publish khi engine classifier bật (422): thiếu manifest/class map/ModelArtifact."""
    from runs.models import ModelArtifact

    engines = config_version.engines or (config_version.payload or {}).get("engines", {})
    if not classifier_enabled(engines):
        return []
    models_cfg = config_version.models or (config_version.payload or {}).get("models", {})
    raw = models_cfg.get(CLASSIFIER_ENGINE) if isinstance(models_cfg, Mapping) else None
    if raw is None:
        return ["Engine classifier bật nhưng thiếu models.classifier (manifest/class map)."]
    errors = validate_classifier_model_config(raw)
    if errors or not isinstance(raw, Mapping):
        return errors
    artifact = ModelArtifact.objects.filter(pk=raw["model_artifact_id"]).first()
    if artifact is None:
        return ["models.classifier.model_artifact_id không trỏ tới ModelArtifact nào."]
    return artifact_errors(artifact)
