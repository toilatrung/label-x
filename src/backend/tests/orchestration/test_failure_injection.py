"""Failure injection: retry, worker chết, broker lỗi, huỷ, dispatch lặp, shard rỗng/sai engine."""

from __future__ import annotations

from io import StringIO
from unittest import mock

import pytest
from celery.exceptions import Retry
from django.core.management import call_command

from config.celery import app as celery_app
from engines.interface import EngineInput, EngineOutput, EngineUnitResult
from orchestration import dispatch as dispatch_module
from orchestration.dispatch import dispatch_run, redispatch_pending, run_work_unit
from orchestration.models import CandidateRecord, LedgerUnit, ShardCommit
from orchestration.registry import registry
from orchestration.services import ledger_counts
from runs.models import QCRun, RunRanking, WorkUnit
from runs.services import cancel_qc_run, create_qc_run
from tests.orchestration.helpers import make_run

pytestmark = pytest.mark.django_db(transaction=True)

ENGINE = "duplicate_overlap"
SHAPES = [
    {"id": i, "type": "rectangle", "frame": 0, "label_id": 4, "points": [0, 0, 10, 10]}
    for i in (1, 2)
]


class WorkerKilled(BaseException):
    """Mô phỏng SIGKILL: không bị `except Exception` bắt, như worker chết thật."""


def ok_output(inp: EngineInput) -> EngineOutput:
    return EngineOutput(
        inp.idempotency_key,
        inp.engine,
        inp.engine_version,
        (),
        tuple(EngineUnitResult(u, "completed", 1) for u in inp.units),
    )


@pytest.fixture
def run_setup(db: None) -> QCRun:
    return make_run(engine=ENGINE)


@pytest.fixture
def set_runner(monkeypatch):
    def _set(fn):
        monkeypatch.setattr(registry, "runner", lambda name, version: fn)

    return _set


@pytest.fixture
def inline_queue(monkeypatch):
    queued: list[int] = []

    def delay(pk: int):
        queued.append(pk)
        run_work_unit.apply(args=(pk,))

    monkeypatch.setattr(run_work_unit, "delay", delay)
    return queued


def first_unit(run: QCRun) -> WorkUnit:
    return run.work_units.order_by("shard_index").first()


# --- D1: retry/backoff thật, có chặn ---------------------------------------------------


def test_transient_failure_schedules_real_retry_with_2_4_8_backoff(run_setup, set_runner):
    calls = {"n": 0}

    def boom(inp: EngineInput) -> EngineOutput:
        calls["n"] += 1
        raise ConnectionError("tạm thời")

    set_runner(boom)
    unit = first_unit(run_setup)
    countdowns: list[float] = []

    def fake_retry(*, exc, countdown, max_retries):
        countdowns.append(countdown)
        assert max_retries == 3  # bị chặn, không còn None
        raise Retry()

    with mock.patch.object(run_work_unit, "retry", side_effect=fake_retry):
        for retries in (0, 1, 2):  # broker giao lại sau countdown
            run_work_unit.push_request(retries=retries)
            try:
                with pytest.raises(Retry):
                    run_work_unit.run(unit.pk)
            finally:
                run_work_unit.pop_request()
            unit.refresh_from_db()
            assert unit.status == WorkUnit.Status.RUNNING  # chưa FAILED khi còn retry
        run_work_unit.push_request(retries=3)
        try:
            with pytest.raises(ConnectionError):
                run_work_unit.run(unit.pk)
        finally:
            run_work_unit.pop_request()
    assert countdowns == [2, 4, 8]
    assert calls["n"] == 4  # lần đầu + 3 retry
    unit.refresh_from_db()
    assert unit.status == WorkUnit.Status.FAILED and "tạm thời" in unit.last_error
    assert ledger_counts(run_setup.pk, ENGINE).failed == 2
    assert ShardCommit.objects.count() == 0


def test_eager_flaky_engine_recovers_within_retries_and_counts_once(run_setup, set_runner):
    calls = {"n": 0}

    def flaky(inp: EngineInput) -> EngineOutput:
        calls["n"] += 1
        if calls["n"] <= 2:
            raise ConnectionError("tạm thời")
        return ok_output(inp)

    set_runner(flaky)
    unit = first_unit(run_setup)
    assert run_work_unit.apply(args=[unit.pk]).get() == WorkUnit.Status.COMPLETED
    assert calls["n"] == 3
    assert ShardCommit.objects.filter(run_id=run_setup.pk).count() == 1
    counts = ledger_counts(run_setup.pk, ENGINE)
    assert counts.completed == len(LedgerUnit.objects.filter(run_id=run_setup.pk)) - counts.pending


def test_eager_always_failing_engine_stops_after_three_retries(run_setup, set_runner):
    calls = {"n": 0}

    def boom(inp: EngineInput) -> EngineOutput:
        calls["n"] += 1
        raise ConnectionError("hỏng")

    set_runner(boom)
    unit = first_unit(run_setup)
    with pytest.raises(ConnectionError):
        run_work_unit.apply(args=[unit.pk]).get()
    assert calls["n"] == 4
    unit.refresh_from_db()
    assert unit.status == WorkUnit.Status.FAILED and unit.finished_at is not None


def test_retry_publish_failure_returns_unit_to_pending(run_setup, set_runner):
    set_runner(mock.Mock(side_effect=ConnectionError("x")))
    unit = first_unit(run_setup)
    with mock.patch.object(run_work_unit, "retry", side_effect=OSError("broker down")):
        with pytest.raises(OSError):
            run_work_unit.run(unit.pk)
    unit.refresh_from_db()
    assert unit.status == WorkUnit.Status.PENDING  # redispatch nhặt lại được


def test_completed_ledger_rows_are_not_overwritten_by_failed_retry(run_setup, set_runner):
    unit = first_unit(run_setup)
    set_runner(ok_output)
    run_work_unit.apply(args=[unit.pk]).get()
    before = list(LedgerUnit.objects.filter(run_id=run_setup.pk).values_list("pk", "outcome"))
    WorkUnit.objects.filter(pk=unit.pk).update(status=WorkUnit.Status.PENDING)  # giao lại muộn
    set_runner(mock.Mock(side_effect=ValueError("không được gọi")))
    run_work_unit.apply(args=[unit.pk]).get()  # ShardCommit đã có -> không chạy engine
    assert (
        list(LedgerUnit.objects.filter(run_id=run_setup.pk).values_list("pk", "outcome")) == before
    )
    assert ShardCommit.objects.count() == 1


# --- D2: broker lỗi, redispatch ---------------------------------------------------------


def test_broker_failure_midway_leaves_pending_and_redispatch_recovers(
    run_setup, monkeypatch, set_runner
):
    set_runner(ok_output)
    sent: list[int] = []

    def delay(pk: int):
        if not sent:
            sent.append(pk)
            raise ConnectionError("broker down")
        sent.append(pk)

    monkeypatch.setattr(run_work_unit, "delay", delay)
    assert dispatch_run(run_setup.pk) == 1  # unit 2 gửi được, unit 1 lỗi: không ném
    statuses = sorted(run_setup.work_units.values_list("status", flat=True))
    assert statuses == ["pending", "pending"]  # delay chỉ ghi nhận, chưa chạy
    assert QCRun.objects.get(pk=run_setup.pk).status == QCRun.Status.QUEUED
    ledger_rows = LedgerUnit.objects.filter(run_id=run_setup.pk).count()

    monkeypatch.setattr(run_work_unit, "delay", lambda pk: run_work_unit.apply(args=(pk,)))
    result = redispatch_pending(0)
    assert result == {"runs": 1, "queued": 2}
    run = QCRun.objects.get(pk=run_setup.pk)
    assert run.status == QCRun.Status.COMPLETED and run.finished_at is not None
    assert LedgerUnit.objects.filter(run_id=run.pk).count() == ledger_rows
    assert ShardCommit.objects.filter(run_id=run.pk).count() == 2
    assert redispatch_pending(0) == {"runs": 0, "queued": 0}  # terminal: không dispatch nữa


def test_create_run_survives_broker_failure_after_commit(settings, monkeypatch):
    settings.ORCHESTRATION_AUTO_DISPATCH = True
    monkeypatch.setattr(run_work_unit, "delay", mock.Mock(side_effect=ConnectionError("down")))
    run = make_run(engine=ENGINE)  # không ném dù broker lỗi sau commit
    assert QCRun.objects.get(pk=run.pk).status == QCRun.Status.QUEUED
    assert set(run.work_units.values_list("status", flat=True)) == {"pending"}


def test_dispatch_exception_in_on_commit_is_swallowed(settings, monkeypatch):
    settings.ORCHESTRATION_AUTO_DISPATCH = True
    monkeypatch.setattr(dispatch_module, "dispatch_run", mock.Mock(side_effect=RuntimeError("db")))
    run = make_run(engine=ENGINE)
    assert QCRun.objects.filter(pk=run.pk).exists()


def test_redispatch_respects_threshold_and_skips_cancelled(run_setup, monkeypatch):
    seen: list[int] = []
    monkeypatch.setattr(run_work_unit, "delay", seen.append)
    assert redispatch_pending(3600) == {"runs": 0, "queued": 0}  # run còn mới
    cancel_qc_run(run_id=run_setup.pk, actor=run_setup.created_by)
    assert redispatch_pending(0) == {"runs": 0, "queued": 0}
    assert dispatch_run(run_setup.pk) == 0 and seen == []


def test_redispatch_recovers_stale_running_shards(run_setup, monkeypatch):
    from datetime import timedelta

    from django.utils import timezone

    seen: list[int] = []
    monkeypatch.setattr(run_work_unit, "delay", seen.append)
    stale, fresh = list(run_setup.work_units.all()[:2])
    WorkUnit.objects.filter(pk=stale.pk).update(
        status=WorkUnit.Status.RUNNING, started_at=timezone.now() - timedelta(hours=1)
    )
    WorkUnit.objects.filter(pk=fresh.pk).update(
        status=WorkUnit.Status.RUNNING, started_at=timezone.now()
    )
    redispatch_pending(1800, 1800)  # chỉ shard RUNNING có lease quá 30 phút bị thu hồi
    assert WorkUnit.objects.get(pk=stale.pk).status == WorkUnit.Status.PENDING
    assert WorkUnit.objects.get(pk=fresh.pk).status == WorkUnit.Status.RUNNING
    redispatch_pending(0, 1800)  # run đủ tuổi: shard PENDING được xếp lại
    assert stale.pk in seen and fresh.pk not in seen


def test_live_long_running_shard_is_not_reset_repeatedly(run_setup, monkeypatch):
    """Shard sống lâu (lease được làm mới khi nhận) không bị sweeper thu hồi lặp lại."""
    from datetime import timedelta

    from django.utils import timezone

    seen: list[int] = []
    monkeypatch.setattr(run_work_unit, "delay", seen.append)
    unit = run_setup.work_units.first()
    # started_at cũ do lần nhận trước, nhưng worker nhận lại -> lease mới
    WorkUnit.objects.filter(pk=unit.pk).update(
        status=WorkUnit.Status.RUNNING, started_at=timezone.now() - timedelta(hours=3)
    )
    WorkUnit.objects.filter(pk=unit.pk).update(started_at=timezone.now())  # claim làm mới lease
    for _ in range(3):  # nhiều lượt sweep liên tiếp
        redispatch_pending(0, 1800)
    assert WorkUnit.objects.get(pk=unit.pk).status == WorkUnit.Status.RUNNING
    assert unit.pk not in seen


def test_redispatch_does_not_amplify_backlogged_messages(run_setup, monkeypatch):
    """Unit đã gửi gần đây (queue backlog) không bị gửi lại mỗi lượt sweep."""
    seen: list[int] = []
    monkeypatch.setattr(run_work_unit, "delay", seen.append)
    assert dispatch_run(run_setup.pk) == 2  # lần gửi đầu: đánh dấu dispatched_at
    assert redispatch_pending(300, 1800) == {"runs": 0, "queued": 0}  # run còn mới
    assert dispatch_run(run_setup.pk, stale_after=300) == 0  # vừa gửi -> không nhân message
    assert len(seen) == 2
    WorkUnit.objects.filter(run=run_setup).update(dispatched_at=None)
    assert dispatch_run(run_setup.pk, stale_after=300) == 2  # chưa từng gửi/quá hạn -> gửi lại


def test_claim_refreshes_lease(run_setup, set_runner):
    from datetime import timedelta

    from django.utils import timezone

    set_runner(ok_output)
    unit = run_setup.work_units.first()
    old = timezone.now() - timedelta(hours=5)
    WorkUnit.objects.filter(pk=unit.pk).update(started_at=old)
    run_work_unit.apply(args=(unit.pk,))
    assert WorkUnit.objects.get(pk=unit.pk).started_at > old


def test_management_command_redispatches(run_setup, monkeypatch):
    seen: list[int] = []
    monkeypatch.setattr(run_work_unit, "delay", seen.append)
    out = StringIO()
    call_command("redispatch_pending_runs", "--older-than", "0", stdout=out)
    assert "runs=1 queued=2" in out.getvalue() and len(seen) == 2


def test_tasks_registered_for_worker_and_beat():
    assert "orchestration.run_work_unit" in celery_app.tasks
    assert "orchestration.redispatch_pending" in celery_app.tasks
    from django.conf import settings

    entry = settings.CELERY_BEAT_SCHEDULE["orchestration-redispatch-pending"]
    assert entry["task"] == "orchestration.redispatch_pending"


# --- D3: huỷ, worker chết, giao lại -----------------------------------------------------


def test_cancel_during_run_is_not_overwritten_and_run_not_ranked(run_setup, set_runner):
    def cancelling(inp: EngineInput) -> EngineOutput:
        cancel_qc_run(run_id=run_setup.pk, actor=run_setup.created_by)  # huỷ giữa lúc chạy
        return ok_output(inp)

    set_runner(cancelling)
    unit = first_unit(run_setup)
    assert run_work_unit.apply(args=[unit.pk]).get() == WorkUnit.Status.CANCELLED
    unit.refresh_from_db()
    assert unit.status == WorkUnit.Status.CANCELLED
    run = QCRun.objects.get(pk=run_setup.pk)
    assert run.status == QCRun.Status.CANCELLED and run.finished_at is not None
    assert RunRanking.objects.filter(run=run).count() == 0
    # Shard đang chạy lúc huỷ không được ghi ShardCommit/candidate cho run đã huỷ.
    assert ShardCommit.objects.filter(run_id=run.pk).count() == 0
    assert CandidateRecord.objects.filter(run_id=run.pk).count() == 0
    other = run.work_units.exclude(pk=unit.pk).get()
    run_work_unit.apply(args=[other.pk]).get()  # shard đến muộn: bị bỏ qua
    other.refresh_from_db()
    run.refresh_from_db()
    assert other.status == WorkUnit.Status.CANCELLED and run.status == QCRun.Status.CANCELLED
    assert RunRanking.objects.filter(run=run).count() == 0


def test_cancel_during_failing_run_does_not_flip_unit_to_failed(run_setup, set_runner):
    def cancel_then_boom(inp: EngineInput) -> EngineOutput:
        cancel_qc_run(run_id=run_setup.pk, actor=run_setup.created_by)
        raise ValueError("lỗi cố định")

    set_runner(cancel_then_boom)
    unit = first_unit(run_setup)
    with pytest.raises(ValueError):
        run_work_unit.apply(args=[unit.pk]).get()
    unit.refresh_from_db()
    assert unit.status == WorkUnit.Status.CANCELLED
    assert QCRun.objects.get(pk=run_setup.pk).status == QCRun.Status.CANCELLED


def test_worker_killed_before_commit_redelivery_completes_once(inline_queue):
    run = make_run(engine="duplicate", shapes=SHAPES)
    unit = first_unit(run)
    with mock.patch("orchestration.services._apply_unit_results", side_effect=WorkerKilled()):
        with pytest.raises(WorkerKilled):
            run_work_unit.run(unit.pk)
    unit.refresh_from_db()
    assert unit.status == WorkUnit.Status.RUNNING  # chưa ack, broker sẽ giao lại
    assert ShardCommit.objects.count() == 0 and CandidateRecord.objects.count() == 0
    assert run_work_unit.apply(args=[unit.pk]).get() == WorkUnit.Status.COMPLETED
    assert ShardCommit.objects.filter(run_id=run.pk).count() == 1
    assert CandidateRecord.objects.filter(run_id=run.pk).count() == 1


def test_worker_killed_after_commit_redelivery_completes_once_without_rerun(inline_queue):
    run = make_run(engine="duplicate", shapes=SHAPES)
    unit = first_unit(run)
    real_finish = dispatch_module._finish_unit
    with mock.patch.object(dispatch_module, "_finish_unit", side_effect=WorkerKilled()):
        with pytest.raises(WorkerKilled):
            run_work_unit.run(unit.pk)
    unit.refresh_from_db()
    assert unit.status == WorkUnit.Status.RUNNING
    assert ShardCommit.objects.filter(run_id=run.pk).count() == 1
    candidates = CandidateRecord.objects.filter(run_id=run.pk).count()
    ledger = list(LedgerUnit.objects.filter(run_id=run.pk).values_list("pk", "outcome"))
    with mock.patch(
        "orchestration.tasks.registry.runner", side_effect=AssertionError("không chạy lại")
    ):
        assert run_work_unit.apply(args=[unit.pk]).get() == WorkUnit.Status.COMPLETED
    assert real_finish is dispatch_module._finish_unit
    assert ShardCommit.objects.filter(run_id=run.pk).count() == 1
    assert CandidateRecord.objects.filter(run_id=run.pk).count() == candidates
    assert list(LedgerUnit.objects.filter(run_id=run.pk).values_list("pk", "outcome")) == ledger


def test_repeated_dispatch_and_duplicate_messages_do_not_duplicate(inline_queue):
    run = make_run(engine="duplicate", shapes=SHAPES)
    assert dispatch_run(run.pk) == 2
    snapshot = (
        ShardCommit.objects.count(),
        CandidateRecord.objects.count(),
        LedgerUnit.objects.count(),
    )
    assert dispatch_run(run.pk) == 0  # run đã terminal
    for unit in run.work_units.all():  # message trùng
        assert run_work_unit.apply(args=[unit.pk]).get() == WorkUnit.Status.COMPLETED
    assert (
        ShardCommit.objects.count(),
        CandidateRecord.objects.count(),
        LedgerUnit.objects.count(),
    ) == snapshot
    assert QCRun.objects.get(pk=run.pk).status == QCRun.Status.COMPLETED


# --- D4: shard rỗng, engine thiếu/sai version, trạng thái run ----------------------------


def test_empty_shard_completes_with_empty_ledger(run_setup, set_runner):
    set_runner(ok_output)
    unit = first_unit(run_setup)
    WorkUnit.objects.filter(pk=unit.pk).update(shard_key="job:5:empty")
    assert run_work_unit.apply(args=[unit.pk]).get() == WorkUnit.Status.COMPLETED
    assert ShardCommit.objects.filter(run_id=run_setup.pk).count() == 1


def test_frames_shard_without_frames_fails_not_silently_passes(run_setup, set_runner):
    set_runner(ok_output)
    unit = first_unit(run_setup)
    WorkUnit.objects.filter(pk=unit.pk).update(shard_key="job:5:frames:50-60")
    with pytest.raises(ValueError):
        run_work_unit.apply(args=[unit.pk]).get()
    unit.refresh_from_db()
    assert unit.status == WorkUnit.Status.FAILED and "không có frame" in unit.last_error
    assert ShardCommit.objects.count() == 0


def test_engine_version_mismatch_fails_shard():
    run = make_run(engine="duplicate")
    run.engine_versions = {"duplicate": "9.9.9"}
    run.save(update_fields=["engine_versions"])
    unit = first_unit(run)
    with pytest.raises(LookupError):
        run_work_unit.apply(args=[unit.pk]).get()
    unit.refresh_from_db()
    assert unit.status == WorkUnit.Status.FAILED and "chưa đăng ký" in unit.last_error
    assert ShardCommit.objects.count() == 0


def test_unregistered_engine_fails_all_shards_and_run_failed(run_setup, inline_queue):
    # ENGINE "duplicate_overlap" không có trong registry (tên đăng ký là "duplicate").
    dispatch_run(run_setup.pk)
    run = QCRun.objects.get(pk=run_setup.pk)
    assert run.status == QCRun.Status.FAILED and run.finished_at is not None
    assert set(run.work_units.values_list("status", flat=True)) == {"failed"}
    assert RunRanking.objects.filter(run=run).count() == 0


def test_run_without_work_units_terminates(run_setup):
    run_setup.work_units.all().delete()
    assert dispatch_run(run_setup.pk) == 0
    run = QCRun.objects.get(pk=run_setup.pk)
    assert run.status == QCRun.Status.COMPLETED and run.finished_at is not None


def test_run_state_queued_running_completed_and_partial(run_setup, set_runner, inline_queue):
    states: list[str] = []

    def probe(inp: EngineInput) -> EngineOutput:
        states.append(QCRun.objects.get(pk=inp.run_id).status)
        if inp.shard_index == 0:
            raise ValueError("lỗi cố định")
        return ok_output(inp)

    set_runner(probe)
    assert QCRun.objects.get(pk=run_setup.pk).status == QCRun.Status.QUEUED
    assert QCRun.objects.get(pk=run_setup.pk).started_at is None
    dispatch_run(run_setup.pk)
    assert states == ["running", "running"]
    run = QCRun.objects.get(pk=run_setup.pk)
    assert run.status == QCRun.Status.PARTIAL
    assert run.started_at is not None and run.finished_at is not None
    assert RunRanking.objects.filter(run=run).count() == 0  # partial không publish ranking


def test_second_run_same_input_still_independent(run_setup, set_runner, inline_queue):
    set_runner(ok_output)
    other, _ = create_qc_run(
        snapshot_id=run_setup.snapshot_id,
        config_version_id=run_setup.config_version_id,
        seed=7,
        created_by=run_setup.created_by,
    )
    dispatch_run(run_setup.pk)
    dispatch_run(other.pk)
    assert ShardCommit.objects.count() == 4


def test_broker_down_publish_is_bounded_not_hanging():
    """Redis chết làm `.delay()` treo vô hạn khi còn result backend; cấu hình phải chặn việc đó."""
    from django.conf import settings

    assert settings.CELERY_TASK_IGNORE_RESULT is True
    assert settings.CELERY_TASK_PUBLISH_RETRY_POLICY["max_retries"] <= 3
    assert settings.CELERY_BROKER_TRANSPORT_OPTIONS["socket_connect_timeout"] <= 5
