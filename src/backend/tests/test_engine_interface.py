"""Engine interface (T-006, DEC-010): schema trong docs/04-api/openapi.yaml và quy tắc tham chiếu.

- Mọi trường của schema engine interface trích mã FR/BR/UC/NFR có trong SRS.
- Map trạng thái: không trạng thái nội bộ chưa hoàn tất nào thành `checked` (FR-AGG-05).
- Ledger: đơn vị failed không bị loại khỏi mẫu số (FR-AGG-04).
"""

from __future__ import annotations

import itertools
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from engines.interface import (
    TERMINAL_INTERNAL_STATES,
    UNIT_PUBLIC_STATUS,
    EngineInternalState,
    EngineStatus,
    EngineUnitOutcome,
    LedgerCounts,
    NotCheckedReason,
    display_status,
    public_status,
)

ROOT = Path(__file__).resolve().parents[3]
SPEC = yaml.safe_load((ROOT / "docs/04-api/openapi.yaml").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]
SRS_TEXT = "\n".join(
    p.read_text(encoding="utf-8")
    for p in (ROOT / "docs/label-x_system-requirement-specification/sections").glob("*.tex")
)
TRACE_ID = re.compile(r"^(FR-[A-Z]{3}-\d{2}|BR-\d{2}|UC-\d{2}|NFR-\d{2})$")

# Schema object của interface: mỗi property phải có trace trong x-labelx-trace.
OBJECT_SCHEMAS = [
    "LedgerEntry",
    "EngineDescriptor",
    "EngineConfig",
    "EngineUnitRef",
    "EngineInput",
    "Candidate",
    "EngineUnitResult",
    "EngineOutput",
]

R = NotCheckedReason


def _codes_exist(codes: list[str], where: str) -> None:
    assert codes, f"{where}: thiếu trace"
    for code in codes:
        assert TRACE_ID.match(code), f"{where}: mã {code} sai định dạng"
        assert re.search(rf"\\req\{{{code}\}}|\b{code}\b", SRS_TEXT), (
            f"{where}: {code} không có trong SRS"
        )


# ------------------------------------------------------------------ contract


@pytest.mark.parametrize("name", OBJECT_SCHEMAS)
def test_every_field_traces_to_srs(name: str) -> None:
    schema = SCHEMAS[name]
    trace: dict[str, list[str]] = schema["x-labelx-trace"]
    assert set(trace) == set(schema["properties"]), f"{name}: trace phải phủ đúng mọi trường"
    for prop, codes in trace.items():
        _codes_exist(codes, f"{name}.{prop}")


def test_unit_outcome_enum_traces_and_maps_every_value() -> None:
    schema = SCHEMAS["EngineUnitOutcome"]
    _codes_exist(schema["x-labelx-trace"], "EngineUnitOutcome")
    mapping: dict[str, str] = schema["x-labelx-public-status"]
    assert set(mapping) == set(schema["enum"])
    assert set(mapping.values()) <= set(SCHEMAS["EngineStatus"]["enum"])


def test_internal_state_has_no_direct_public_map() -> None:
    """EngineInternalState chỉ điều phối; trạng thái hiển thị luôn từ ledger (review F-2)."""
    schema = SCHEMAS["EngineInternalState"]
    _codes_exist(schema["x-labelx-trace"], "EngineInternalState")
    assert "x-labelx-public-status" not in schema
    assert set(schema["x-labelx-terminal"]) <= set(schema["enum"])


def test_python_enums_match_contract() -> None:
    assert [s.value for s in EngineStatus] == SCHEMAS["EngineStatus"]["enum"]
    assert [r.value for r in NotCheckedReason] == SCHEMAS["NotCheckedReason"]["enum"]
    assert [o.value for o in EngineUnitOutcome] == SCHEMAS["EngineUnitOutcome"]["enum"]
    assert [s.value for s in EngineInternalState] == SCHEMAS["EngineInternalState"]["enum"]
    assert {k.value: v.value for k, v in UNIT_PUBLIC_STATUS.items()} == SCHEMAS[
        "EngineUnitOutcome"
    ]["x-labelx-public-status"]
    assert {s.value for s in TERMINAL_INTERNAL_STATES} == set(
        SCHEMAS["EngineInternalState"]["x-labelx-terminal"]
    )


def test_ledger_entry_requires_denominator_fields() -> None:
    required = set(SCHEMAS["LedgerEntry"]["required"])
    assert {
        "total",
        "eligible",
        "completed",
        "failed",
        "pending",
        "not_checked",
        "coverage",
    } <= required


# --------------------------------------------------------------- status map


def test_only_completed_unit_maps_to_checked() -> None:
    checked = {o for o, s in UNIT_PUBLIC_STATUS.items() if s is EngineStatus.CHECKED}
    assert checked == {EngineUnitOutcome.COMPLETED}


def test_unit_map_equals_single_unit_ledger() -> None:
    """Bảng map từng đơn vị trùng quy tắc ledger: không có nguồn trạng thái thứ hai."""
    for outcome, expected in UNIT_PUBLIC_STATUS.items():
        reasons = list(NotCheckedReason) if outcome is EngineUnitOutcome.NOT_CHECKED else [None]
        for reason in reasons:
            ledger = LedgerCounts.from_outcomes([(outcome, reason)])
            finished = outcome not in {
                EngineUnitOutcome.PENDING,
                EngineUnitOutcome.RUNNING,
                EngineUnitOutcome.RETRYING,
            }
            assert public_status(ledger, finished=finished) is expected, (outcome, reason)


def test_display_status_always_from_ledger() -> None:
    """Hiển thị luôn bằng public_status(ledger); chưa dừng mà còn pending thì running."""
    for state in EngineInternalState:
        finished = state in TERMINAL_INTERNAL_STATES
        for ledger in _all_ledgers():
            status = display_status(state, ledger)
            assert status is public_status(ledger, finished=finished)
            if not finished and ledger.pending:
                assert status is EngineStatus.RUNNING
            if status is EngineStatus.CHECKED:
                assert ledger.completed == ledger.eligible > 0


def test_display_examples_resolve_former_conflicts() -> None:
    blocked = LedgerCounts(completed=4, not_checked_reasons={R.NO_MODEL: 1})
    assert display_status(EngineInternalState.SUCCEEDED, blocked) is EngineStatus.PARTIAL
    done = LedgerCounts(completed=5)
    assert display_status(EngineInternalState.CANCELLED, done) is EngineStatus.CHECKED
    assert (
        display_status(EngineInternalState.QUEUED, LedgerCounts(pending=5)) is EngineStatus.RUNNING
    )


def _all_ledgers(limit: int = 2) -> Any:
    reasons = list(NotCheckedReason)
    for completed, failed, pending in itertools.product(range(limit + 1), repeat=3):
        for counts in itertools.product(range(2), repeat=len(reasons)):
            yield LedgerCounts(completed, failed, pending, dict(zip(reasons, counts, strict=True)))


def test_checked_only_when_every_eligible_unit_completed() -> None:
    """Duyệt mọi ledger nhỏ: `checked` ⇔ engine đã dừng, eligible > 0 và completed = eligible."""
    for ledger in _all_ledgers():
        for finished in (True, False):
            status = public_status(ledger, finished=finished)
            expected = (
                ledger.eligible > 0
                and ledger.completed == ledger.eligible
                and (finished or ledger.pending == 0)
            )
            assert (status is EngineStatus.CHECKED) == expected, (ledger, finished, status)
            if status is EngineStatus.CHECKED:
                assert ledger.failed == ledger.pending == ledger.blocked == 0


def test_status_examples() -> None:
    assert public_status(LedgerCounts(pending=3), finished=False) is EngineStatus.RUNNING
    assert (
        public_status(LedgerCounts(completed=2, pending=1), finished=False) is EngineStatus.RUNNING
    )
    assert (
        public_status(LedgerCounts(completed=2, pending=1), finished=True) is EngineStatus.PARTIAL
    )
    assert public_status(LedgerCounts(completed=2, failed=1), finished=True) is EngineStatus.PARTIAL
    assert public_status(LedgerCounts(failed=3), finished=True) is EngineStatus.FAILED
    assert (
        public_status(LedgerCounts(not_checked_reasons={R.NO_MODEL: 5}), finished=True)
        is EngineStatus.NOT_CHECKED
    )
    assert (
        public_status(LedgerCounts(not_checked_reasons={R.NOT_APPLICABLE: 5}), finished=True)
        is EngineStatus.NOT_CHECKED
    )
    assert (
        public_status(
            LedgerCounts(completed=4, not_checked_reasons={R.NOT_APPLICABLE: 2}), finished=True
        )
        is EngineStatus.CHECKED
    )
    assert (
        public_status(LedgerCounts(completed=4, not_checked_reasons={R.DISABLED: 1}), finished=True)
        is EngineStatus.PARTIAL
    )


# -------------------------------------------------------------------- ledger


def test_failed_unit_stays_in_denominator() -> None:
    ok = LedgerCounts(completed=10)
    with_failure = LedgerCounts(completed=9, failed=1)
    assert with_failure.eligible == ok.eligible == 10
    assert with_failure.coverage == pytest.approx(0.9)


def test_denominator_never_shrinks_when_units_fail() -> None:
    for ledger in _all_ledgers():
        for target in ("completed", "pending"):
            if getattr(ledger, target) == 0:
                continue
            moved = LedgerCounts(
                completed=ledger.completed - (target == "completed"),
                failed=ledger.failed + 1,
                pending=ledger.pending - (target == "pending"),
                not_checked_reasons=ledger.not_checked_reasons,
            )
            assert moved.eligible == ledger.eligible
            assert moved.total == ledger.total


def test_blocking_not_checked_stays_in_denominator_but_out_of_scope_does_not() -> None:
    blocked = LedgerCounts(completed=8, not_checked_reasons={R.NO_MODEL: 2})
    out_of_scope = LedgerCounts(
        completed=8, not_checked_reasons={R.NOT_APPLICABLE: 1, R.NOT_TRIGGERED: 1}
    )
    assert blocked.eligible == 10 and blocked.coverage == pytest.approx(0.8)
    assert out_of_scope.eligible == 8 and out_of_scope.coverage == 1.0


def test_ledger_invariants() -> None:
    for ledger in _all_ledgers():
        assert (
            ledger.total == ledger.completed + ledger.failed + ledger.pending + ledger.not_checked
        )
        assert ledger.eligible == ledger.completed + ledger.failed + ledger.pending + ledger.blocked
        assert ledger.coverage is None or 0 <= ledger.coverage <= 1
        assert (ledger.coverage is None) == (ledger.eligible == 0)


def test_from_outcomes_counts_and_requires_reason() -> None:
    U = EngineUnitOutcome
    ledger = LedgerCounts.from_outcomes(
        [
            (U.COMPLETED, None),
            (U.FAILED, None),
            (U.RETRYING, None),
            (U.PENDING, None),
            (U.NOT_CHECKED, R.NOT_APPLICABLE),
            (U.NOT_CHECKED, R.NO_MODEL),
        ]
    )
    assert (ledger.completed, ledger.failed, ledger.pending, ledger.not_checked) == (1, 1, 2, 2)
    assert (ledger.total, ledger.eligible, ledger.blocked) == (6, 5, 1)
    with pytest.raises(ValueError, match="lý do"):
        LedgerCounts.from_outcomes([(U.NOT_CHECKED, None)])
    with pytest.raises(ValueError):
        LedgerCounts.from_outcomes([(U.FAILED, R.DISABLED)])
    with pytest.raises(ValueError, match="âm"):
        LedgerCounts(completed=-1)


def test_excluded_units_still_checked_but_warned() -> None:
    """PO 2026-10-08 (DEC-010): loại khỏi mẫu số nhưng phải cảnh báo; trạng thái vẫn checked."""
    ledger = LedgerCounts(
        completed=900, not_checked_reasons={R.NOT_APPLICABLE: 100, R.NOT_TRIGGERED: 0}
    )
    assert public_status(ledger, finished=True) is EngineStatus.CHECKED
    assert ledger.coverage == 1.0
    assert (ledger.total, ledger.eligible, ledger.excluded) == (1000, 900, 100)
    assert ledger.needs_exclusion_warning
    assert ledger.excluded_reasons == {R.NOT_APPLICABLE: 100}
    assert not LedgerCounts(completed=5).needs_exclusion_warning
    blocked = LedgerCounts(completed=5, not_checked_reasons={R.NO_MODEL: 1})
    assert blocked.excluded == 0 and blocked.excluded_reasons == {}
