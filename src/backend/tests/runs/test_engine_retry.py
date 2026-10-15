"""Single-engine retries keep successes, evidence, budget, Review and other engines intact."""

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from engines.interface import EngineOutput, EngineUnitResult
from orchestration.dispatch import dispatch_run, run_work_unit
from orchestration.models import (
    Evaluation,
    LedgerUnit,
    ShardCommit,
    VlmBudget,
    VlmEvidence,
    VlmUnit,
)
from orchestration.registry import registry
from orchestration.services import vlm_ledger_counts
from orchestration.vlm_stage import dispatch_vlm_units, execute_vlm_unit
from runs.engine_retry import retry_failed_engine
from runs.models import EngineResult, WorkUnit
from runs.services import BusinessRuleUnmetError, InvalidTransitionError
from tests.orchestration.helpers import make_run
from tests.orchestration.test_vlm_stage import FakeClient, _make_run, _run_shards
from tests.orchestration.test_vlm_stage import _env as _env
from tests.vlm.test_contract import VALID
from vlm.errors import VlmProviderError, VlmProviderFailure

pytestmark = pytest.mark.django_db(transaction=True)


def failed_vlm_run():
    run = _make_run(vlm={**VALID, "max_attempts": 4, "budget": {"max_calls": 20}})
    _run_shards(run)
    units = list(VlmUnit.objects.filter(run=run).order_by("pk"))
    assert execute_vlm_unit(units[0].pk, client=FakeClient()) == "completed"
    assert (
        execute_vlm_unit(
            units[1].pk, client=FakeClient([VlmProviderError(VlmProviderFailure.AUTH)])
        )
        == "failed"
    )
    run.refresh_from_db()
    assert run.status == "partial"
    return run, units


def test_retry_vlm_only_failed_candidates_preserves_evidence_rankings_and_budget():
    run, units = failed_vlm_run()
    rankings = list(run.rankings.values())
    engine_results = list(run.engine_results.exclude(engine="vlm").values())
    work_units = list(run.work_units.values())
    evidence = list(VlmEvidence.objects.filter(run=run).values())
    budget_before = VlmBudget.objects.get(run=run).used_calls
    retry_failed_engine(run_id=run.pk, engine="vlm", actor=run.created_by)
    assert list(run.work_units.values()) == work_units
    assert list(run.engine_results.exclude(engine="vlm").values()) == engine_results
    latest = list(VlmUnit.objects.filter(run=run, evaluation_generation=2).order_by("pk"))
    assert len(latest) == 2
    assert {u.candidate_id for u in latest} == {u.candidate_id for u in units[1:]}
    assert Evaluation.objects.filter(run=run, generation=2, source="manual").count() == 2
    assert vlm_ledger_counts(run.pk).completed == 1
    assert vlm_ledger_counts(run.pk).pending == 2
    assert dispatch_run(run.pk) == 0  # No unrelated shard is queued.
    with patch("orchestration.vlm_stage.run_vlm_unit_task.delay") as delay:
        assert dispatch_vlm_units(run.pk) == 2
        assert {c.args[0] for c in delay.call_args_list} == {u.pk for u in latest}
        assert dispatch_vlm_units(run.pk) == 0
    for unit in latest:
        assert execute_vlm_unit(unit.pk, client=FakeClient()) == "completed"
    run.refresh_from_db()
    assert run.status == "completed"
    assert vlm_ledger_counts(run.pk).completed == 3
    assert vlm_ledger_counts(run.pk).failed == 0
    assert VlmBudget.objects.get(run=run).used_calls == budget_before + 2
    assert list(VlmEvidence.objects.filter(pk__in=[e["id"] for e in evidence]).values()) == evidence
    assert list(run.rankings.values()) == rankings
    assert list(run.work_units.values()) == work_units


def test_retry_vlm_failure_does_not_stop_other_retry_units():
    run, _ = failed_vlm_run()
    retry_failed_engine(run_id=run.pk, engine="vlm", actor=run.created_by)
    units = list(VlmUnit.objects.filter(run=run, evaluation_generation=2).order_by("pk"))
    assert (
        execute_vlm_unit(
            units[0].pk, client=FakeClient([VlmProviderError(VlmProviderFailure.AUTH)])
        )
        == "failed"
    )
    units[1].refresh_from_db()
    assert units[1].status == "pending"
    assert execute_vlm_unit(units[1].pk, client=FakeClient()) == "completed"
    run.refresh_from_db()
    assert run.status == "partial"
    retry_failed_engine(run_id=run.pk, engine="vlm", actor=run.created_by)
    assert VlmUnit.objects.filter(run=run, evaluation_generation=3).count() == 1


def test_duplicate_click_rejected_and_budget_exhaustion_rolls_back():
    run, _ = failed_vlm_run()
    VlmBudget.objects.filter(run=run).update(used_calls=20)
    with pytest.raises(BusinessRuleUnmetError, match="ngân sách"):
        retry_failed_engine(run_id=run.pk, engine="vlm", actor=run.created_by)
    assert not VlmUnit.objects.filter(run=run, evaluation_generation=2).exists()
    run.refresh_from_db()
    assert run.status == "partial"
    VlmBudget.objects.filter(run=run).update(used_calls=2)
    retry_failed_engine(run_id=run.pk, engine="vlm", actor=run.created_by)
    with pytest.raises(InvalidTransitionError):
        retry_failed_engine(run_id=run.pk, engine="vlm", actor=run.created_by)
    assert VlmUnit.objects.filter(run=run, evaluation_generation=2).count() == 2


def failed_shard_run(monkeypatch):
    run = make_run("duplicate")
    units = list(run.work_units.order_by("pk"))
    run_work_unit.apply(args=[units[0].pk]).get()

    def fail(inp):
        raise ValueError("broken engine")

    monkeypatch.setattr(registry, "runner", lambda *args: fail)
    with pytest.raises(ValueError):
        run_work_unit.apply(args=[units[1].pk]).get()
    run.refresh_from_db()
    assert run.status == "partial"
    return run, units


def test_retry_shard_only_selected_engine_preserves_success_and_other_failure(monkeypatch):
    run, units = failed_shard_run(monkeypatch)
    successful_commit = list(ShardCommit.objects.filter(run=run).values())
    EngineResult.objects.create(run=run, engine="geometry", status="failed", failed_units=1)
    other = WorkUnit.objects.create(
        run=run, engine="geometry", status="failed", shard_key="other", idempotency_key="other"
    )
    other_before = WorkUnit.objects.filter(pk=other.pk).values().get()
    retry_failed_engine(run_id=run.pk, engine="duplicate", actor=run.created_by)
    units[0].refresh_from_db()
    units[1].refresh_from_db()
    assert units[0].status == "completed" and units[0].attempt == 1
    assert units[1].status == "pending" and units[1].attempt == 2
    assert WorkUnit.objects.filter(pk=other.pk).values().get() == other_before
    with (
        patch("orchestration.dispatch.run_work_unit.delay") as delay,
        patch("orchestration.vlm_stage.run_vlm_unit_task.delay") as vlm_delay,
    ):
        assert dispatch_run(run.pk) == 1
        assert delay.call_args.args == (units[1].pk,)
        assert dispatch_vlm_units(run.pk) == 0
        vlm_delay.assert_not_called()
    monkeypatch.setattr(
        registry,
        "runner",
        lambda *args: (
            lambda inp: EngineOutput(
                inp.idempotency_key,
                inp.engine,
                inp.engine_version,
                (),
                tuple(EngineUnitResult(u, "completed", 1) for u in inp.units),
            )
        ),
    )
    run_work_unit.apply(args=[units[1].pk]).get()
    run.refresh_from_db()
    assert run.status == "partial"  # The other engine still failed.
    assert run.engine_results.get(engine="duplicate").failed_units == 0
    assert (
        list(ShardCommit.objects.filter(pk__in=[s["id"] for s in successful_commit]).values())
        == successful_commit
    )
    assert WorkUnit.objects.filter(pk=other.pk).values().get() == other_before


def test_retry_frame_failure_inside_committed_shard_keeps_original_commit(monkeypatch):
    run = make_run("duplicate")

    def partial(inp):
        return EngineOutput(
            inp.idempotency_key,
            inp.engine,
            inp.engine_version,
            (),
            tuple(
                EngineUnitResult(u, "failed" if u.frame.frame_number == 1 else "completed", 1)
                for u in inp.units
            ),
        )

    monkeypatch.setattr(registry, "runner", lambda *args: partial)
    for unit in run.work_units.all():
        run_work_unit.apply(args=[unit.pk]).get()
    original = list(ShardCommit.objects.filter(run=run).values())
    retry_failed_engine(run_id=run.pk, engine="duplicate", actor=run.created_by)
    retry_unit = run.work_units.get(status="pending")
    assert ":frames:1-1:retry:" in retry_unit.shard_key
    assert list(ShardCommit.objects.filter(run=run).values()) == original
    completed = list(LedgerUnit.objects.filter(run=run, outcome="completed").values())
    monkeypatch.setattr(
        registry,
        "runner",
        lambda *args: (
            lambda inp: EngineOutput(
                inp.idempotency_key,
                inp.engine,
                inp.engine_version,
                (),
                tuple(EngineUnitResult(u, "completed", 1) for u in inp.units),
            )
        ),
    )
    run_work_unit.apply(args=[retry_unit.pk]).get()
    assert (
        list(LedgerUnit.objects.filter(pk__in=[r["id"] for r in completed]).values()) == completed
    )
    assert not LedgerUnit.objects.filter(run=run, outcome="failed").exists()
    run.refresh_from_db()
    assert run.status == "completed"


def test_retry_api_permission_scope_validation_and_selected_engine(monkeypatch):
    run, _ = failed_shard_run(monkeypatch)
    client = APIClient()
    client.force_authenticate(run.created_by)
    url = f"/api/runs/{run.pk}/retry-failed/"
    assert client.post(url, {"engine": "duplicate"}, format="json").status_code == 403
    RoleAssignment.objects.create(user=run.created_by, role=Role.QA_LEAD, dataset_id=999)
    assert client.post(url, {"engine": "duplicate"}, format="json").status_code == 403
    RoleAssignment.objects.create(user=run.created_by, role=Role.QA_LEAD, dataset_id=1)
    assert client.post(url, {"engine": "all"}, format="json").status_code == 400
    assert client.post(url, {"engine": "schema"}, format="json").status_code == 409
    response = client.post(url, {"engine": "duplicate"}, format="json")
    assert response.status_code == 202, response.data
    assert response.data["id"] == run.pk
    assert client.post(url, {"engine": "duplicate"}, format="json").status_code == 409
