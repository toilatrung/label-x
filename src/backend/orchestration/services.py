"""Ghi kết quả shard: candidate, evidence và ledger trong cùng một transaction (FR-AGG-06)."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from django.db import IntegrityError, transaction

from engines.interface import (
    Anchor,
    Candidate,
    EngineConfig,
    EngineInput,
    EngineOutput,
    EngineUnitOutcome,
    EngineUnitRef,
    FrameKey,
    LedgerCounts,
    NotCheckedReason,
)
from orchestration.dedup import dedup_key, sha256_hex, to_jsonable
from orchestration.models import CandidateRecord, LedgerUnit, ShardCommit

logger = logging.getLogger("labelx.orchestration")

_TERMINAL_FROM_ENGINE = {EngineUnitOutcome.COMPLETED.value, EngineUnitOutcome.FAILED.value}


class ShardOutputError(ValueError):
    """Output không khớp input của shard; lỗi cố định, không retry."""


def engine_input_to_payload(engine_input: EngineInput) -> dict[str, Any]:
    payload: dict[str, Any] = to_jsonable(engine_input)
    return payload


def engine_input_from_payload(payload: Mapping[str, Any]) -> EngineInput:
    config = payload["config"]
    return EngineInput(
        idempotency_key=payload["idempotency_key"],
        run_id=payload["run_id"],
        snapshot_id=payload["snapshot_id"],
        engine=payload["engine"],
        engine_version=payload["engine_version"],
        config=EngineConfig(
            engine=config["engine"],
            version=config["version"],
            enabled=config["enabled"],
            params=config["params"],
        ),
        seed=payload["seed"],
        shard_index=payload["shard_index"],
        units=tuple(
            EngineUnitRef(
                kind=u["kind"],
                frame=FrameKey(u["frame"]["cvat_task_id"], u["frame"]["frame_number"]),
            )
            for u in payload["units"]
        ),
    )


def _unit_identity(unit: EngineUnitRef) -> tuple[str, int, int]:
    return (unit.kind, unit.frame.cvat_task_id, unit.frame.frame_number)


def seed_ledger(run_id: int, engine: str, units: Iterable[EngineUnitRef]) -> int:
    """Đưa mọi đơn vị của run vào mẫu số ở trạng thái pending. Idempotent; trả số dòng mới."""
    rows = [
        LedgerUnit(
            run_id=run_id,
            engine=engine,
            kind=u.kind,
            cvat_task_id=u.frame.cvat_task_id,
            frame_number=u.frame.frame_number,
        )
        for u in units
    ]
    before = LedgerUnit.objects.filter(run_id=run_id, engine=engine).count()
    LedgerUnit.objects.bulk_create(rows, ignore_conflicts=True)
    return LedgerUnit.objects.filter(run_id=run_id, engine=engine).count() - before


def ledger_counts(run_id: int, engine: str) -> LedgerCounts:
    rows = LedgerUnit.objects.filter(run_id=run_id, engine=engine).values_list(
        "outcome", "not_checked_reason"
    )
    return LedgerCounts.from_outcomes(
        (EngineUnitOutcome(o), NotCheckedReason(r) if r else None) for o, r in rows
    )


def _validate(engine_input: EngineInput, output: EngineOutput) -> None:
    if output.idempotency_key != engine_input.idempotency_key:
        raise ShardOutputError("idempotency_key của output không khớp input")
    if (output.engine, output.engine_version) != (
        engine_input.engine,
        engine_input.engine_version,
    ):
        raise ShardOutputError("engine/version của output không khớp input")
    expected = Counter(_unit_identity(u) for u in engine_input.units)
    got = Counter(_unit_identity(r.unit) for r in output.unit_results)
    if expected != got or any(n > 1 for n in expected.values()):
        raise ShardOutputError("unit_results phải phủ đúng và duy nhất mọi đơn vị của shard")
    for result in output.unit_results:
        if result.outcome not in _TERMINAL_FROM_ENGINE:
            raise ShardOutputError(f"outcome {result.outcome!r} không hợp lệ cho đơn vị đã xong")
    for candidate in output.candidates:
        if (candidate.engine, candidate.engine_version) != (output.engine, output.engine_version):
            raise ShardOutputError("candidate không thuộc engine của shard")


def _candidate_record(run_id: int, shard: ShardCommit, candidate: Candidate) -> CandidateRecord:
    anchor: Anchor = candidate.anchor
    evidence = to_jsonable(candidate.evidence)
    return CandidateRecord(
        run_id=run_id,
        dedup_key=dedup_key(candidate),
        shard=shard,
        engine=candidate.engine,
        engine_version=candidate.engine_version,
        family=candidate.family,
        cvat_task_id=candidate.frame.cvat_task_id,
        frame_number=candidate.frame.frame_number,
        anchor=to_jsonable(anchor),
        policy_version=anchor.policy_version,
        evidence=evidence,
        evidence_sha256=sha256_hex(evidence),
    )


def commit_shard_output(engine_input: EngineInput, output: EngineOutput) -> bool:
    """Ghi nguyên tử kết quả shard. Trả True nếu commit mới, False nếu đã commit (retry no-op).

    Hoặc toàn bộ (ShardCommit + candidate + ledger) được ghi, hoặc không gì cả: worker chết
    giữa chừng rollback, lần chạy lại ghi đúng một lần.
    """
    _validate(engine_input, output)
    run_id = engine_input.run_id
    if ShardCommit.objects.filter(
        run_id=run_id, idempotency_key=engine_input.idempotency_key
    ).exists():
        return False
    try:
        with transaction.atomic():
            shard = ShardCommit.objects.create(
                idempotency_key=engine_input.idempotency_key,
                run_id=run_id,
                snapshot_id=engine_input.snapshot_id,
                engine=engine_input.engine,
                engine_version=engine_input.engine_version,
                shard_index=engine_input.shard_index,
                output_sha256=sha256_hex(output),
                attempts=max((r.attempts for r in output.unit_results), default=1),
            )
            CandidateRecord.objects.bulk_create(
                [_candidate_record(run_id, shard, c) for c in output.candidates],
                ignore_conflicts=True,
            )
            _apply_unit_results(engine_input, output)
    except IntegrityError:
        # Một worker khác commit cùng khoá/shard trước; transaction của ta đã rollback sạch.
        if ShardCommit.objects.filter(
            run_id=run_id, idempotency_key=engine_input.idempotency_key
        ).exists():
            return False
        raise
    logger.info(
        "shard committed",
        extra={
            "run_id": run_id,
            "engine": engine_input.engine,
            "shard_index": engine_input.shard_index,
            "candidates": len(output.candidates),
        },
    )
    return True


def _apply_unit_results(engine_input: EngineInput, output: EngineOutput) -> None:
    ledger = LedgerUnit.objects.select_for_update().filter(
        run_id=engine_input.run_id, engine=engine_input.engine
    )
    by_identity = {(u.kind, u.cvat_task_id, u.frame_number): u for u in ledger}
    for result in output.unit_results:
        row = by_identity.get(_unit_identity(result.unit))
        if row is None:
            raise ShardOutputError("đơn vị không có trong ledger của run (chưa seed)")
        if row.outcome == EngineUnitOutcome.COMPLETED.value:
            continue  # completed không bị ghi đè: giữ tổng và coverage ổn định
        row.outcome = result.outcome
        row.attempts = max(row.attempts, result.attempts)
        row.save(update_fields=["outcome", "attempts"])


def mark_shard_failed(engine_input: EngineInput, attempts: int) -> None:
    """Hết retry: đơn vị chưa xong thành failed, vẫn nằm trong mẫu số. Không tạo ShardCommit,
    nên retry-failed (T-024) vẫn chạy lại được cùng idempotency_key."""
    with transaction.atomic():
        for row in LedgerUnit.objects.select_for_update().filter(
            run_id=engine_input.run_id,
            engine=engine_input.engine,
            outcome__in=["pending", "running", "retrying"],
        ):
            if (row.kind, row.cvat_task_id, row.frame_number) in {
                _unit_identity(u) for u in engine_input.units
            }:
                row.outcome = EngineUnitOutcome.FAILED.value
                row.attempts = max(row.attempts, attempts)
                row.save(update_fields=["outcome", "attempts"])


def run_metrics(run_id: int) -> dict[str, Any]:
    """Số liệu shard/candidate/ledger cho dashboard queue (metric queue/shard)."""
    shards = ShardCommit.objects.filter(run_id=run_id)
    engines = sorted(set(LedgerUnit.objects.filter(run_id=run_id).values_list("engine", flat=True)))
    return {
        "run_id": run_id,
        "shards_committed": shards.count(),
        "candidates": CandidateRecord.objects.filter(run_id=run_id).count(),
        "ledger": {
            e: {
                "total": (c := ledger_counts(run_id, e)).total,
                "completed": c.completed,
                "failed": c.failed,
                "pending": c.pending,
            }
            for e in engines
        },
    }
