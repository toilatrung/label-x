from __future__ import annotations

from unittest import mock

import pytest

from engines.interface import (
    Anchor,
    Candidate,
    EngineConfig,
    EngineDescriptor,
    EngineInput,
    EngineOutput,
    EngineUnitRef,
    EngineUnitResult,
    FrameKey,
    ObjectRef,
)
from orchestration import services
from orchestration.dedup import dedup_key
from orchestration.models import CandidateRecord, LedgerUnit, ShardCommit
from orchestration.registry import EngineRegistry
from orchestration.retry import RetryPolicy
from orchestration.services import (
    ShardOutputError,
    commit_shard_output,
    engine_input_from_payload,
    engine_input_to_payload,
    ledger_counts,
    mark_shard_failed,
    run_metrics,
    seed_ledger,
)
from orchestration.tasks import execute_shard, run_engine_shard
from tests.orchestration.helpers import make_run

pytestmark = pytest.mark.django_db(transaction=True)

ENGINE = "fake"
RUN = 0  # id QCRun thật, gán bởi fixture autouse


@pytest.fixture(autouse=True)
def _real_run(db):
    global RUN
    RUN = make_run().pk


def units(*frames: int) -> tuple[EngineUnitRef, ...]:
    return tuple(EngineUnitRef("frame", FrameKey(1, f)) for f in frames)


def make_input(shard: int, frames: tuple[int, ...], run_id: int | None = None) -> EngineInput:
    run_id = run_id or RUN
    return EngineInput(
        idempotency_key=f"key-{run_id}-{shard}",
        run_id=run_id,
        snapshot_id=3,
        engine=ENGINE,
        engine_version="1.0.0",
        config=EngineConfig(ENGINE, "1.0.0", True, {"t": 0.5}),
        seed=1,
        shard_index=shard,
        units=units(*frames),
    )


def candidate(frame: int, objects: tuple[str, ...] = ("a", "b")) -> Candidate:
    return Candidate(
        engine=ENGINE,
        engine_version="1.0.0",
        family="duplicate",
        frame=FrameKey(1, frame),
        anchor=Anchor("pair", tuple(ObjectRef("cvat", o) for o in objects), "1.0.0", "R-1"),
        evidence={"iou": 0.9, "ids": list(objects)},
    )


def make_output(inp: EngineInput, candidates=(), outcome="completed") -> EngineOutput:
    return EngineOutput(
        idempotency_key=inp.idempotency_key,
        engine=inp.engine,
        engine_version=inp.engine_version,
        candidates=tuple(candidates),
        unit_results=tuple(EngineUnitResult(u, outcome, 1) for u in inp.units),
    )


def snapshot_state(run_id: int | None = None) -> tuple[int, int, int, list]:
    run_id = run_id or RUN
    return (
        ShardCommit.objects.filter(run_id=run_id).count(),
        CandidateRecord.objects.filter(run_id=run_id).count(),
        LedgerUnit.objects.filter(run_id=run_id).count(),
        sorted(LedgerUnit.objects.values_list("frame_number", "outcome")),
    )


def test_commit_is_idempotent_for_same_key():
    inp = make_input(0, (0, 1))
    seed_ledger(RUN, ENGINE, inp.units)
    out = make_output(inp, [candidate(0)])
    assert commit_shard_output(inp, out) is True
    before = snapshot_state()
    assert commit_shard_output(inp, out) is False
    assert snapshot_state() == before


def test_crash_mid_commit_rolls_back_then_retry_writes_once():
    inp = make_input(0, (0, 1))
    seed_ledger(RUN, ENGINE, inp.units)
    out = make_output(inp, [candidate(0)])
    with mock.patch.object(services, "_apply_unit_results", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            commit_shard_output(inp, out)
    assert snapshot_state()[:2] == (0, 0)
    assert ledger_counts(RUN, ENGINE).pending == 2
    assert commit_shard_output(inp, out) is True
    assert snapshot_state()[:2] == (1, 1)
    assert ledger_counts(RUN, ENGINE).completed == 2


def test_dedup_across_shards_keeps_one_candidate_regardless_of_object_order():
    a, b = make_input(0, (0,)), make_input(1, (1,))
    seed_ledger(RUN, ENGINE, a.units + b.units)
    assert dedup_key(candidate(0, ("a", "b"))) == dedup_key(candidate(0, ("b", "a")))
    commit_shard_output(a, make_output(a, [candidate(0), candidate(0, ("b", "a"))]))
    commit_shard_output(b, make_output(b, [candidate(1)]))
    assert CandidateRecord.objects.filter(run_id=RUN).count() == 2


def test_policy_version_changes_dedup_key():
    c = candidate(0)
    newer = Candidate(**{**c.__dict__, "anchor": Anchor("pair", c.anchor.objects, "2.0.0", "R-1")})
    assert dedup_key(c) != dedup_key(newer)


def test_ledger_total_invariant_and_failed_stays_in_denominator():
    a, b = make_input(0, (0, 1)), make_input(1, (2,))
    seed_ledger(RUN, ENGINE, a.units + b.units)
    assert ledger_counts(RUN, ENGINE).total == 3
    commit_shard_output(a, make_output(a))
    mark_shard_failed(b, attempts=4)
    counts = ledger_counts(RUN, ENGINE)
    assert (counts.total, counts.eligible, counts.completed, counts.failed) == (3, 3, 2, 1)
    assert counts.coverage == pytest.approx(2 / 3)
    # retry-failed: cùng key chạy lại được và không đổi tổng
    assert commit_shard_output(b, make_output(b)) is True
    counts = ledger_counts(RUN, ENGINE)
    assert (counts.total, counts.completed, counts.failed) == (3, 3, 0)


def test_seed_is_idempotent():
    inp = make_input(0, (0, 1))
    assert seed_ledger(RUN, ENGINE, inp.units) == 2
    assert seed_ledger(RUN, ENGINE, inp.units) == 0


def test_output_must_cover_exactly_shard_units():
    inp = make_input(0, (0, 1))
    seed_ledger(RUN, ENGINE, inp.units)
    short = make_output(make_input(0, (0,)))
    short = EngineOutput(inp.idempotency_key, ENGINE, "1.0.0", (), short.unit_results)
    with pytest.raises(ShardOutputError):
        commit_shard_output(inp, short)
    with pytest.raises(ShardOutputError):
        commit_shard_output(inp, make_output(inp, outcome="pending"))
    assert snapshot_state()[0] == 0


def test_unseeded_unit_rejected_and_rolled_back():
    inp = make_input(0, (0,))
    with pytest.raises(ShardOutputError):
        commit_shard_output(inp, make_output(inp, [candidate(0)]))
    assert snapshot_state()[:2] == (0, 0)


def test_payload_roundtrip():
    inp = make_input(2, (4, 5))
    assert engine_input_from_payload(engine_input_to_payload(inp)) == inp


def test_registry():
    reg = EngineRegistry()
    desc = EngineDescriptor(ENGINE, "1.0.0", "frame", True, False, False, "1")
    runner = mock.Mock()
    reg.register(desc, runner)
    assert reg.descriptor(ENGINE, "1.0.0") is desc
    assert reg.runner(ENGINE, "1.0.0") is runner
    with pytest.raises(ValueError):
        reg.register(desc, runner)
    with pytest.raises(LookupError):
        reg.runner("other", "1")


def test_backoff_exponential_capped_and_bounded_retries():
    p = RetryPolicy(max_retries=3, base_seconds=2, factor=2, cap_seconds=5)
    assert [p.backoff(n) for n in (1, 2, 3)] == [2, 4, 5]
    assert not p.exhausted(2) and p.exhausted(3)
    with pytest.raises(ValueError):
        p.backoff(0)


def test_ac02_forced_shard_failure_then_retry_keeps_counts(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = False
    reg = EngineRegistry()
    desc = EngineDescriptor(ENGINE, "1.0.0", "frame", True, False, False, "1")
    calls = {"n": 0}

    def flaky(inp: EngineInput) -> EngineOutput:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("transient")
        return make_output(inp, [candidate(0)])

    reg.register(desc, flaky)
    inp = make_input(0, (0, 1))
    seed_ledger(RUN, ENGINE, inp.units)
    with pytest.raises(ConnectionError):
        execute_shard(inp, engines=reg)
    assert snapshot_state()[:2] == (0, 0)
    assert execute_shard(inp, engines=reg) is True
    assert execute_shard(inp, engines=reg) is False  # worker chạy lại sau ack muộn
    assert snapshot_state()[:2] == (1, 1)
    metrics = run_metrics(RUN)
    assert metrics["shards_committed"] == 1 and metrics["ledger"][ENGINE]["completed"] == 2


def test_task_marks_failed_on_permanent_error():
    inp = make_input(0, (0,))
    seed_ledger(RUN, ENGINE, inp.units)
    with pytest.raises(LookupError):  # engine chưa đăng ký
        run_engine_shard.apply(args=[engine_input_to_payload(inp)]).get()
    assert ledger_counts(RUN, ENGINE).failed == 1


def test_task_retries_with_backoff_then_fails_when_exhausted():
    inp = make_input(0, (0,))
    seed_ledger(RUN, ENGINE, inp.units)
    with (
        mock.patch("orchestration.tasks.execute_shard", side_effect=ConnectionError("x")),
        mock.patch("orchestration.tasks.default_policy", return_value=RetryPolicy(max_retries=0)),
    ):
        with pytest.raises(ConnectionError):
            run_engine_shard.apply(args=[engine_input_to_payload(inp)]).get()
    assert ledger_counts(RUN, ENGINE).failed == 1


def test_run_id_attname_compat_for_readers_and_writers():
    """T-027/T-030 đọc/ghi bằng `run_id=`: FK không được phá cách dùng cũ."""
    inp = make_input(0, (0,))
    seed_ledger(RUN, ENGINE, inp.units)
    commit_shard_output(inp, make_output(inp, [candidate(0)]))
    assert CandidateRecord.objects.filter(run_id=RUN).get().run_id == RUN
    assert LedgerUnit.objects.filter(run_id=RUN, engine=ENGINE).count() == 1
    shard = ShardCommit.objects.get(run_id=RUN)
    row = LedgerUnit.objects.create(
        run_id=RUN, engine="other", kind="frame", cvat_task_id=1, frame_number=0
    )
    assert row.run_id == shard.run_id == RUN


def test_builtin_registration_is_idempotent():
    from orchestration.builtin_engines import register_builtin_engines
    from orchestration.registry import registry

    register_builtin_engines(registry)
    register_builtin_engines(registry)
    assert [d.name for d in registry.descriptors()].count("duplicate") == 1


def test_auto_dispatch_disabled_in_tests(settings):
    assert settings.ORCHESTRATION_AUTO_DISPATCH is False
