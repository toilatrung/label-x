"""Failure recovery with fake endpoints, durable retry state and no broker traffic."""

from datetime import timedelta

import pytest
from django.utils import timezone

from orchestration.dispatch import run_work_unit
from orchestration.models import ResourceLease, VlmAttempt, VlmBudget, VlmUnit
from orchestration.resources import EndpointLease, ResourceWaiting
from orchestration.runsync import refresh_run
from orchestration.vlm_stage import execute_vlm_unit
from runs.gpu_worker import WorkerUnavailable
from runs.models import QCRun, WorkUnit
from runs.progress import engine_progress
from tests.orchestration.helpers import make_run
from tests.orchestration.test_fail_fast import ok_output
from tests.orchestration.test_vlm_stage import FakeClient, _make_run, _provider_error, _run_shards
from tests.orchestration.test_vlm_stage import _env as _env
from tests.vlm.test_contract import VALID

pytestmark = pytest.mark.django_db(transaction=True)


def detector_run():
    run = make_run(engine="fake")
    run.work_units.update(engine="detector")
    run.engine_results.update(engine="detector")
    run.engine_versions = {"detector": "1.0.0"}
    run.save(update_fields=["engine_versions"])
    return run


def make_due():
    past = timezone.now() - timedelta(seconds=1)
    VlmUnit.objects.filter(status="pending").update(retry_at=past)
    WorkUnit.objects.filter(status="pending").update(retry_at=past)
    ResourceLease.objects.update(retry_at=past)


def test_endpoint_shared_across_instances_and_release():
    with EndpointLease("gpu:physical-worker", 60):
        with pytest.raises(ResourceWaiting):
            with EndpointLease("gpu:physical-worker/", 60):
                pytest.fail("second inference admitted")
    with EndpointLease("gpu:physical-worker", 60):
        pass


def test_uncertain_timeout_quarantines_until_lease_expires():
    with EndpointLease("gpu:timeout", 1800) as lease:
        lease.failed("timeout", uncertain=True)
    row = ResourceLease.objects.get()
    assert row.retry_at > timezone.now() + timedelta(seconds=1790)
    with pytest.raises(ResourceWaiting):
        with EndpointLease("gpu:timeout", 1800):
            pytest.fail("timed out remote request might still run")


def test_old_owner_cannot_release_new_lease():
    with EndpointLease("gpu:recovery", 60) as first:
        ResourceLease.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        with EndpointLease("gpu:recovery", 60) as second:
            first.__exit__()
            assert ResourceLease.objects.get().owner == second.owner


def test_detector_busy_defers_without_failing_siblings(settings, monkeypatch):
    from orchestration.registry import registry

    settings.ORCHESTRATION_FAIL_FAST = True
    run = detector_run()
    unit = run.work_units.order_by("pk").first()

    def busy(inp):
        raise WorkerUnavailable(
            "GPU Worker HTTP 503: worker_busy", code="worker_busy", retryable=True
        )

    monkeypatch.setattr(registry, "runner", lambda *args: busy)
    assert run_work_unit.apply(args=[unit.pk]).get() == "waiting_retry"
    unit.refresh_from_db()
    assert unit.status == "pending" and unit.retry_at
    assert unit.request_attempts == 0
    assert not run.work_units.filter(status="failed").exists()
    assert run_work_unit.apply(args=[unit.pk]).get() == "waiting_retry"
    make_due()
    monkeypatch.setattr(registry, "runner", lambda *args: ok_output)
    assert run_work_unit.apply(args=[unit.pk]).get() == "completed"
    assert engine_progress(run, "detector")["provider_calls"] == 1


def test_detector_auth_does_not_retry_or_poison_other_shards(monkeypatch):
    from orchestration.registry import registry

    run = detector_run()
    unit = run.work_units.order_by("pk").first()

    def denied(inp):
        raise WorkerUnavailable("GPU Worker từ chối xác thực.", code="auth")

    monkeypatch.setattr(registry, "runner", lambda *args: denied)
    assert run_work_unit.apply(args=[unit.pk]).get() == "failed"
    assert run.work_units.exclude(pk=unit.pk).filter(status="pending").exists()


def test_vlm_retry_is_durable_and_does_not_charge_early(settings):
    settings.ORCHESTRATION_FAIL_FAST = True
    run = _make_run(vlm={**VALID, "max_attempts": 3})
    _run_shards(run)
    unit = VlmUnit.objects.filter(run=run).first()
    client = FakeClient([_provider_error()])
    assert execute_vlm_unit(unit.pk, client=client) == "waiting_retry"
    assert client.calls == 1
    assert execute_vlm_unit(unit.pk, client=client) == "waiting_retry"
    assert client.calls == 1
    assert VlmAttempt.objects.filter(unit=unit).count() == 1
    make_due()
    assert execute_vlm_unit(unit.pk, client=client) == "completed"
    assert VlmBudget.objects.get(run=run).used_calls == 2
    assert execute_vlm_unit(unit.pk, client=client) == "completed"
    assert client.calls == 2


def test_vlm_exhaustion_is_per_candidate(settings):
    settings.ORCHESTRATION_FAIL_FAST = True
    run = _make_run(vlm={**VALID, "max_attempts": 2})
    _run_shards(run)
    units = list(VlmUnit.objects.filter(run=run).order_by("pk"))
    bad = FakeClient([_provider_error()] * 2)
    assert execute_vlm_unit(units[0].pk, client=bad) == "waiting_retry"
    make_due()
    assert execute_vlm_unit(units[0].pk, client=bad) == "failed"
    make_due()
    for unit in units[1:]:
        assert execute_vlm_unit(unit.pk, client=FakeClient()) == "completed"
    run.refresh_from_db()
    assert run.status == QCRun.Status.PARTIAL
    assert run.engine_results.get(engine="vlm").failed_units == 1


def test_vlm_deadline_finishes_unprocessed_as_skipped():
    run = _make_run()
    _run_shards(run)
    VlmBudget.objects.filter(run=run).update(started_at=timezone.now() - timedelta(hours=2))
    refresh_run(run.pk)
    run.refresh_from_db()
    assert run.status == QCRun.Status.PARTIAL
    assert set(VlmUnit.objects.filter(run=run).values_list("status", flat=True)) == {"skipped"}
    assert VlmAttempt.objects.filter(unit__run=run).count() == 0
    progress = engine_progress(run, "vlm")
    assert progress["failed"] == 0 and progress["skipped"] == 3
    from orchestration.services import vlm_ledger_counts
    from runs.vlm_read import build_vlm_view

    ledger = vlm_ledger_counts(run.pk)
    assert ledger.failed == 0 and ledger.not_checked == 3
    assert ledger.eligible == 3 and ledger.coverage == 0
    unit = VlmUnit.objects.filter(run=run).first()
    assert build_vlm_view(unit, "not_triggered")["state"] == "skipped"


def test_detector_completed_sibling_can_commit_after_another_shard_fails(monkeypatch):
    from orchestration.registry import registry

    run = detector_run()
    units = list(run.work_units.order_by("pk"))

    def first_failed(inp):
        raise WorkerUnavailable("bad batch", code="invalid_batch")

    monkeypatch.setattr(registry, "runner", lambda *args: first_failed)
    assert run_work_unit.apply(args=[units[0].pk]).get() == "failed"
    monkeypatch.setattr(registry, "runner", lambda *args: ok_output)
    assert run_work_unit.apply(args=[units[1].pk]).get() == "completed"
    run.refresh_from_db()
    assert run.status == "partial"


def test_detector_wait_deadline_settles_pending_without_inference():
    from orchestration.dispatch import prepare_work_unit

    run = detector_run()
    for unit in run.work_units.all():
        prepare_work_unit(unit)
    run.work_units.update(deadline_at=timezone.now() - timedelta(seconds=1))
    refresh_run(run.pk)
    run.refresh_from_db()
    assert run.status == "failed"
    assert set(run.work_units.values_list("error_code", flat=True)) == {"deadline_exceeded"}


@pytest.mark.parametrize("code", ["worker_busy", "inference_unavailable"])
def test_gpu_503_preserves_safe_error_code(monkeypatch, code):
    import httpx

    from runs import gpu_worker

    def unavailable(*args, **kwargs):
        response = httpx.Response(
            503, json={"error": code}, request=httpx.Request("POST", "https://gpu.test/infer")
        )
        raise httpx.HTTPStatusError("unavailable", request=response.request, response=response)

    monkeypatch.setattr(gpu_worker, "request_json", unavailable)
    with pytest.raises(WorkerUnavailable) as error:
        gpu_worker._request_worker(None, "/infer", {}, "https://gpu.test", "secret", 10)
    assert error.value.code == code
    assert error.value.retryable
    assert "secret" not in str(error.value)


def test_targeted_vlm_retry_that_expires_remains_partial(monkeypatch):
    from runs.engine_retry import retry_failed_engine

    run = _make_run()
    _run_shards(run)
    VlmBudget.objects.filter(run=run).update(started_at=timezone.now() - timedelta(hours=2))
    refresh_run(run.pk)
    retry_failed_engine(run_id=run.pk, engine="vlm", actor=run.created_by)
    from orchestration.vlm_stage import dispatch_vlm_units, run_vlm_unit_task

    monkeypatch.setattr(run_vlm_unit_task, "delay", lambda pk: None)
    dispatch_vlm_units(run.pk)
    assert not VlmUnit.objects.filter(
        run=run, evaluation_generation=2, deadline_at__isnull=True
    ).exists()
    VlmUnit.objects.filter(run=run, evaluation_generation=2).update(
        deadline_at=timezone.now() - timedelta(seconds=1)
    )
    refresh_run(run.pk)
    run.refresh_from_db()
    assert run.status == "partial"
    assert run.engine_results.get(engine="vlm").reason == "provider_unavailable"


def test_vlm_scheduled_retry_holds_dispatch_window(settings, monkeypatch):
    from orchestration.vlm_stage import dispatch_vlm_units, run_vlm_unit_task

    settings.VLM_DISPATCH_WINDOW = 1
    run = _make_run()
    _run_shards(run)
    first = VlmUnit.objects.filter(run=run).order_by("pk").first()
    assert execute_vlm_unit(first.pk, client=FakeClient([_provider_error()])) == "waiting_retry"
    sent = []
    monkeypatch.setattr(run_vlm_unit_task, "delay", lambda pk: sent.append(pk))
    assert dispatch_vlm_units(run.pk) == 0
    assert sent == []
    make_due()
    assert execute_vlm_unit(first.pk, client=FakeClient()) == "completed"
    assert dispatch_vlm_units(run.pk) == 1
    assert len(sent) == 1
