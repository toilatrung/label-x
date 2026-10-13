"""M04A-03: stage VLM phụ thuộc candidate, budget nguyên tử, retry, idempotency (mock).

Không có lời gọi Qwen thật; client là giả. Kết quả ở đây KHÔNG phải runtime pass.
"""

from __future__ import annotations

import json
import threading
from datetime import timedelta
from typing import Any

import httpx
import pytest
from django.contrib.auth.models import User
from django.db import close_old_connections
from django.utils import timezone

from engines.interface import (
    Anchor,
    Candidate,
    EngineInput,
    EngineOutput,
    EngineUnitResult,
    ObjectRef,
)
from orchestration.dispatch import redispatch_pending, run_work_unit
from orchestration.models import Evaluation, VlmAttempt, VlmBudget, VlmUnit
from orchestration.registry import registry
from orchestration.vlm_stage import (
    DbBudgetGate,
    compute_vlm_idempotency_key,
    execute_vlm_unit,
    start_vlm_stage,
)
from runs.models import ConfigVersion, QCRun
from runs.services import cancel_qc_run, create_qc_run
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot
from tests.vlm.test_contract import PNG, VALID
from vlm.client import DashScopeClient
from vlm.contract import CropInput
from vlm.errors import VlmInvalidCropError

pytestmark = pytest.mark.django_db(transaction=True)

ENGINE = "duplicate_overlap"
TAXONOMY = {
    "version": "t",
    "labels": [{"label_id": 1, "name": "car"}, {"label_id": 2, "name": "bus"}],
}


class FixtureCrops:
    """Nguồn crop giả: identity tất định, load trả PNG hợp lệ."""

    def identity(self, candidate: Any) -> str:
        return f"fixture-{candidate.pk}"

    def load(self, candidate: Any) -> CropInput:
        return CropInput(PNG, "image/png")


class BrokenCrops(FixtureCrops):
    def load(self, candidate: Any) -> CropInput:
        raise VlmInvalidCropError("hỏng")


class FakeClient:
    """Client giả đếm số lần gọi provider; `script` là hàng đợi phản hồi/ngoại lệ."""

    def __init__(self, script: list[Any] | None = None, label: str = "1") -> None:
        self.calls = 0
        self.script = list(script or [])
        self.label = label

    def preflight(self, request: Any) -> None:
        return None

    def complete(self, request: Any) -> tuple[str, str | None]:
        self.calls += 1
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return json.dumps({"label": self.label}), "req-1"


def _make_run(
    *,
    vlm: dict[str, Any] | None = None,
    with_taxonomy: bool = True,
    vlm_enabled: bool = True,
    frame_media: dict[int, bytes] | None = None,
    frame_size: tuple[int, int] = (10, 10),
    raw_shapes: list[dict[str, Any]] | None = None,
) -> QCRun:
    user, _ = User.objects.get_or_create(username="qa")
    frames = tuple(
        FrameExport(
            frame_index=i,
            source_frame_id=1000 + i,
            file_name=f"{i}.jpg",
            width=frame_size[0],
            height=frame_size[1],
            media_bytes=(frame_media or {}).get(i, f"frame-{i}".encode()),
            media_storage_key=f"snapshots/vlm/{i}.jpg",
        )
        for i in range(3)
    )
    job = JobExport(
        cvat_job_id=5,
        cvat_task_id=9,
        source_updated_at="2026-10-09T07:05:45Z",
        annotations={"shapes": raw_shapes or [], "tracks": []},
        frames=frames,
        assignee_cvat_user_id=None,
    )
    snap = create_locked_snapshot(
        dataset_id=1, created_by=user, jobs=[job], taxonomy_version="t", guideline_version="g"
    )
    engines: dict[str, Any] = {ENGINE: {"enabled": True}, "vlm": {"enabled": vlm_enabled}}
    if with_taxonomy:
        engines["schema"] = {"enabled": False, "params": {"taxonomy": TAXONOMY}}
    models: dict[str, Any] = {}
    cfg_vlm = VALID if vlm is None else vlm
    if cfg_vlm:
        models["vlm"] = cfg_vlm
    cfg = ConfigVersion.objects.create(
        name="c",
        status=ConfigVersion.Status.PUBLISHED,
        payload={"shard_size": 2},
        engines=engines,
        models=models,
        created_by=user,
        published_by=user,
        published_at=timezone.now(),
    )
    run, _ = create_qc_run(snapshot_id=snap.pk, config_version_id=cfg.pk, seed=1, created_by=user)
    return run


@pytest.fixture(autouse=True)
def _env(settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    settings.VLM_CROP_PROVIDER = "tests.orchestration.test_vlm_stage.FixtureCrops"
    settings.ORCHESTRATION_AUTO_DISPATCH = False
    monkeypatch.setenv("VLM_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test-not-real")

    def runner(inp: EngineInput) -> EngineOutput:
        candidates = tuple(
            Candidate(
                engine=inp.engine,
                engine_version=inp.engine_version,
                family="E1",
                frame=u.frame,
                anchor=Anchor(
                    "annotation", (ObjectRef("cvat", f"{u.frame.frame_number}"),), "p", "r"
                ),
                evidence={"frame": u.frame.frame_number, "confidence": 0.9},
            )
            for u in inp.units
        )
        return EngineOutput(
            inp.idempotency_key,
            inp.engine,
            inp.engine_version,
            candidates,
            tuple(EngineUnitResult(u, "completed", 1) for u in inp.units),
        )

    monkeypatch.setattr(registry, "runner", lambda name, version: runner)


def _run_shards(run: QCRun, only: int | None = None) -> None:
    units = list(run.work_units.order_by("shard_index"))
    for unit in units[: only if only is not None else len(units)]:
        run_work_unit.apply(args=[unit.pk]).get()


def _vlm_result(run: QCRun) -> Any:
    return run.engine_results.get(engine="vlm")


def test_vlm_units_only_after_all_candidate_shards_finish() -> None:
    run = _make_run()
    assert VlmUnit.objects.count() == 0 and not VlmBudget.objects.exists()
    _run_shards(run, only=1)  # còn shard mở
    assert VlmUnit.objects.count() == 0 and not VlmBudget.objects.exists()
    run.refresh_from_db()
    assert run.status == QCRun.Status.RUNNING
    _run_shards(run)
    units = VlmUnit.objects.filter(run_id=run.pk)
    assert units.count() == 3  # mỗi frame một candidate
    assert VlmBudget.objects.get(run_id=run.pk).max_calls == VALID["budget"]["max_calls"]
    run.refresh_from_db()
    assert run.status == QCRun.Status.RUNNING  # VLM chưa chạy xong: run chưa chốt


def test_full_flow_completes_run_and_vlm_failure_does_not_fail_run() -> None:
    run = _make_run()
    _run_shards(run)
    client = FakeClient()
    for unit in VlmUnit.objects.filter(run_id=run.pk):
        assert execute_vlm_unit(unit.pk, client=client) == "completed"
    run.refresh_from_db()
    assert run.status == QCRun.Status.COMPLETED
    result = _vlm_result(run)
    assert (result.status, result.eligible_units, result.completed_units) == ("checked", 3, 3)
    assert client.calls == 3
    unit = VlmUnit.objects.filter(run_id=run.pk).first()
    assert unit.result["label"] == "1" and unit.result["status"] == "checked"


def test_redelivery_does_not_recall_provider_or_charge_budget() -> None:
    run = _make_run()
    _run_shards(run)
    unit = VlmUnit.objects.filter(run_id=run.pk).first()
    client = FakeClient()
    assert execute_vlm_unit(unit.pk, client=client) == "completed"
    for _ in range(3):
        assert execute_vlm_unit(unit.pk, client=client) == "completed"
    assert client.calls == 1
    assert VlmBudget.objects.get(run_id=run.pk).used_calls == 1
    assert VlmAttempt.objects.filter(unit=unit).count() == 1


def test_retry_counts_each_real_attempt_once_max_three() -> None:
    run = _make_run()
    _run_shards(run)
    unit = VlmUnit.objects.filter(run_id=run.pk).first()
    sleeps: list[float] = []
    import vlm.runner as runner_module

    original = runner_module.time.sleep
    runner_module.time.sleep = sleeps.append  # type: ignore[assignment]
    try:
        client = FakeClient(
            [
                _provider_error(),
                _provider_error(),
                (json.dumps({"label": "1"}), "req-9"),
            ]
        )
        assert execute_vlm_unit(unit.pk, client=client) == "completed"
    finally:
        runner_module.time.sleep = original  # type: ignore[assignment]
    assert client.calls == 3
    assert VlmBudget.objects.get(run_id=run.pk).used_calls == 3
    assert sorted(VlmAttempt.objects.filter(unit=unit).values_list("attempt_no", flat=True)) == [
        1,
        2,
        3,
    ]
    unit.refresh_from_db()
    assert unit.attempts == 3


def _provider_error() -> Exception:
    from vlm.errors import VlmProviderError, VlmProviderFailure

    return VlmProviderError(VlmProviderFailure.SERVER_ERROR)


def test_gate_numbers_attempts_after_existing_and_charges_each_real_send() -> None:
    run = _make_run()
    _run_shards(run)
    unit = VlmUnit.objects.filter(run_id=run.pk).first()
    first = DbBudgetGate(unit)
    assert first.attempts_done == 0
    assert first.try_consume() and first.try_consume()
    assert VlmBudget.objects.get(run_id=run.pk).used_calls == 2
    # Worker chết sau khi gửi attempt 1-2; lần nhận lại tiếp tục từ attempt 3 và tính budget.
    resumed = DbBudgetGate(unit)
    assert resumed.attempts_done == 2
    assert resumed.try_consume()
    assert VlmBudget.objects.get(run_id=run.pk).used_calls == 3
    assert sorted(VlmAttempt.objects.filter(unit=unit).values_list("attempt_no", flat=True)) == [
        1,
        2,
        3,
    ]


def test_worker_dies_after_send_then_reclaim_sends_again_and_is_charged() -> None:
    run = _make_run()
    _run_shards(run)
    unit = VlmUnit.objects.filter(run_id=run.pk).first()
    gate = DbBudgetGate(unit)
    assert gate.try_consume()  # đã gửi attempt 1 rồi worker chết: unit kẹt RUNNING
    VlmUnit.objects.filter(pk=unit.pk).update(
        status="running", started_at=timezone.now() - timedelta(hours=2), lease_token="dead"
    )
    QCRun.objects.filter(pk=run.pk).update(created_at=timezone.now() - timedelta(hours=1))
    redispatch_pending(older_than_seconds=0, running_stale_seconds=60)
    client = FakeClient()
    assert execute_vlm_unit(unit.pk, client=client) == "completed"
    assert client.calls == 1  # provider bị gọi lần hai
    assert VlmBudget.objects.get(run_id=run.pk).used_calls == 2  # và được tính budget
    unit.refresh_from_db()
    assert unit.attempts == 2


def test_reclaim_never_exceeds_max_attempts_per_logical_turn() -> None:
    run = _make_run(vlm={**VALID, "max_attempts": 2})
    _run_shards(run)
    unit = VlmUnit.objects.filter(run_id=run.pk).first()
    gate = DbBudgetGate(unit)
    assert gate.try_consume() and gate.try_consume()  # đã gửi 2/2 rồi chết
    VlmUnit.objects.filter(pk=unit.pk).update(
        status="running", started_at=timezone.now() - timedelta(hours=2), lease_token="dead"
    )
    QCRun.objects.filter(pk=run.pk).update(created_at=timezone.now() - timedelta(hours=1))
    redispatch_pending(older_than_seconds=0, running_stale_seconds=60)
    client = FakeClient()
    assert execute_vlm_unit(unit.pk, client=client) == "failed"
    assert client.calls == 0
    assert VlmBudget.objects.get(run_id=run.pk).used_calls == 2
    unit.refresh_from_db()
    assert unit.reason_code == "provider_error" and unit.attempts == 2


def test_missing_api_key_costs_no_budget_and_makes_no_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VLM_API_KEY")
    monkeypatch.delenv("DASHSCOPE_API_KEY")
    run = _make_run(vlm={**VALID, "budget": {"max_calls": 3}})
    _run_shards(run)
    requests: list[Any] = []
    client = DashScopeClient(
        transport=httpx.MockTransport(lambda r: requests.append(r) or httpx.Response(500))
    )
    for u in VlmUnit.objects.filter(run_id=run.pk):
        assert execute_vlm_unit(u.pk, client=client) == "failed"
    assert requests == []
    assert VlmBudget.objects.get(run_id=run.pk).used_calls == 0
    assert VlmAttempt.objects.count() == 0


def test_candidate_selection_seam_and_created_count(monkeypatch: pytest.MonkeyPatch) -> None:
    import orchestration.vlm_stage as stage

    run = _make_run()
    _run_shards(run)
    assert VlmUnit.objects.filter(run_id=run.pk).count() == 3
    assert stage.EVALUATION_GENERATION == 1
    assert set(VlmUnit.objects.values_list("evaluation_generation", flat=True)) == {1}
    # Policy thay thế qua điểm nối: chỉ chọn một candidate; start trả đúng số unit chèn thật.
    Evaluation.objects.all().delete()  # Evaluation giữ FK PROTECT tới VlmUnit
    VlmUnit.objects.all().delete()
    first = stage.select_candidates_for_vlm(run)[0]
    monkeypatch.setattr(stage, "select_candidates_for_vlm", lambda r: [first])
    assert start_vlm_stage(run.pk) == 1
    assert start_vlm_stage(run.pk) == 0
    assert VlmUnit.objects.filter(run_id=run.pk).count() == 1


def test_budget_exhaustion_stops_provider_calls_and_keeps_run_alive() -> None:
    run = _make_run(vlm={**VALID, "budget": {"max_calls": 2}})
    _run_shards(run)
    client = FakeClient()
    outcomes = [
        execute_vlm_unit(u.pk, client=client)
        for u in VlmUnit.objects.filter(run_id=run.pk).order_by("pk")
    ]
    assert outcomes == ["completed", "completed", "failed"]
    assert client.calls == 2
    assert VlmBudget.objects.get(run_id=run.pk).used_calls == 2
    failed = VlmUnit.objects.get(run_id=run.pk, status="failed")
    assert failed.reason_code == "budget_exhausted" and failed.attempts == 0
    run.refresh_from_db()
    assert run.status == QCRun.Status.COMPLETED
    result = _vlm_result(run)
    assert (result.status, result.completed_units, result.failed_units) == ("partial", 2, 1)


def test_zero_budget_never_calls_provider() -> None:
    """Policy C: budget 0 ⇒ không tạo VlmUnit nào, Evaluation ghi budget_exhausted + cần người xem."""
    run = _make_run(vlm={**VALID, "budget": {"max_calls": 0}})
    _run_shards(run)
    client = FakeClient()
    assert VlmUnit.objects.filter(run_id=run.pk).count() == 0 and client.calls == 0
    rows = Evaluation.objects.filter(run_id=run.pk)
    assert rows.count() == 3
    assert set(rows.values_list("primary_reason", flat=True)) == {"budget_exhausted"}
    assert all(r.human_review_required and not r.call_qwen for r in rows)
    assert _vlm_result(run).status == "not_checked"


def test_budget_is_atomic_under_concurrency() -> None:
    run = _make_run(vlm={**VALID, "budget": {"max_calls": 5}})
    _run_shards(run)
    units = list(VlmUnit.objects.filter(run_id=run.pk))
    extra = [
        VlmUnit.objects.create(
            run_id=run.pk,
            candidate=units[0].candidate,
            evaluation_generation=g,
            idempotency_key=f"k{g}",
            policy_version="p",
            model="m",
            prompt_version="v",
        )
        for g in range(2, 12)
    ]
    results: list[bool] = []
    barrier = threading.Barrier(len(extra))

    def worker(unit: VlmUnit) -> None:
        try:
            barrier.wait()
            results.append(DbBudgetGate(unit).try_consume())
        finally:
            close_old_connections()

    threads = [threading.Thread(target=worker, args=(u,)) for u in extra]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 5 and results.count(False) == 5
    budget = VlmBudget.objects.get(run_id=run.pk)
    assert budget.used_calls == 5
    assert VlmAttempt.objects.filter(unit__in=extra).count() == 5  # attempt bị từ chối rollback


def test_start_stage_is_idempotent() -> None:
    run = _make_run()
    _run_shards(run)
    keys = set(VlmUnit.objects.filter(run_id=run.pk).values_list("idempotency_key", flat=True))
    assert len(keys) == 3
    assert start_vlm_stage(run.pk) == 0
    assert start_vlm_stage(run.pk) == 0
    assert VlmUnit.objects.filter(run_id=run.pk).count() == 3


def test_idempotency_key_components() -> None:
    base = {
        "evaluation_generation": 1,
        "candidate_dedup_key": "c",
        "crop_identity": "x",
        "snapshot_revision": "r",
        "policy_version": "p",
        "model": "m",
        "prompt_version": "v",
    }
    key = compute_vlm_idempotency_key(**base)
    assert key == compute_vlm_idempotency_key(**base) and len(key) == 64
    for field, value in {
        "evaluation_generation": 2,
        "candidate_dedup_key": "c2",
        "crop_identity": "x2",
        "snapshot_revision": "r2",
        "policy_version": "p2",
        "model": "m2",
        "prompt_version": "v2",
    }.items():
        assert compute_vlm_idempotency_key(**{**base, field: value}) != key


def test_cancel_run_cancels_pending_vlm_units() -> None:
    run = _make_run()
    _run_shards(run)
    cancel_qc_run(run_id=run.pk, actor=User.objects.get(username="qa"))
    assert set(VlmUnit.objects.filter(run_id=run.pk).values_list("status", flat=True)) == {
        "cancelled"
    }
    client = FakeClient()
    unit = VlmUnit.objects.filter(run_id=run.pk).first()
    assert execute_vlm_unit(unit.pk, client=client) == "cancelled" and client.calls == 0


def test_no_vlm_model_config_is_no_model_without_stage() -> None:
    run = _make_run(vlm={})
    assert _vlm_result(run).status == "not_checked" and _vlm_result(run).reason == "no_model"
    assert "vlm" not in run.engine_versions
    _run_shards(run)
    assert VlmUnit.objects.count() == 0 and not VlmBudget.objects.exists()
    run.refresh_from_db()
    assert run.status == QCRun.Status.COMPLETED


def test_disabled_vlm_engine_creates_nothing() -> None:
    run = _make_run(vlm_enabled=False)
    assert _vlm_result(run).reason == "disabled"
    _run_shards(run)
    assert VlmUnit.objects.count() == 0
    run.refresh_from_db()
    assert run.status == QCRun.Status.COMPLETED


def test_missing_taxonomy_skips_stage_as_not_applicable() -> None:
    run = _make_run(with_taxonomy=False)
    _run_shards(run)
    assert VlmUnit.objects.count() == 0
    assert VlmBudget.objects.get(run_id=run.pk).skipped_reason == "not_applicable"
    result = _vlm_result(run)
    assert (result.status, result.reason) == ("not_checked", "not_applicable")
    run.refresh_from_db()
    assert run.status == QCRun.Status.COMPLETED


def test_no_candidates_means_not_triggered() -> None:
    run = _make_run()

    # engine không sinh candidate nào
    def empty(inp: EngineInput) -> EngineOutput:
        return EngineOutput(
            inp.idempotency_key,
            inp.engine,
            inp.engine_version,
            (),
            tuple(EngineUnitResult(u, "completed", 1) for u in inp.units),
        )

    registry.runner = lambda name, version: empty  # type: ignore[method-assign]
    _run_shards(run)
    result = _vlm_result(run)
    assert (result.status, result.reason) == ("not_checked", "not_triggered")
    run.refresh_from_db()
    assert run.status == QCRun.Status.COMPLETED


def test_invalid_crop_fails_unit_without_provider_call(settings: Any) -> None:
    settings.VLM_CROP_PROVIDER = "tests.orchestration.test_vlm_stage.BrokenCrops"
    run = _make_run()
    _run_shards(run)
    client = FakeClient()
    unit = VlmUnit.objects.filter(run_id=run.pk).first()
    assert execute_vlm_unit(unit.pk, client=client) == "failed"
    unit.refresh_from_db()
    assert unit.reason_code == "invalid_crop" and client.calls == 0
    assert VlmBudget.objects.get(run_id=run.pk).used_calls == 0


def test_default_provider_without_crop_source_fails_visibly(settings: Any) -> None:
    del settings.VLM_CROP_PROVIDER
    run = _make_run()
    _run_shards(run)
    client = FakeClient()
    for u in VlmUnit.objects.filter(run_id=run.pk):
        assert execute_vlm_unit(u.pk, client=client) == "failed"
    assert client.calls == 0
    assert set(VlmUnit.objects.values_list("reason_code", flat=True)) == {"invalid_crop"}


def test_stale_running_vlm_unit_is_reclaimed_by_sweeper() -> None:
    run = _make_run()
    _run_shards(run)
    unit = VlmUnit.objects.filter(run_id=run.pk).first()
    VlmUnit.objects.filter(pk=unit.pk).update(
        status="running", started_at=timezone.now() - timedelta(hours=2), lease_token="old"
    )
    QCRun.objects.filter(pk=run.pk).update(created_at=timezone.now() - timedelta(hours=1))
    redispatch_pending(older_than_seconds=0, running_stale_seconds=60)
    unit.refresh_from_db()
    assert unit.status == "pending" and unit.dispatched_at is not None
    assert execute_vlm_unit(unit.pk, client=FakeClient()) == "completed"


def test_fresh_running_unit_is_not_run_twice() -> None:
    run = _make_run()
    _run_shards(run)
    unit = VlmUnit.objects.filter(run_id=run.pk).first()
    VlmUnit.objects.filter(pk=unit.pk).update(
        status="running", started_at=timezone.now(), lease_token="owner"
    )
    client = FakeClient()
    assert execute_vlm_unit(unit.pk, client=client) == "running" and client.calls == 0


def test_uncertain_and_parse_failure_flow_through_real_client(monkeypatch: Any) -> None:
    run = _make_run()
    _run_shards(run)
    units = list(VlmUnit.objects.filter(run_id=run.pk).order_by("pk"))
    bodies = iter(["uncertain", "garbage", "1"])

    def handler(request: httpx.Request) -> httpx.Response:
        text = next(bodies)
        content = json.dumps({"label": text}) if text != "garbage" else "không phải json"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = DashScopeClient(transport=httpx.MockTransport(handler))
    assert [execute_vlm_unit(u.pk, client=client) for u in units] == [
        "completed",
        "failed",
        "completed",
    ]
    reasons = list(
        VlmUnit.objects.filter(run_id=run.pk).order_by("pk").values_list("reason_code", "result")
    )
    assert reasons[1][0] == "parse_failure"
    assert reasons[0][1]["status"] == "uncertain" and reasons[0][1]["label"] is None
    assert "sk-test-not-real" not in json.dumps([r[1] for r in reasons])
