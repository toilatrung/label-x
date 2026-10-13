"""Schema `ConfigVersion.thresholds["classification_routing"]` (M04A-01, tên policy
`classification-routing-v0`).

Chỉ kiểm hình dạng và miền giá trị khi tạo/publish config; logic định tuyến nằm ở M04C-01
(`orchestration/routing_policy.py`). Khoá và miền giá trị khớp `RoutingPolicy.from_config`.
Ngưỡng score/margin là NGƯỠNG ĐỊNH TUYẾN TẠM, không phải ngưỡng quality/calibration.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

ROUTING_THRESHOLDS_KEY = "classification_routing"
ROUTING_KEYS = frozenset({"score_threshold", "margin_threshold"})


def validate_routing_thresholds(thresholds: Mapping[str, Any]) -> list[str]:
    """Trả danh sách lỗi; rỗng nếu thiếu khoá (dùng mặc định) hoặc hợp lệ."""
    if ROUTING_THRESHOLDS_KEY not in thresholds:
        return []
    raw = thresholds[ROUTING_THRESHOLDS_KEY]
    if not isinstance(raw, Mapping):
        return [f"thresholds.{ROUTING_THRESHOLDS_KEY} phải là object."]
    errors: list[str] = []
    unknown = sorted(set(raw) - ROUTING_KEYS)
    if unknown:
        errors.append(f"thresholds.{ROUTING_THRESHOLDS_KEY} có khoá không hỗ trợ: {unknown}.")
    for key in sorted(ROUTING_KEYS & set(raw)):
        value = raw[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            or not 0.0 <= value <= 1.0
        ):
            errors.append(f"thresholds.{ROUTING_THRESHOLDS_KEY}.{key} phải là số trong [0, 1].")
    return errors
