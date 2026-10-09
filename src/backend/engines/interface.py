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
from typing import Any


@dataclass(frozen=True, order=True)
class FrameKey:
    """Stable frame identity from the public engine contract."""

    cvat_task_id: int
    frame_number: int


@dataclass(frozen=True, order=True)
class ObjectRef:
    """Object identity in a source namespace (DEC-005)."""

    namespace: str
    id: str


@dataclass(frozen=True)
class Anchor:
    """Candidate deduplication anchor (DEC-006)."""

    kind: str
    objects: tuple[ObjectRef, ...]
    policy_version: str
    rule_id: str


@dataclass(frozen=True)
class EngineDescriptor:
    """Registration metadata consumed by the orchestrator."""

    name: str
    version: str
    unit: str
    required: bool
    needs_model: bool
    needs_reference: bool
    applicability_version: str


@dataclass(frozen=True)
class EngineConfig:
    """Versioned configuration supplied to an engine run."""

    engine: str
    version: str
    enabled: bool
    params: Mapping[str, Any]


@dataclass(frozen=True)
class EngineUnitRef:
    """A frame or shape unit in an engine shard."""

    kind: str
    frame: FrameKey


@dataclass(frozen=True)
class EngineInput:
    """Pure-Python representation of the public ``EngineInput`` schema."""

    idempotency_key: str
    run_id: int
    snapshot_id: int
    engine: str
    engine_version: str
    config: EngineConfig
    seed: int
    shard_index: int
    units: tuple[EngineUnitRef, ...]


@dataclass(frozen=True)
class Candidate:
    """Immutable engine suspicion; it is not a confirmed Issue."""

    engine: str
    engine_version: str
    family: str
    frame: FrameKey
    anchor: Anchor
    evidence: Any


@dataclass(frozen=True)
class EngineUnitResult:
    """Terminal result for one unit in a shard."""

    unit: EngineUnitRef
    outcome: str
    attempts: int


@dataclass(frozen=True)
class EngineOutput:
    """Pure-Python representation of the public ``EngineOutput`` schema."""

    idempotency_key: str
    engine: str
    engine_version: str
    candidates: tuple[Candidate, ...]
    unit_results: tuple[EngineUnitResult, ...]


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


# Đơn vị ngoài phạm vi áp dụng: không vào mẫu số (B-04 "mẫu số áp dụng", DEC-010; PO 2026-10-08).
# Bị loại phải được cảnh báo khi hiển thị (excluded > 0), không im lặng.
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
    """Trạng thái điều phối của engine trong run, schema `EngineInternalState` (không hiển thị)."""

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


# Trạng thái điều phối mà engine đã dừng trong run. EngineInternalState không quyết định trạng thái
# hiển thị: hiển thị luôn tính từ ledger bằng display_status() (DEC-010, review F-2).
TERMINAL_INTERNAL_STATES = frozenset(
    {
        EngineInternalState.SUCCEEDED,
        EngineInternalState.PARTIALLY_SUCCEEDED,
        EngineInternalState.FAILED,
        EngineInternalState.CANCELLED,
        EngineInternalState.DISABLED,
        EngineInternalState.MODEL_UNAVAILABLE,
        EngineInternalState.REFERENCE_UNAVAILABLE,
        EngineInternalState.NOT_APPLICABLE,
    }
)


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
    def excluded_reasons(self) -> dict[NotCheckedReason, int]:
        """Đơn vị bị loại khỏi mẫu số theo lý do, dùng cho cảnh báo hiển thị."""
        return {
            r: n
            for r, n in self.not_checked_reasons.items()
            if r in EXCLUDED_FROM_ELIGIBLE and n > 0
        }

    @property
    def excluded(self) -> int:
        return sum(self.excluded_reasons.values())

    @property
    def needs_exclusion_warning(self) -> bool:
        return self.excluded > 0

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


def display_status(state: EngineInternalState, ledger: LedgerCounts) -> EngineStatus:
    """Trạng thái hiển thị: luôn tính từ ledger; state chỉ cho biết engine đã dừng hay chưa."""
    return public_status(ledger, finished=state in TERMINAL_INTERNAL_STATES)
