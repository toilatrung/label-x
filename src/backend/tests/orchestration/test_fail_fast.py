"""Failed engines stop, healthy engines continue and partial results reach Review."""

import pytest

from engines.interface import EngineOutput, EngineUnitResult
from orchestration.dispatch import _claim, build_engine_input, prepare_work_unit, run_work_unit
from orchestration.models import ShardCommit, VlmUnit
from orchestration.registry import registry
from orchestration.services import StaleLeaseError, commit_shard_output
from orchestration.vlm_stage import _claim_unit, _settle_unit, execute_vlm_unit
from runs.models import EngineResult, QCRun, RunRanking, WorkUnit
from runs.services import BusinessRuleUnmetError, retry_failed_qc_run
from tests.orchestration.helpers import make_run
from tests.orchestration.test_vlm_stage import FakeClient, _make_run, _provider_error, _run_shards
from tests.orchestration.test_vlm_stage import _env as _env
from vlm.contract import VlmStatus

pytestmark = pytest.mark.django_db(transaction=True)


def ok_output(inp):
    return EngineOutput(
        inp.idempotency_key,
        inp.engine,
        inp.engine_version,
        (),
        tuple(EngineUnitResult(u, "completed", 1) for u in inp.units),
    )


def test_first_error_stops_only_that_engine_and_publishes_partial(settings, monkeypatch):
    settings.ORCHESTRATION_FAIL_FAST = True
    run = make_run(engine="broken")
    run.engine_versions = {**run.engine_versions, "healthy": "1.0.0"}
    run.save(update_fields=["engine_versions"])
    EngineResult.objects.create(run=run, engine="healthy")
    healthy = WorkUnit.objects.create(
        run=run, engine="healthy", shard_key="job:5:frames:0-2", idempotency_key="healthy"
    )
    for unit in run.work_units.all():
        prepare_work_unit(unit)
    broken = list(run.work_units.filter(engine="broken"))
    late, token, _ = _claim(broken[1].pk, None)
    late_input = build_engine_input(late)
    calls = []

    def runner(inp):
        calls.append(inp.engine)
        if inp.engine == "broken":
            raise TimeoutError("inference timeout")
        return ok_output(inp)

    monkeypatch.setattr(registry, "runner", lambda name, version: runner)
    with pytest.raises(TimeoutError):
        run_work_unit.apply(args=[broken[0].pk]).get()
    assert set(run.work_units.filter(engine="broken").values_list("status", flat=True)) == {
        "failed"
    }
    late.refresh_from_db()
    assert late.lease_token == ""
    healthy.refresh_from_db()
    assert healthy.status == "pending"
    with pytest.raises(StaleLeaseError):
        commit_shard_output(late_input, ok_output(late_input), fence=(late.pk, token))
    assert not ShardCommit.objects.filter(run=run, engine="broken").exists()
    run_work_unit.apply(args=[broken[1].pk]).get()
    run_work_unit.apply(args=[healthy.pk]).get()
    assert calls == ["broken", "healthy"]
    run.refresh_from_db()
    assert run.status == QCRun.Status.PARTIAL
    assert run.score_version
    assert run.rankings.count() == len(RunRanking.Source.values)
    assert run.engine_results.get(engine="broken").failed_units == 3
    assert run.engine_results.get(engine="healthy").completed_units == 3
    with pytest.raises(BusinessRuleUnmetError, match="Review"):
        retry_failed_qc_run(run_id=run.pk, actor=run.created_by)


def test_vlm_failure_stops_siblings_and_late_evidence(settings, monkeypatch):
    settings.ORCHESTRATION_FAIL_FAST = True
    run = _make_run()
    _run_shards(run)
    units = list(VlmUnit.objects.filter(run=run).order_by("pk"))
    late, token, _ = _claim_unit(units[1].pk)
    client = FakeClient([_provider_error()] * 3)
    assert execute_vlm_unit(units[0].pk, client=client) == "failed"
    assert client.calls == 1
    assert set(VlmUnit.objects.filter(run=run).values_list("status", flat=True)) == {"failed"}
    assert not _settle_unit(late, token, {"status": VlmStatus.CHECKED.value})
    assert execute_vlm_unit(units[2].pk, client=client) == "failed"
    assert client.calls == 1
    run.refresh_from_db()
    assert run.status == QCRun.Status.PARTIAL
    assert run.engine_results.get(engine="vlm").failed_units == 3
    assert run.rankings.count() == len(RunRanking.Source.values)
