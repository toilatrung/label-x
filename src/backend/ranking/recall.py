"""Recall@k trên số lỗi đã xác minh (SRS công thức 2.1; FR-EVL-07, FR-EVL-10)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from typing import Literal

RecallStatus = Literal["computed", "insufficient_sample"]


@dataclass(frozen=True)
class RecallAtK:
    """Kết quả không bao giờ mang số khi mẫu lỗi chưa đủ: `value` và `frame_recall` là None."""

    status: RecallStatus
    k: Decimal
    frames: int
    top_frames: int
    errors_total: int
    errors_in_top: int
    frames_with_errors: int
    frames_with_errors_in_top: int
    value: float | None
    frame_recall: float | None


def recall_at_k(
    ranking: Sequence[str],
    errors_by_frame: Mapping[str, int],
    *,
    k: Decimal = Decimal("0.2"),
    e_min: int,
) -> RecallAtK:
    """|{e ∈ E : φ(e) ∈ T_k(π)}| / |E| với T_k là ⌈kN⌉ frame đầu của ranking π.

    `ranking` đã được sắp theo điểm giảm dần và đã phá hoà theo khoá cố định; mỗi lỗi trong
    `errors_by_frame` được tính một lần (không phải số frame có lỗi). |E| < e_min, kể cả |E| = 0,
    là "không đủ mẫu", không phải 0% hay 100%.
    """
    if not isinstance(k, Decimal) or not k.is_finite() or not Decimal(0) < k <= Decimal(1):
        raise ValueError("k must be a finite Decimal in (0, 1]")
    if type(e_min) is not int or e_min < 1:
        raise ValueError("e_min must be a positive integer")
    if len(set(ranking)) != len(ranking):
        raise ValueError("ranking must not repeat a frame")
    unknown = sorted(set(errors_by_frame) - set(ranking))
    if unknown:
        raise ValueError(f"errors reference frames outside the ranking: {unknown}")
    if any(type(count) is not int or count < 0 for count in errors_by_frame.values()):
        raise ValueError("error counts must be non-negative integers")

    # Decimal, không dùng float: 0.2 * 15 = 3.0000000000000004 sẽ bị ceil thành 4.
    top_frames = int((Decimal(len(ranking)) * k).to_integral_value(ROUND_CEILING))
    top = set(ranking[:top_frames])
    errors_total = sum(errors_by_frame.values())
    errors_in_top = sum(count for frame, count in errors_by_frame.items() if frame in top)
    with_errors = {frame for frame, count in errors_by_frame.items() if count > 0}
    with_errors_in_top = len(with_errors & top)
    enough = errors_total >= e_min
    return RecallAtK(
        status="computed" if enough else "insufficient_sample",
        k=k,
        frames=len(ranking),
        top_frames=top_frames,
        errors_total=errors_total,
        errors_in_top=errors_in_top,
        frames_with_errors=len(with_errors),
        frames_with_errors_in_top=with_errors_in_top,
        value=errors_in_top / errors_total if enough else None,
        frame_recall=with_errors_in_top / len(with_errors) if enough else None,
    )
