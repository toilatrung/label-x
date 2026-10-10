"""Tích hợp orchestrator với QCRun/WorkUnit của T-024."""

from __future__ import annotations

import pytest
from django.utils import timezone

from engines.interface import EngineInput, EngineOutput, EngineUnitResult
from orchestration.dispatch import build_engine_input, dispatch_run, run_work_unit
from orchestration.models import CandidateRecord, ShardCommit
from orchestration.registry import registry
from orchestration.services import ledger_counts
from runs.models import QCRun, RunRanking, WorkUnit
from runs.services import create_qc_run, retry_failed_qc_run
from tests.orchestration.helpers import make_run

pytestmark = pytest.mark.django_db(transaction=True)

ENGINE = "duplicate_overlap"


@pytest.fixture
def run_setup(db: None):
    return make_run(engine=ENGINE)


@pytest.fixture
def fake_engine(monkeypatch):
    calls: list[int] = []

    def runner(inp: EngineInput) -> EngineOutput:
        calls.append(inp.shard_index)
        return EngineOutput(
            inp.idempotency_key,
            inp.engine,
            inp.engine_version,
            (),
            tuple(EngineUnitResult(u, "completed", 1) for u in inp.units),
        )

    monkeypatch.setattr(registry, "runner", lambda name, version: runner)
    return calls


def test_engine_input_units_follow_shard_key(run_setup: QCRun):
    sizes = sorted(len(build_engine_input(u).units) for u in run_setup.work_units.all())
    assert sizes == [1, 2]


def test_run_work_units_commit_and_are_idempotent(run_setup: QCRun, fake_engine):
    for unit in run_setup.work_units.all():
        run_work_unit.apply(args=[unit.pk]).get()
    assert set(run_setup.work_units.values_list("status", flat=True)) == {"completed"}
    assert ShardCommit.objects.filter(run_id=run_setup.pk).count() == 2
    counts = ledger_counts(run_setup.pk, ENGINE)
    assert (counts.total, counts.completed, counts.pending) == (3, 3, 0)
    # chạy lại: unit đã completed -> không gọi engine, không đổi dữ liệu
    called = len(fake_engine)
    for unit in run_setup.work_units.all():
        run_work_unit.apply(args=[unit.pk]).get()
    assert len(fake_engine) == called
    assert CandidateRecord.objects.count() == 0


def test_failed_unit_retried_after_retry_failed_keeps_ledger_total(run_setup: QCRun, monkeypatch):
    def boom(name: str, version: str):
        raise LookupError("engine chưa đăng ký")

    monkeypatch.setattr(registry, "runner", boom)
    unit = run_setup.work_units.order_by("shard_index").first()
    with pytest.raises(LookupError):
        run_work_unit.apply(args=[unit.pk]).get()
    unit.refresh_from_db()
    assert unit.status == WorkUnit.Status.FAILED and "chưa đăng ký" in unit.last_error
    counts = ledger_counts(run_setup.pk, ENGINE)
    assert counts.failed == len(build_engine_input(unit).units)
    assert counts.total == counts.eligible


def test_cancelled_run_skips_units(run_setup: QCRun, fake_engine):
    QCRun.objects.filter(pk=run_setup.pk).update(cancel_requested_at=timezone.now())
    unit = run_setup.work_units.first()
    run_work_unit.apply(args=[unit.pk]).get()
    assert fake_engine == []


def test_two_runs_same_input_commit_independently(run_setup: QCRun, fake_engine):
    other, _ = create_qc_run(
        snapshot_id=run_setup.snapshot_id,
        config_version_id=run_setup.config_version_id,
        seed=2,
        created_by=run_setup.created_by,
    )
    for run in (run_setup, other):
        for unit in run.work_units.all():
            run_work_unit.apply(args=[unit.pk]).get()
    assert ShardCommit.objects.count() == 4
    assert dispatch_run(run_setup.pk) == 0  # không còn unit pending


@pytest.fixture
def inline_queue(monkeypatch):
    """Thay Celery broker bằng chạy tại chỗ; ghi lại thứ tự xếp hàng."""
    queued: list[int] = []

    def delay(pk: int):
        queued.append(pk)
        run_work_unit.apply(args=(pk,))

    monkeypatch.setattr(run_work_unit, "delay", delay)
    return queued


def test_run_completes_and_engine_result_follows_ledger(
    run_setup: QCRun, fake_engine, inline_queue
):
    assert dispatch_run(run_setup.pk) == 2
    run = QCRun.objects.get(pk=run_setup.pk)
    assert run.status == QCRun.Status.COMPLETED and run.finished_at is not None
    result = run.engine_results.get(engine=ENGINE)
    assert (result.eligible_units, result.completed_units, result.failed_units) == (3, 3, 0)
    assert result.status == "checked"
    assert RunRanking.objects.filter(run=run).count() == len(RunRanking.Source.values)


def test_partial_run_then_retry_failed_completes(run_setup: QCRun, monkeypatch, inline_queue):
    state = {"fail": True}

    def runner(inp: EngineInput) -> EngineOutput:
        if inp.shard_index == 0 and state["fail"]:
            raise ValueError("lỗi cố định")
        return EngineOutput(
            inp.idempotency_key,
            inp.engine,
            inp.engine_version,
            (),
            tuple(EngineUnitResult(u, "completed", 1) for u in inp.units),
        )

    monkeypatch.setattr(registry, "runner", lambda name, version: runner)
    dispatch_run(run_setup.pk)
    run = QCRun.objects.get(pk=run_setup.pk)
    assert run.status == QCRun.Status.PARTIAL
    result = run.engine_results.get(engine=ENGINE)
    assert result.failed_units > 0 and result.status == "partial"
    total = result.eligible_units

    state["fail"] = False
    retry_failed_qc_run(run_id=run.pk, actor=run.created_by)
    dispatch_run(run.pk)
    run.refresh_from_db()
    result = run.engine_results.get(engine=ENGINE)
    assert run.status == QCRun.Status.COMPLETED
    assert (result.eligible_units, result.completed_units, result.failed_units) == (total, total, 0)


def test_create_run_auto_dispatches_after_commit(settings, monkeypatch):
    settings.ORCHESTRATION_AUTO_DISPATCH = True
    seen: list[int] = []
    monkeypatch.setattr(run_work_unit, "delay", seen.append)
    run = make_run(engine=ENGINE)
    assert sorted(seen) == sorted(run.work_units.values_list("pk", flat=True))


def test_duplicate_engine_registered_and_runs_on_snapshot(inline_queue):
    shapes = [
        {"id": i, "type": "rectangle", "frame": 0, "label_id": 4, "points": [0, 0, 10, 10]}
        for i in (1, 2)
    ]
    run = make_run(engine="duplicate", shapes=shapes)
    dispatch_run(run.pk)
    run.refresh_from_db()
    assert run.status == QCRun.Status.COMPLETED
    candidates = CandidateRecord.objects.filter(run_id=run.pk)
    assert candidates.count() == 1 and candidates.get().family


def test_engine_result_reason_from_ledger_not_checked(run_setup: QCRun, inline_queue):
    # Ledger not_checked do engine ghi (T-027): kiểm refresh_run gán lý do vào EngineResult.
    from orchestration.models import LedgerUnit
    from orchestration.runsync import refresh_run

    dispatch_run(run_setup.pk)  # seed ledger, chạy fake_engine không đăng ký -> failed
    LedgerUnit.objects.filter(run_id=run_setup.pk, engine=ENGINE).update(
        outcome="not_checked", not_checked_reason="no_reference"
    )
    refresh_run(run_setup.pk)
    result = run_setup.engine_results.get(engine=ENGINE)
    assert result.status == "not_checked" and result.reason == "no_reference"


def test_default_run_with_all_registered_engines_end_to_end(inline_queue):
    """Run mặc định: duplicate + schema + geometry chạy thật qua registry."""
    from orchestration.models import LedgerUnit
    from runs.models import ConfigVersion
    from runs.services import create_qc_run

    base = make_run(engine="duplicate")
    cfg = ConfigVersion.objects.get(pk=base.config_version_id)
    cfg.engines = {}
    cfg.payload = {"shard_size": 2}
    cfg.save()
    run, _ = create_qc_run(
        snapshot_id=base.snapshot_id, config_version_id=cfg.pk, seed=9, created_by=base.created_by
    )
    dispatch_run(run.pk)
    run.refresh_from_db()
    results = {r.engine: r for r in run.engine_results.all()}
    assert run.status == QCRun.Status.COMPLETED
    # Frame không có annotation: duplicate và geometry đều not_applicable (không coi là đã kiểm).
    expected = {
        "schema": "no_reference",
        "geometry": "not_applicable",
        "duplicate": "not_applicable",
    }
    for name, reason in expected.items():
        reasons = set(
            LedgerUnit.objects.filter(run_id=run.pk, engine=name).values_list(
                "not_checked_reason", flat=True
            )
        )
        assert reasons == {reason}, (name, reasons)
        assert results[name].status == "not_checked" and results[name].reason == reason
    # Schema thiếu taxonomy vẫn nằm trong mẫu số (không bị loại như not_applicable).
    assert results["schema"].eligible_units == 3
    assert results["geometry"].eligible_units == 0
    assert results["duplicate"].eligible_units == 0
