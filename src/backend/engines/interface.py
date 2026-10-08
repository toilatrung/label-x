"""Quy tắc tham chiếu của engine interface (docs/04-api/engine-interface.html, DEC-010).

Không phụ thuộc Django: orchestrator (E-08) và báo cáo coverage dùng chung một cách tính.
- Coverage ledger theo engine (FR-AGG-04): đơn vị failed vẫn nằm trong mẫu số.
- Trạng thái công khai (FR-AGG-05, B-19): `checked` chỉ khi mọi đơn vị eligible đã completed.
Enum trùng contract docs/04-api/openapi.yaml; test giữ hai nguồn khớp nhau.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class EngineStatus(StrEnum):
    """Trạng thái công khai, schema `EngineStatus`."""

    RUNNING = "running"
    CHECKED = "checked"
    PARTIAL = "partial"
    FAILED = "failed"
    NOT_CHECKED = "not_checked"


class NotCheckedReason(StrEnum):
    """Lý do không kiểm, schema `NotCheckedReason` (SRS tab:enginestates)."""

    DISABLED = "disabled"
    NO_MODEL = "no_model"
    NO_REFERENCE = "no_reference"
    NOT_APPLICABLE = "not_applicable"
    NOT_TRIGGERED = "not_triggered"


# Đơn vị ngoài phạm vi áp dụng: không tính vào mẫu số (tab:enginestates).
EXCLUDED_FROM_ELIGIBLE = frozenset(
    {NotCheckedReason.NOT_APPLICABLE, NotCheckedReason.NOT_TRIGGERED}
)


class EngineUnitOutcome(StrEnum):
    """Trạng thái nội bộ của một đơn vị, schema `EngineUnitOutcome`."""

    PENDING = "pending"
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_CHECKED = "not_checked"


UNFINISHED_OUTCOMES = frozenset(
    {EngineUnitOutcome.PENDING, EngineUnitOutcome.RUNNING, EngineUnitOutcome.RETRYING}
)

UNIT_PUBLIC_STATUS: Mapping[EngineUnitOutcome, EngineStatus] = {
    EngineUnitOutcome.PENDING: EngineStatus.RUNNING,
    EngineUnitOutcome.RUNNING: EngineStatus.RUNNING,
    EngineUnitOutcome.RETRYING: EngineStatus.RUNNING,
    EngineUnitOutcome.COMPLETED: EngineStatus.CHECKED,
    EngineUnitOutcome.FAILED: EngineStatus.FAILED,
    EngineUnitOutcome.NOT_CHECKED: EngineStatus.NOT_CHECKED,
}


class EngineInternalState(StrEnum):
    """Trạng thái nội bộ của engine trong run, schema `EngineInternalState`."""

    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    PARTIALLY_SUCCEEDED = "partially_succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DISABLED = "disabled"
    MODEL_UNAVAILABLE = "model_unavailable"
    REFERENCE_UNAVAILABLE = "reference_unavailable"
    NOT_APPLICABLE = "not_applicable"


INTERNAL_PUBLIC_STATUS: Mapping[EngineInternalState, EngineStatus] = {
    EngineInternalState.QUEUED: EngineStatus.RUNNING,
    EngineInternalState.RUNNING: EngineStatus.RUNNING,
    EngineInternalState.RETRYING: EngineStatus.RUNNING,
    EngineInternalState.SUCCEEDED: EngineStatus.CHECKED,
    EngineInternalState.PARTIALLY_SUCCEEDED: EngineStatus.PARTIAL,
    EngineInternalState.FAILED: EngineStatus.FAILED,
    EngineInternalState.CANCELLED: EngineStatus.PARTIAL,
    EngineInternalState.DISABLED: EngineStatus.NOT_CHECKED,
    EngineInternalState.MODEL_UNAVAILABLE: EngineStatus.NOT_CHECKED,
    EngineInternalState.REFERENCE_UNAVAILABLE: EngineStatus.NOT_CHECKED,
    EngineInternalState.NOT_APPLICABLE: EngineStatus.NOT_CHECKED,
}


@dataclass(frozen=True)
class LedgerCounts:
    """Số đơn vị của một engine trong run (schema `LedgerEntry`, phần đếm)."""

    completed: int = 0
    failed: int = 0
    pending: int = 0
    not_checked_reasons: Mapping[NotCheckedReason, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        values = [self.completed, self.failed, self.pending, *self.not_checked_reasons.values()]
        if any(v < 0 for v in values):
            raise ValueError("Số đơn vị trong ledger không được âm.")

    @property
    def not_checked(self) -> int:
        return sum(self.not_checked_reasons.values())

    @property
    def total(self) -> int:
        return self.completed + self.failed + self.pending + self.not_checked

    @property
    def excluded(self) -> int:
        return sum(self.not_checked_reasons.get(r, 0) for r in EXCLUDED_FROM_ELIGIBLE)

    @property
    def eligible(self) -> int:
        """Mẫu số coverage: mọi đơn vị trong phạm vi áp dụng, kể cả failed và chưa xong."""
        return self.total - self.excluded

    @property
    def blocked(self) -> int:
        """Đơn vị eligible không kiểm do disabled/no_model/no_reference."""
        return self.not_checked - self.excluded

    @property
    def coverage(self) -> float | None:
        return self.completed / self.eligible if self.eligible else None

    @classmethod
    def from_outcomes(
        cls, outcomes: Iterable[tuple[EngineUnitOutcome, NotCheckedReason | None]]
    ) -> LedgerCounts:
        counts: Counter[EngineUnitOutcome] = Counter()
        reasons: Counter[NotCheckedReason] = Counter()
        for outcome, reason in outcomes:
            if outcome is EngineUnitOutcome.NOT_CHECKED:
                if reason is None:
                    raise ValueError("Đơn vị not_checked phải có lý do (FR-AGG-04).")
                reasons[reason] += 1
            elif reason is not None:
                raise ValueError("Chỉ đơn vị not_checked mới có lý do.")
            else:
                counts[outcome] += 1
        return cls(
            completed=counts[EngineUnitOutcome.COMPLETED],
            failed=counts[EngineUnitOutcome.FAILED],
            pending=sum(counts[o] for o in UNFINISHED_OUTCOMES),
            not_checked_reasons=dict(reasons),
        )


def public_status(ledger: LedgerCounts, *, finished: bool) -> EngineStatus:
    """Trạng thái công khai của engine từ ledger (docs/04-api/engine-interface.html §3).

    `finished` = orchestrator đã dừng engine trong run (xong, lỗi hoặc huỷ).
    """
    if ledger.pending and not finished:
        return EngineStatus.RUNNING
    if ledger.eligible == 0 or ledger.blocked == ledger.eligible:
        return EngineStatus.NOT_CHECKED
    if ledger.completed == ledger.eligible:
        return EngineStatus.CHECKED
    if ledger.completed == 0 and ledger.failed == ledger.eligible:
        return EngineStatus.FAILED
    return EngineStatus.PARTIAL
