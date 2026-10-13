"""Hợp đồng Qwen adapter (M04A-01, CR-116): input crop, taxonomy, candidate context; output JSON.

Thuần Python, không phụ thuộc Django/HTTP, để worker, orchestrator và test dùng chung.
- Prompt do backend sở hữu theo `prompt_version`; FE không gửi prompt/model/ảnh.
- Không phiên bản Qwen nào được giả định hỗ trợ JSON schema phía provider: phản hồi luôn được
  validate ở đây (`parse_response`); sai schema/nhãn ngoài taxonomy -> VlmParseError.
- Kết quả VLM chỉ là đề xuất/evidence, không phải quyết định; `uncertain` là abstention,
  không có lớp thứ 11.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from vlm.config import VlmConfig
from vlm.errors import VlmInvalidCropError, VlmParseError, VlmReasonCode

UNCERTAIN_LABEL = "uncertain"
ALLOWED_CROP_MIME = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_CROP_BYTES = 2 * 1024 * 1024  # crop nhỏ; ảnh nhúng inline (base64) nên giới hạn chặt
MAX_RATIONALE_CHARS = 500

# Schema nội bộ của output (JSON Schema draft 2020-12 dạng tài liệu; backend tự validate).
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["label"],
    "additionalProperties": False,
    "properties": {
        "label": {"type": "string", "description": "class_id trong taxonomy hoặc 'uncertain'"},
        "rationale": {"type": "string", "maxLength": MAX_RATIONALE_CHARS},
    },
}


class VlmStatus(StrEnum):
    """Kết quả một đơn vị VLM: engine checked|failed|not_checked; uncertain là kết luận AI."""

    CHECKED = "checked"
    UNCERTAIN = "uncertain"
    FAILED = "failed"
    NOT_CHECKED = "not_checked"


@dataclass(frozen=True)
class TaxonomyLabel:
    class_id: str
    class_name: str


@dataclass(frozen=True)
class CandidateContext:
    """Ngữ cảnh candidate đưa cho Qwen; chỉ metadata cần thiết, không chứa PII/đường dẫn."""

    candidate_id: str
    snapshot_revision: str
    current_label: str | None = None  # nhãn annotator/classifier đang tranh chấp (class_id)
    classifier_top3: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class CropInput:
    data: bytes = field(repr=False)  # repr ẩn bytes để không rò vào log
    mime_type: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


@dataclass(frozen=True)
class VlmRequest:
    crop: CropInput
    taxonomy: tuple[TaxonomyLabel, ...]
    context: CandidateContext
    config: VlmConfig


@dataclass(frozen=True)
class VlmVerdict:
    """Phản hồi đã validate. `label` là class_id hoặc None khi uncertain."""

    status: VlmStatus
    label: str | None
    rationale: str | None  # lời giải thích của model, KHÔNG phải bằng chứng đã xác minh


@dataclass(frozen=True)
class VlmResult:
    """Kết quả cuối của một đơn vị, có reason_code khi không phải checked."""

    status: VlmStatus
    label: str | None = None
    rationale: str | None = None
    reason_code: VlmReasonCode | None = None
    attempts: int = 0
    request_id: str | None = None  # ID provider đã redacted/cắt ngắn
    model: str | None = None
    prompt_version: str | None = None
    crop_sha256: str | None = None


class VlmClient(Protocol):
    """Cổng gọi provider (hiện thực ở M04A-02). Mỗi lần gọi = một attempt thực tính budget."""

    def complete(self, request: VlmRequest) -> tuple[str, str | None]:
        """Trả (nội dung văn bản thô, request_id). Ném VlmProviderError khi lỗi provider."""
        ...


def validate_crop(crop: CropInput) -> None:
    if crop.mime_type not in ALLOWED_CROP_MIME:
        raise VlmInvalidCropError("MIME crop không được hỗ trợ.")
    if not crop.data:
        raise VlmInvalidCropError("Crop rỗng.")
    if len(crop.data) > MAX_CROP_BYTES:
        raise VlmInvalidCropError("Crop vượt kích thước tối đa.")
    if not _magic_matches(crop.data, crop.mime_type):
        raise VlmInvalidCropError("Nội dung crop không khớp MIME khai báo.")


def _magic_matches(data: bytes, mime: str) -> bool:
    if mime == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if mime == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def build_prompt(
    prompt_version: str, taxonomy: Sequence[TaxonomyLabel], context: CandidateContext
) -> str:
    """Prompt phía backend. Bản duy nhất hiện có: `vlm-prompt-v0`."""
    if prompt_version != "vlm-prompt-v0":
        raise VlmParseError(f"prompt_version không biết: {prompt_version}")
    labels = "\n".join(f"- {t.class_id}: {t.class_name}" for t in taxonomy)
    hint = ""
    if context.current_label is not None:
        hint = f"\nNhãn đang được đề xuất cho vùng này: {context.current_label}."
    return (
        "Bạn kiểm tra một ảnh crop của một đối tượng trong bộ dữ liệu giao thông.\n"
        "Chọn đúng MỘT class_id trong danh sách dưới đây nếu chắc chắn; nếu ảnh mờ, bị che, "
        f'hoặc không khớp lớp nào thì trả "{UNCERTAIN_LABEL}".\n'
        f"Danh sách lớp:\n{labels}{hint}\n"
        'Trả lời CHỈ bằng một đối tượng JSON: {"label": "<class_id hoặc uncertain>", '
        '"rationale": "<tối đa 1-2 câu>"}. Không thêm văn bản khác.'
    )


_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def parse_response(text: str, taxonomy: Sequence[TaxonomyLabel]) -> VlmVerdict:
    """Validate phản hồi thô theo OUTPUT_SCHEMA và taxonomy; ném VlmParseError nếu sai."""
    body = text.strip()
    match = _FENCE.match(body)
    if match:
        body = match.group(1)
    try:
        data = json.loads(body)
    except (ValueError, RecursionError) as exc:
        raise VlmParseError("Phản hồi không phải JSON hợp lệ.") from exc
    if not isinstance(data, Mapping):
        raise VlmParseError("Phản hồi JSON phải là object.")
    extra = set(data) - {"label", "rationale"}
    if extra:
        raise VlmParseError("Phản hồi có khoá ngoài schema.")
    label = data.get("label")
    if not isinstance(label, str):
        raise VlmParseError("Thiếu 'label' dạng chuỗi.")
    rationale = data.get("rationale")
    if rationale is not None:
        if not isinstance(rationale, str) or len(rationale) > MAX_RATIONALE_CHARS:
            raise VlmParseError("'rationale' sai kiểu hoặc quá dài.")
    if label == UNCERTAIN_LABEL:
        return VlmVerdict(VlmStatus.UNCERTAIN, None, rationale)
    if label not in {t.class_id for t in taxonomy}:
        raise VlmParseError("Nhãn ngoài taxonomy.")
    return VlmVerdict(VlmStatus.CHECKED, label, rationale)
