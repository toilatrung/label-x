"""Policy định tuyến Faster R-CNN → Qwen (M04C-01, CR-117).

Không phụ thuộc Django/DB: orchestrator và evaluation API (M04C-02) dùng chung một hàm
quyết định, và lưu `RoutingPolicy.as_record()` cùng mỗi evaluation.

Ranh giới:
- confidence ≥ 0,85 là NGƯỠNG ĐỊNH TUYẾN TẠM, không phải ngưỡng quality hay calibration.
- M-04 v0 chỉ dùng confidence top-1. Faster R-CNN không trả phân bố đầy đủ (kể cả background)
  nên KHÔNG có margin và trigger `low_margin` bị vô hiệu cho tới khi worker cung cấp phân bố đó.
- Detection không ghép annotation (hoặc ngược lại) ⇒ `detector_no_match`: chuyển thẳng reviewer,
  không gọi Qwen.
- Detector chỉ được tin khi evidence mang `artifact_verified is True` (manifest + checksum +
  class map đã xác minh ở adapter); không có mặc định tin cậy.
- Conflict luôn ưu tiên hơn score cao.
- Policy chỉ quyết định có gọi Qwen hay không; không tạo ReviewDecision/Adjudication.
- Detector không dùng được hoặc evidence sai kiểu vẫn gọi Qwen làm fallback.

Tên policy và các reason `classifier_*` được giữ để tương thích payload FE v0 đã đóng băng; nguồn
runtime thực tế là candidate của engine `detector`, không có classifier riêng.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

POLICY_NAME = "classification-routing-v0"
POLICY_VERSION = "v0"
DEFAULT_SCORE_THRESHOLD = 0.85
DEFAULT_MARGIN_THRESHOLD = 0.15


class RoutingReason(StrEnum):
    """Tập con `reason_code` của payload FE v0 do policy sinh ra."""

    # `classifier_*`: tên tương thích payload FE v0; runtime là detector, không có classifier.
    CLASSIFIER_ONLY = "classifier_only"
    LOW_SCORE = "low_score"
    # Vô hiệu ở M-04 v0: không có margin thật nên policy không bao giờ sinh reason này.
    LOW_MARGIN = "low_margin"
    UNKNOWN = "unknown"
    LABEL_CONFLICT = "label_conflict"
    DETECTOR_NO_MATCH = "detector_no_match"
    MANUAL_RECHECK = "manual_recheck"
    INVALID_CROP = "invalid_crop"
    BUDGET_EXHAUSTED = "budget_exhausted"
    # Tên tương thích FE v0; nguồn runtime hiện là detector theo CR-117.
    CLASSIFIER_UNTRUSTED = "classifier_untrusted"
    CLASSIFIER_UNAVAILABLE = "classifier_unavailable"


# Thứ tự ưu tiên khi nhiều lý do cùng đúng; lý do đầu tiên là `primary`.
_TRIGGER_PRIORITY = (
    RoutingReason.DETECTOR_NO_MATCH,
    RoutingReason.MANUAL_RECHECK,
    RoutingReason.LABEL_CONFLICT,
    RoutingReason.UNKNOWN,
    RoutingReason.CLASSIFIER_UNAVAILABLE,
    RoutingReason.CLASSIFIER_UNTRUSTED,
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

    def __post_init__(self) -> None:
        # Dựng trực tiếp cũng phải hợp lệ: nan/inf/ngoài [0,1]/bool/chuỗi đều lỗi.
        _threshold(self.score_threshold, "score_threshold")
        _threshold(self.margin_threshold, "margin_threshold")

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> RoutingPolicy:
        """Đọc từ `ConfigVersion.thresholds["classification_routing"]`; thiếu → mặc định."""
        if config is None:
            return cls()
        if not isinstance(config, Mapping):
            raise RoutingPolicyError("classification_routing phải là object.")
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
    source_unknown: bool = False
    predicted_class_id: int | None = None
    annotated_class_id: int | None = None
    score: float | None = None
    margin: float | None = None
    manual_recheck: bool = False
    budget_exhausted: bool = False
    # False: detector không có/lỗi hạ tầng/dữ liệu sai kiểu ⇒ reason tương thích
    # `classifier_unavailable`.
    source_available: bool = True
    source_trusted: bool = False
    # Detection/annotation không ghép một-một ⇒ detector_no_match (reviewer, không Qwen).
    detector_no_match: bool = False
    # "verified" khi adapter đã xác minh manifest/checksum/class map; ngược lại "unverified".
    checkpoint_status: str = ""


@dataclass(frozen=True)
class RoutingDecision:
    """Kết quả định tuyến; `reasons[0]` luôn bằng `primary`.

    `checkpoint_status` ("verified"/"unverified") là trạng thái xác minh artifact, KHÔNG phải kết
    luận về chất lượng mô hình; nguồn không verified ⇒ `classifier_untrusted`, gọi Qwen và
    `human_review_required`.
    """

    primary: RoutingReason
    reasons: tuple[RoutingReason, ...]
    call_qwen: bool
    human_review_required: bool
    policy: Mapping[str, Any]
    checkpoint_status: str = ""


def _valid_number(value: object) -> bool:
    """Số hữu hạn trong [0, 1]; ngoài miền (vd 5.0), bool, None, nan/inf ⇒ không đủ tin cậy."""
    return (
        value is not None
        and not isinstance(value, bool)
        and isinstance(value, int | float)
        and math.isfinite(value)
        and 0.0 <= value <= 1.0
    )


def _real_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _trigger_reasons(policy: RoutingPolicy, data: RoutingInput) -> list[RoutingReason]:
    found: set[RoutingReason] = set()
    if data.manual_recheck:
        found.add(RoutingReason.MANUAL_RECHECK)
    if not data.source_available:
        found.add(RoutingReason.CLASSIFIER_UNAVAILABLE)
        # Không có kết quả detector thì không có score/margin để gọi là "thấp".
        return [reason for reason in _TRIGGER_PRIORITY if reason in found]
    # Chỉ so nhãn khi cả hai là int thật; kiểu khác không bao giờ thành conflict giả.
    if (
        _real_int(data.predicted_class_id)
        and _real_int(data.annotated_class_id)
        and data.predicted_class_id != data.annotated_class_id
    ):
        found.add(RoutingReason.LABEL_CONFLICT)
    if data.source_unknown:
        found.add(RoutingReason.UNKNOWN)
    if not data.source_trusted:
        found.add(RoutingReason.CLASSIFIER_UNTRUSTED)
    # Thiếu/NaN/ngoài [0,1] coi như không đủ tin cậy, không coi là đạt ngưỡng.
    if not _valid_number(data.score) or data.score < policy.score_threshold:  # type: ignore[operator]
        found.add(RoutingReason.LOW_SCORE)
    # Cố ý không xét data.margin: v0 không có margin thật, không suy diễn từ detection output.
    return [reason for reason in _TRIGGER_PRIORITY if reason in found]


def route(policy: RoutingPolicy, data: RoutingInput) -> RoutingDecision:
    """Quyết định có gọi Qwen hay không; hàm thuần, tất định.

    LƯU Ý: route() tin `RoutingInput` đã chuẩn hoá. Gọi trực tiếp với nhãn sai kiểu (chuỗi, bool,
    float) thì phép so conflict BỎ QUA (không báo conflict giả nhưng cũng không báo lỗi). Mọi đường
    vào phải đi qua `routing_input_from_candidate`, hàm này biến detector evidence sai kiểu thành
    nguồn không khả dụng.

    Thứ tự: crop lỗi (không có gì để gửi) → các lý do trigger; nếu cần Qwen mà hết budget
    thì không gọi và chuyển người review. Không có trigger → classifier_only.
    """
    record = policy.as_record()
    if data.detector_no_match:
        return RoutingDecision(
            primary=RoutingReason.DETECTOR_NO_MATCH,
            reasons=(RoutingReason.DETECTOR_NO_MATCH,),
            call_qwen=False,
            human_review_required=True,
            policy=record,
            checkpoint_status=data.checkpoint_status,
        )
    if data.crop_valid is not True:  # chuỗi "false"/None cũng không phải crop hợp lệ
        return RoutingDecision(
            primary=RoutingReason.INVALID_CROP,
            reasons=(RoutingReason.INVALID_CROP,),
            call_qwen=False,
            human_review_required=True,
            policy=record,
            checkpoint_status=data.checkpoint_status,
        )
    triggers = _trigger_reasons(policy, data)
    if not triggers:
        return RoutingDecision(
            primary=RoutingReason.CLASSIFIER_ONLY,
            reasons=(RoutingReason.CLASSIFIER_ONLY,),
            call_qwen=False,
            human_review_required=False,
            policy=record,
            checkpoint_status=data.checkpoint_status,
        )
    if data.budget_exhausted:
        return RoutingDecision(
            primary=RoutingReason.BUDGET_EXHAUSTED,
            reasons=(RoutingReason.BUDGET_EXHAUSTED, *triggers),
            call_qwen=False,
            human_review_required=True,
            policy=record,
            checkpoint_status=data.checkpoint_status,
        )
    return RoutingDecision(
        primary=triggers[0],
        reasons=tuple(triggers),
        call_qwen=True,
        # Nguồn không đáng tin: gọi Qwen VÀ yêu cầu người xem, không để qua mặt review.
        human_review_required=RoutingReason.CLASSIFIER_UNTRUSTED in triggers,
        policy=record,
        checkpoint_status=data.checkpoint_status,
    )


DETECTOR_ENGINE = "detector"
ANNOTATED_CLASS_KEY = "annotated_class_id"


def routing_input_from_candidate(
    candidate: Mapping[str, Any],
    *,
    manual_recheck: bool = False,
    budget_exhausted: bool = False,
) -> RoutingInput:
    """Dựng input trực tiếp từ candidate Faster R-CNN.

    Contract detector dùng ``engine=detector`` và ``evidence`` chứa ``class_id``, ``class_name``
    cùng ``confidence``. Detector hiện không trả top-k/margin nên margin để ``None``. Candidate
    từ engine khác hoặc evidence sai schema được định tuyến an toàn sang Qwen.
    """
    raw = candidate.get("evidence")
    if candidate.get("engine") != DETECTOR_ENGINE or not isinstance(raw, Mapping):
        return RoutingInput(
            source_available=False,
            manual_recheck=manual_recheck,
            budget_exhausted=budget_exhausted,
        )
    evidence: Mapping[str, Any] = raw
    trusted = evidence.get("artifact_verified") is True
    common: dict[str, Any] = {
        "manual_recheck": manual_recheck,
        "budget_exhausted": budget_exhausted,
        "source_trusted": trusted,
        "checkpoint_status": "verified" if trusted else "unverified",
    }
    status = evidence.get("match_status")
    if status in ("unmatched_detection", "unmatched_annotation"):
        return RoutingInput(detector_no_match=True, **common)
    if status != "matched":
        # Thiếu/lạ match_status: không đủ dữ kiện để tin ⇒ fail closed sang Qwen.
        return RoutingInput(source_available=False, **common)
    predicted = evidence.get("class_id")
    score = evidence.get("confidence")
    annotated = evidence.get(ANNOTATED_CLASS_KEY, candidate.get(ANNOTATED_CLASS_KEY))
    for value in (predicted, annotated):
        if value is not None and not _real_int(value):
            return RoutingInput(source_available=False, **common)
    if predicted is None or not _valid_number(score):
        return RoutingInput(source_available=False, **common)
    return RoutingInput(
        predicted_class_id=predicted,
        annotated_class_id=annotated,
        score=float(cast(int | float, score)),
        margin=None,
        **common,
    )
