"""R-1/R-2: tranh chấp thật trên PostgreSQL (nhiều thread = nhiều connection).

- R-1: một owner duy nhất chạy shard (lease); delivery trùng bị bỏ qua; worker cũ sau khi bị thu hồi
  không được chốt FAILED/COMPLETED đè lên owner mới.
- R-2: claim và cancel khoá QCRun -> WorkUnit cùng thứ tự, không deadlock.
"""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from django.db import OperationalError, connections
from django.utils import timezone

from engines.interface import EngineInput, EngineOutput, EngineUnitResult
from orchestration.dispatch import run_work_unit
from orchestration.models import LedgerUnit, ShardCommit
from orchestration.registry import registry
from runs.models import QCRun, WorkUnit
from runs.services import cancel_qc_run
from tests.orchestration.helpers import make_run

pytestmark = pytest.mark.django_db(transaction=True)

ENGINE = "duplicate_overlap"


def ok(inp: EngineInput) -> EngineOutput:
    return EngineOutput(
        inp.idempotency_key,
        inp.engine,
        inp.engine_version,
        (),
        tuple(EngineUnitResult(u, "completed", 1) for u in inp.units),
    )


class Gate:
    """Runner chịu điều khiển theo tên thread: đánh dấu đã vào, chờ tín hiệu, rồi ok hoặc lỗi."""

    def __init__(self) -> None:
        self.entered: dict[str, threading.Event] = {}
        self.release: dict[str, threading.Event] = {}
        self.fail: dict[str, Exception] = {}
        self.calls: list[str] = []

    def thread(self, name: str) -> None:
        self.entered[name] = threading.Event()
        self.release[name] = threading.Event()

    def __call__(self, inp: EngineInput) -> EngineOutput:
        name = threading.current_thread().name
        self.calls.append(name)
        if name in self.entered:
            self.entered[name].set()
            assert self.release[name].wait(30), f"{name} không được thả"
        if name in self.fail:
            raise self.fail[name]
        return ok(inp)


def _spawn(name: str, fn, results: dict) -> threading.Thread:
    def target() -> None:
        try:
            results[name] = fn()
        except BaseException as exc:  # noqa: BLE001 - thu mọi lỗi để assert ở thread chính
            results[name] = exc
        finally:
            connections.close_all()

    thread = threading.Thread(target=target, name=name)
    thread.start()
    return thread


@pytest.fixture
def gate(monkeypatch) -> Gate:
    g = Gate()
    monkeypatch.setattr(registry, "runner", lambda name, version: g)
    return g


def _unit(run: QCRun) -> WorkUnit:
    return run.work_units.order_by("shard_index").first()


def _age_lease(unit: WorkUnit) -> None:
    WorkUnit.objects.filter(pk=unit.pk).update(started_at=timezone.now() - timedelta(hours=2))


def test_duplicate_delivery_while_owner_running_is_skipped_and_engine_runs_once(gate):
    run = make_run(engine=ENGINE)
    unit = _unit(run)
    gate.thread("owner")
    results: dict = {}
    owner = _spawn("owner", lambda: run_work_unit.run(unit.pk), results)
    assert gate.entered["owner"].wait(30)
    assert run_work_unit.run(unit.pk) == "running"  # delivery trùng: không chạy song song
    assert gate.calls == ["owner"]
    gate.release["owner"].set()
    owner.join(30)
    assert results["owner"] == WorkUnit.Status.COMPLETED
    assert gate.calls == ["owner"]  # engine chỉ chạy một lần
    assert ShardCommit.objects.filter(run_id=run.pk).count() == 1


def test_stale_owner_failure_cannot_fail_unit_reclaimed_and_completed_by_new_owner(gate):
    """Tái hiện R-1: A lỗi cố định sau khi B đã nhận lại; unit/run không được thành FAILED."""
    run = make_run(engine=ENGINE)
    unit = _unit(run)
    gate.thread("A")
    gate.fail["A"] = ValueError("lỗi cố định của worker cũ")
    results: dict = {}
    a = _spawn("A", lambda: run_work_unit.run(unit.pk), results)
    assert gate.entered["A"].wait(30)
    _age_lease(unit)  # worker A bị coi là chết/bỏ rơi; B nhận lại
    b_result = _spawn("B", lambda: run_work_unit.run(unit.pk), results)
    b_result.join(30)
    assert results["B"] == WorkUnit.Status.COMPLETED
    gate.release["A"].set()  # A tỉnh dậy, lỗi cố định SAU khi B đã xong
    a.join(30)
    assert isinstance(results["A"], ValueError)
    unit.refresh_from_db()
    other_ids = list(
        WorkUnit.objects.filter(run=run).exclude(pk=unit.pk).values_list("pk", flat=True)
    )
    assert unit.status == WorkUnit.Status.COMPLETED  # không bị A ghi FAILED
    assert (
        ShardCommit.objects.filter(run_id=run.pk, idempotency_key=unit.idempotency_key).count() == 1
    )
    assert not LedgerUnit.objects.filter(run_id=run.pk, outcome="failed").exists()
    for pk in other_ids:  # shard còn lại chạy bình thường -> run COMPLETED, không FAILED/PARTIAL
        gate.calls.clear()
        assert run_work_unit.run(pk) == WorkUnit.Status.COMPLETED
    assert QCRun.objects.get(pk=run.pk).status == QCRun.Status.COMPLETED


def test_stale_owner_failure_while_new_owner_is_still_running_is_ignored(gate):
    run = make_run(engine=ENGINE)
    unit = _unit(run)
    gate.thread("A")
    gate.thread("B")
    gate.fail["A"] = ValueError("lỗi cố định của worker cũ")
    results: dict = {}
    a = _spawn("A", lambda: run_work_unit.run(unit.pk), results)
    assert gate.entered["A"].wait(30)
    _age_lease(unit)
    b = _spawn("B", lambda: run_work_unit.run(unit.pk), results)
    assert gate.entered["B"].wait(30)  # B là owner hiện tại, đang chạy
    gate.release["A"].set()  # A lỗi cố định khi B còn chạy
    a.join(30)
    assert isinstance(results["A"], ValueError)
    unit.refresh_from_db()
    assert unit.status == WorkUnit.Status.RUNNING  # A không chốt được: không còn là chủ lease
    assert not LedgerUnit.objects.filter(run_id=run.pk, outcome="failed").exists()
    gate.release["B"].set()
    b.join(30)
    assert results["B"] == WorkUnit.Status.COMPLETED
    unit.refresh_from_db()
    assert unit.status == WorkUnit.Status.COMPLETED


@pytest.mark.parametrize("round_no", range(12))
def test_claim_and_cancel_do_not_deadlock(gate, round_no):
    """Tái hiện R-2: claim (WorkUnit -> QCRun) đảo thứ tự với cancel (QCRun -> WorkUnit)."""
    run = make_run(engine=ENGINE)
    unit = _unit(run)
    actor = run.created_by
    barrier = threading.Barrier(2)
    results: dict = {}

    def claim():
        barrier.wait(10)
        return run_work_unit.run(unit.pk)

    def cancel():
        barrier.wait(10)
        return cancel_qc_run(run_id=run.pk, actor=actor)

    threads = [_spawn("claim", claim, results), _spawn("cancel", cancel, results)]
    for t in threads:
        t.join(60)
    assert not any(t.is_alive() for t in threads)
    for name, value in results.items():
        assert not isinstance(value, OperationalError), f"{name}: {value!r}"
    final = QCRun.objects.get(pk=run.pk)
    assert final.status == QCRun.Status.CANCELLED  # huỷ luôn thắng, nhất quán dù claim đến trước
    assert WorkUnit.objects.get(pk=unit.pk).status in (
        WorkUnit.Status.CANCELLED,
        WorkUnit.Status.COMPLETED,
    )


def _set_retry_ticket(unit: WorkUnit, ticket: str) -> None:
    """Trạng thái sau khi owner lên lịch retry: RUNNING + token = vé retry dùng một lần."""
    WorkUnit.objects.filter(pk=unit.pk).update(
        status=WorkUnit.Status.RUNNING, lease_token=ticket, started_at=timezone.now()
    )


def test_two_copies_of_same_retry_ticket_run_the_engine_once(gate):
    """RV2-1: bản sao thứ hai của cùng một retry không được chạy cùng lúc với bản đầu."""
    run = make_run(engine=ENGINE)
    unit = _unit(run)
    _set_retry_ticket(unit, "ticket-1")
    gate.thread("copy1")
    gate.fail["copy1"] = ValueError("lỗi cố định của lần thử")
    results: dict = {}
    first = _spawn("copy1", lambda: run_work_unit.run(unit.pk, lease_token="ticket-1"), results)
    assert gate.entered["copy1"].wait(30)  # bản 1 đã nhận retry (token đã đổi)
    assert run_work_unit.run(unit.pk, lease_token="ticket-1") == "running"  # bản sao: bị bỏ qua
    assert gate.calls == ["copy1"]
    gate.release["copy1"].set()
    first.join(30)
    assert isinstance(results["copy1"], ValueError)
    assert WorkUnit.objects.get(pk=unit.pk).status == WorkUnit.Status.FAILED  # chỉ một owner chốt
    assert ShardCommit.objects.filter(run_id=run.pk).count() == 0


def test_two_copies_of_same_retry_ticket_interleaved_success_and_failure(gate):
    """Bản 1 lỗi rồi bản sao thành công: bản sao không được chạy nên không có commit lẻ."""
    run = make_run(engine=ENGINE)
    unit = _unit(run)
    _set_retry_ticket(unit, "ticket-2")
    gate.thread("copy1")
    results: dict = {}
    first = _spawn("copy1", lambda: run_work_unit.run(unit.pk, lease_token="ticket-2"), results)
    assert gate.entered["copy1"].wait(30)
    second = _spawn("copy2", lambda: run_work_unit.run(unit.pk, lease_token="ticket-2"), results)
    second.join(30)
    assert results["copy2"] == "running"
    gate.release["copy1"].set()
    first.join(30)
    assert results["copy1"] == WorkUnit.Status.COMPLETED
    assert gate.calls == ["copy1"]
    assert ShardCommit.objects.filter(run_id=run.pk).count() == 1


def test_stale_worker_success_after_new_owner_failed_cannot_commit(gate):
    """RV2-2: A hết lease, B nhận lại và FAILED; A trả output thành công nhưng không ghi được."""
    run = make_run(engine=ENGINE)
    unit = _unit(run)
    gate.thread("A")
    gate.fail["B"] = ValueError("owner mới lỗi cố định")
    results: dict = {}
    a = _spawn("A", lambda: run_work_unit.run(unit.pk), results)
    assert gate.entered["A"].wait(30)
    _age_lease(unit)
    b = _spawn("B", lambda: run_work_unit.run(unit.pk), results)
    b.join(30)
    assert isinstance(results["B"], ValueError)
    assert WorkUnit.objects.get(pk=unit.pk).status == WorkUnit.Status.FAILED
    gate.release["A"].set()  # A trả output thành công SAU khi B chốt FAILED
    a.join(30)
    assert results["A"] == "stale"
    assert WorkUnit.objects.get(pk=unit.pk).status == WorkUnit.Status.FAILED  # A không đảo ngược
    assert ShardCommit.objects.filter(run_id=run.pk).count() == 0
    assert not LedgerUnit.objects.filter(run_id=run.pk, outcome="completed").exists()


def test_stale_worker_output_cannot_overwrite_current_owner_output(gate):
    """Hai output khác nội dung: chỉ output của owner hiện hành được lưu (hash + attempts)."""
    run = make_run(engine=ENGINE)
    unit = _unit(run)
    stale_marker = 7

    def runner(inp: EngineInput) -> EngineOutput:
        name = threading.current_thread().name
        if name == "A":
            gate.entered["A"].set()
            assert gate.release["A"].wait(30)
            attempts = stale_marker
        else:
            attempts = 1
        return EngineOutput(
            inp.idempotency_key,
            inp.engine,
            inp.engine_version,
            (),
            tuple(EngineUnitResult(u, "completed", attempts) for u in inp.units),
        )

    registry_runner = registry.runner
    registry.runner = lambda name, version: runner  # type: ignore[method-assign]
    try:
        gate.thread("A")
        results: dict = {}
        a = _spawn("A", lambda: run_work_unit.run(unit.pk), results)
        assert gate.entered["A"].wait(30)
        _age_lease(unit)
        b = _spawn("B", lambda: run_work_unit.run(unit.pk), results)
        b.join(30)
        assert results["B"] == WorkUnit.Status.COMPLETED
        gate.release["A"].set()
        a.join(30)
    finally:
        registry.runner = registry_runner  # type: ignore[method-assign]
    assert results["A"] in ("stale", WorkUnit.Status.COMPLETED)
    commit = ShardCommit.objects.get(run_id=run.pk, idempotency_key=unit.idempotency_key)
    assert commit.attempts == 1  # output của owner hiện hành (B), không phải của A (attempts=7)
    assert not LedgerUnit.objects.filter(run_id=run.pk, attempts=stale_marker).exists()
