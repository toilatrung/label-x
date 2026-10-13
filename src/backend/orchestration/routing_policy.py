"""Policy định tuyến classifier → Qwen `classification-routing-v0` (M04C-01, CR-115/CR-116).

Không phụ thuộc Django/DB: orchestrator và evaluation API (M04C-02) dùng chung một hàm
quyết định, và lưu `RoutingPolicy.as_record()` cùng mỗi evaluation.

Ranh giới:
- score ≥ 0,85 và margin ≥ 0,15 là NGƯỠNG ĐỊNH TUYẾN TẠM, không phải ngưỡng quality hay
  calibration; score classifier không phải xác suất đã hiệu chuẩn.
- Conflict luôn ưu tiên hơn score cao: score cao không bao giờ biến conflict thành classifier-only.
- Policy chỉ quyết định có gọi Qwen hay không; không tạo ReviewDecision/Adjudication.
- unknown là abstention, không phải lớp thứ 11.
- Classifier chỉ đáng tin khi `checkpoint_status == "trained"`: smoke_only, rỗng hoặc thiếu coi như
  KHÔNG đáng tin ⇒ luôn gọi Qwen và yêu cầu người xem (`classifier_untrusted`). Quyết định tạm
  an toàn, đảo lại được khi PO chốt.
- Classifier không dùng được (thiếu, lỗi hạ tầng, dữ liệu sai kiểu) ⇒ `classifier_unavailable`,
  vẫn gọi Qwen làm fallback nhưng không gọi là low_score.
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
    # Mở rộng so với payload FE v0 (cần ghi vào #278): classifier không đáng tin / không dùng được.
    CLASSIFIER_UNTRUSTED = "classifier_untrusted"
    CLASSIFIER_UNAVAILABLE = "classifier_unavailable"


# Thứ tự ưu tiên khi nhiều lý do cùng đúng; lý do đầu tiên là `primary`.
_TRIGGER_PRIORITY = (
    RoutingReason.MANUAL_RECHECK,
    RoutingReason.LABEL_CONFLICT,
    RoutingReason.UNKNOWN,
    RoutingReason.CLASSIFIER_UNAVAILABLE,
    RoutingReason.CLASSIFIER_UNTRUSTED,
    RoutingReason.LOW_SCORE,
    RoutingReason.LOW_MARGIN,
)
TRUSTED_CHECKPOINT = "trained"


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
    classifier_unknown: bool = False
    predicted_class_id: int | None = None
    annotated_class_id: int | None = None
    score: float | None = None
    margin: float | None = None
    manual_recheck: bool = False
    budget_exhausted: bool = False
    # False: classifier không có/lỗi hạ tầng/dữ liệu sai kiểu ⇒ classifier_unavailable.
    classifier_available: bool = True
    # "trained" mới đáng tin; "smoke_only", rỗng hoặc thiếu ⇒ classifier_untrusted.
    checkpoint_status: str = ""


@dataclass(frozen=True)
class RoutingDecision:
    """Kết quả định tuyến; `reasons[0]` luôn bằng `primary`.

    `checkpoint_status` được chuyển nguyên vào evidence để reviewer thấy kết quả đến từ
    checkpoint smoke_only (không phải mô hình đã huấn luyện thật); khác "trained" ⇒ policy ép gọi
    Qwen và `human_review_required`.
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
    if not data.classifier_available:
        found.add(RoutingReason.CLASSIFIER_UNAVAILABLE)
        # Không có kết quả classifier thì không có score/margin để gọi là "thấp".
        return [reason for reason in _TRIGGER_PRIORITY if reason in found]
    # Chỉ so nhãn khi cả hai là int thật; kiểu khác không bao giờ thành conflict giả.
    if (
        _real_int(data.predicted_class_id)
        and _real_int(data.annotated_class_id)
        and data.predicted_class_id != data.annotated_class_id
    ):
        found.add(RoutingReason.LABEL_CONFLICT)
    if data.classifier_unknown:
        found.add(RoutingReason.UNKNOWN)
    if data.checkpoint_status != TRUSTED_CHECKPOINT:
        found.add(RoutingReason.CLASSIFIER_UNTRUSTED)
    # Thiếu/NaN/ngoài [0,1] coi như không đủ tin cậy, không coi là đạt ngưỡng.
    if not _valid_number(data.score) or data.score < policy.score_threshold:  # type: ignore[operator]
        found.add(RoutingReason.LOW_SCORE)
    if not _valid_number(data.margin) or data.margin < policy.margin_threshold:  # type: ignore[operator]
        found.add(RoutingReason.LOW_MARGIN)
    return [reason for reason in _TRIGGER_PRIORITY if reason in found]


def route(policy: RoutingPolicy, data: RoutingInput) -> RoutingDecision:
    """Quyết định có gọi Qwen hay không; hàm thuần, tất định.

    Unknown (abstention) do policy quyết: contract classifier luôn trả classifier_unknown=false,
    nên adapter coi "completed mà predicted_class_id null" là unknown (xem
    routing_input_from_candidate). Không có lớp thứ 11.

    Thứ tự: crop lỗi (không có gì để gửi) → các lý do trigger; nếu cần Qwen mà hết budget
    thì không gọi và chuyển người review. Không có trigger → classifier_only.
    """
    record = policy.as_record()
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
        # Classifier không đáng tin: gọi Qwen VÀ yêu cầu người xem, không để qua mặt review.
        human_review_required=RoutingReason.CLASSIFIER_UNTRUSTED in triggers,
        policy=record,
        checkpoint_status=data.checkpoint_status,
    )


# Adapter theo contract classifier chính thức của #286 (feat/M-04-b-classifier @3a9ca080):
# `Candidate.classifier` là object|null. Chỉ sửa phần này khi contract đổi, không đụng route().
CLASSIFIER_KEY = "classifier"
ANNOTATED_CLASS_KEY = "annotated_class_id"
# Lý do classifier thất bại vì crop (không phải hạ tầng) ⇒ crop_valid=false.
_CROP_FAILURES = frozenset({"invalid_crop", "box_too_small"})


class ClassifierNotReadyError(RuntimeError):
    """Classifier pending/running: orchestration phải CHỜ, không quyết định hay gọi Qwen sớm."""


def routing_input_from_candidate(
    candidate: Mapping[str, Any],
    *,
    manual_recheck: bool = False,
    budget_exhausted: bool = False,
) -> RoutingInput:
    """Dựng RoutingInput từ candidate; dữ liệu thiếu/sai kiểu ⇒ không đủ tin cậy, không đoán.

    - `classifier` null/không phải object, failed vì hạ tầng (inference_error, timeout,
      checkpoint_unavailable, checksum_mismatch...), cancelled hoặc có số/nhãn sai kiểu ⇒
      `classifier_unavailable` (vẫn gọi Qwen, không phải low_score).
    - `pending`/`running` ⇒ ClassifierNotReadyError (chờ).
    - `crop_valid` phải là bool thật; False, failed vì crop (invalid_crop/box_too_small) hoặc
      không phải bool ⇒ invalid_crop. Không có classifier thì không giả định crop hỏng.
    - Contract luôn trả `classifier_unknown=false`; abstention do policy quyết: classifier completed
      mà không có lớp dự đoán (`predicted_class_id` null) được coi là unknown.
    - `checkpoint_status` khác "trained" ⇒ classifier_untrusted (xem `route`).
    """
    raw = candidate.get(CLASSIFIER_KEY)
    if not isinstance(raw, Mapping):
        return RoutingInput(
            classifier_available=False,
            manual_recheck=manual_recheck,
            budget_exhausted=budget_exhausted,
        )
    clf: Mapping[str, Any] = raw
    status = clf.get("status")
    if status in ("pending", "running"):
        raise ClassifierNotReadyError(f"classifier {status}")
    crop_ok = clf.get("crop_valid") is True and clf.get("reason_code") not in _CROP_FAILURES
    common: dict[str, Any] = {
        "crop_valid": crop_ok,
        "manual_recheck": manual_recheck,
        "budget_exhausted": budget_exhausted,
        "checkpoint_status": str(clf.get("checkpoint_status") or ""),
    }
    if not crop_ok:
        return RoutingInput(classifier_available=False, **common)
    if status != "completed":  # failed (hạ tầng), cancelled hoặc giá trị lạ
        return RoutingInput(classifier_available=False, **common)
    predicted = clf.get("predicted_class_id")
    annotated = clf.get(ANNOTATED_CLASS_KEY, candidate.get(ANNOTATED_CLASS_KEY))
    for value in (predicted, annotated):
        if value is not None and not _real_int(value):
            return RoutingInput(classifier_available=False, **common)
    return RoutingInput(
        classifier_unknown=bool(clf.get("classifier_unknown")) or predicted is None,
        predicted_class_id=predicted,
        annotated_class_id=annotated,
        score=clf.get("score"),
        margin=clf.get("margin"),
        **common,
    )
