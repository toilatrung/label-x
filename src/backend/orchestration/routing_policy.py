"""Policy định tuyến classifier → Qwen `classification-routing-v0` (M04C-01, CR-115/CR-116).

Không phụ thuộc Django/DB: orchestrator và evaluation API (M04C-02) dùng chung một hàm
quyết định, và lưu `RoutingPolicy.as_record()` cùng mỗi evaluation.

Ranh giới:
- score ≥ 0,85 và margin ≥ 0,15 là NGƯỠNG ĐỊNH TUYẾN TẠM, không phải ngưỡng quality hay
  calibration; score classifier không phải xác suất đã hiệu chuẩn.
- Conflict luôn ưu tiên hơn score cao: score cao không bao giờ biến conflict thành classifier-only.
- Policy chỉ quyết định có gọi Qwen hay không; không tạo ReviewDecision/Adjudication.
- unknown là abstention, không phải lớp thứ 11.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

POLICY_NAME = "classification-routing-v0"
POLICY_VERSION = "v0"
DEFAULT_SCORE_THRESHOLD = 0.85
DEFAULT_MARGIN_THRESHOLD = 0.15


class RoutingReason(StrEnum):
    """Tập con `reason_code` của payload FE v0 do policy sinh ra."""

    CLASSIFIER_ONLY = "classifier_only"
    LOW_SCORE = "low_score"
    LOW_MARGIN = "low_margin"
    UNKNOWN = "unknown"
    LABEL_CONFLICT = "label_conflict"
    MANUAL_RECHECK = "manual_recheck"
    INVALID_CROP = "invalid_crop"
    BUDGET_EXHAUSTED = "budget_exhausted"


# Thứ tự ưu tiên khi nhiều lý do cùng đúng; lý do đầu tiên là `primary`.
_TRIGGER_PRIORITY = (
    RoutingReason.MANUAL_RECHECK,
    RoutingReason.LABEL_CONFLICT,
    RoutingReason.UNKNOWN,
    RoutingReason.LOW_SCORE,
    RoutingReason.LOW_MARGIN,
)


class RoutingPolicyError(ValueError):
    """Cấu hình policy không hợp lệ."""


def _threshold(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RoutingPolicyError(f"{name} phải là số.")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise RoutingPolicyError(f"{name} phải nằm trong [0, 1].")
    return number


@dataclass(frozen=True)
class RoutingPolicy:
    """Cấu hình bất biến; ngưỡng chỉ là routing tạm."""

    score_threshold: float = DEFAULT_SCORE_THRESHOLD
    margin_threshold: float = DEFAULT_MARGIN_THRESHOLD

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> RoutingPolicy:
        """Đọc từ `ConfigVersion.thresholds["classification_routing"]`; thiếu → mặc định."""
        if config is None:
            return cls()
        unknown = set(config) - {"score_threshold", "margin_threshold"}
        if unknown:
            raise RoutingPolicyError(f"Khoá không hỗ trợ: {sorted(unknown)}.")
        return cls(
            score_threshold=_threshold(
                config.get("score_threshold", DEFAULT_SCORE_THRESHOLD), "score_threshold"
            ),
            margin_threshold=_threshold(
                config.get("margin_threshold", DEFAULT_MARGIN_THRESHOLD), "margin_threshold"
            ),
        )

    def as_record(self) -> dict[str, Any]:
        """Bản ghi lưu theo evaluation, kèm SHA-256 của nội dung chuẩn hoá."""
        body = {
            "name": POLICY_NAME,
            "version": POLICY_VERSION,
            "score_threshold": self.score_threshold,
            "margin_threshold": self.margin_threshold,
            "threshold_semantics": "routing_temporary",
        }
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {**body, "policy_sha256": digest}


@dataclass(frozen=True)
class RoutingInput:
    """Dữ kiện của một candidate; không chứa prompt, ảnh hay secret."""

    crop_valid: bool = True
    classifier_unknown: bool = False
    predicted_class_id: str | None = None
    annotated_class_id: str | None = None
    score: float | None = None
    margin: float | None = None
    manual_recheck: bool = False
    budget_exhausted: bool = False


@dataclass(frozen=True)
class RoutingDecision:
    """Kết quả định tuyến; `reasons[0]` luôn bằng `primary`."""

    primary: RoutingReason
    reasons: tuple[RoutingReason, ...]
    call_qwen: bool
    human_review_required: bool
    policy: Mapping[str, Any]


def _valid_number(value: float | None) -> bool:
    return (
        value is not None
        and not isinstance(value, bool)
        and isinstance(value, int | float)
        and math.isfinite(value)
    )


def _trigger_reasons(policy: RoutingPolicy, data: RoutingInput) -> list[RoutingReason]:
    found: set[RoutingReason] = set()
    if data.manual_recheck:
        found.add(RoutingReason.MANUAL_RECHECK)
    if (
        data.predicted_class_id is not None
        and data.annotated_class_id is not None
        and data.predicted_class_id != data.annotated_class_id
    ):
        found.add(RoutingReason.LABEL_CONFLICT)
    if data.classifier_unknown:
        found.add(RoutingReason.UNKNOWN)
    # Thiếu/NaN score hoặc margin coi như không đủ tin cậy, không coi là đạt ngưỡng.
    if not _valid_number(data.score) or data.score < policy.score_threshold:  # type: ignore[operator]
        found.add(RoutingReason.LOW_SCORE)
    if not _valid_number(data.margin) or data.margin < policy.margin_threshold:  # type: ignore[operator]
        found.add(RoutingReason.LOW_MARGIN)
    return [reason for reason in _TRIGGER_PRIORITY if reason in found]


def route(policy: RoutingPolicy, data: RoutingInput) -> RoutingDecision:
    """Quyết định có gọi Qwen hay không; hàm thuần, tất định.

    Thứ tự: crop lỗi (không có gì để gửi) → các lý do trigger; nếu cần Qwen mà hết budget
    thì không gọi và chuyển người review. Không có trigger → classifier_only.
    """
    record = policy.as_record()
    if not data.crop_valid:
        return RoutingDecision(
            primary=RoutingReason.INVALID_CROP,
            reasons=(RoutingReason.INVALID_CROP,),
            call_qwen=False,
            human_review_required=True,
            policy=record,
        )
    triggers = _trigger_reasons(policy, data)
    if not triggers:
        return RoutingDecision(
            primary=RoutingReason.CLASSIFIER_ONLY,
            reasons=(RoutingReason.CLASSIFIER_ONLY,),
            call_qwen=False,
            human_review_required=False,
            policy=record,
        )
    if data.budget_exhausted:
        return RoutingDecision(
            primary=RoutingReason.BUDGET_EXHAUSTED,
            reasons=(RoutingReason.BUDGET_EXHAUSTED, *triggers),
            call_qwen=False,
            human_review_required=True,
            policy=record,
        )
    return RoutingDecision(
        primary=triggers[0],
        reasons=tuple(triggers),
        call_qwen=True,
        human_review_required=False,
        policy=record,
    )


# Adapter tạm: tên field candidate sẽ được chốt ở #286; chỉ sửa bảng này, không đụng route().
CANDIDATE_FIELD_MAP = {
    "crop_valid": "crop_valid",
    "classifier_unknown": "unknown",
    "predicted_class_id": "class_id",
    "annotated_class_id": "annotated_class_id",
    "score": "score",
    "margin": "margin",
}


def routing_input_from_candidate(
    candidate: Mapping[str, Any],
    *,
    manual_recheck: bool = False,
    budget_exhausted: bool = False,
) -> RoutingInput:
    """Dựng RoutingInput từ dict candidate; field thiếu → giá trị an toàn (không đủ tin cậy)."""
    get = {key: candidate.get(name) for key, name in CANDIDATE_FIELD_MAP.items()}
    return RoutingInput(
        crop_valid=get["crop_valid"] is not False,
        classifier_unknown=bool(get["classifier_unknown"]),
        predicted_class_id=get["predicted_class_id"],
        annotated_class_id=get["annotated_class_id"],
        score=get["score"],
        margin=get["margin"],
        manual_recheck=manual_recheck,
        budget_exhausted=budget_exhausted,
    )
