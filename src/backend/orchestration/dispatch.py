"""Nối orchestrator với QCRun/WorkUnit của T-024: dựng input, chạy shard, cập nhật trạng thái."""

from __future__ import annotations

import re
from typing import Any

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from engines.interface import EngineConfig, EngineInput, EngineUnitRef, FrameKey
from orchestration.models import ShardCommit
from orchestration.runsync import mark_run_running, refresh_run
from orchestration.services import engine_input_to_payload, seed_ledger
from orchestration.tasks import run_engine_shard
from runs.models import QCRun, WorkUnit
from snapshots.models import SnapshotFrame

_FRAMES = re.compile(r"^job:(?P<job>\d+):frames:(?P<start>\d+)-(?P<end>\d+)$")


def shard_units(work_unit: WorkUnit) -> tuple[EngineUnitRef, ...]:
    """Đơn vị frame của shard theo shard_key (`job:<id>:frames:<a>-<b>`); shard rỗng -> không có."""
    match = _FRAMES.match(work_unit.shard_key)
    if match is None:
        return ()
    frames = SnapshotFrame.objects.filter(
        snapshot_job__snapshot_id=work_unit.run.snapshot_id,
        snapshot_job__cvat_job_id=int(match["job"]),
        frame_index__gte=int(match["start"]),
        frame_index__lte=int(match["end"]),
    ).select_related("snapshot_job")
    return tuple(
        EngineUnitRef("frame", FrameKey(f.snapshot_job.cvat_task_id, f.frame_index))
        for f in frames.order_by("frame_index")
    )


def build_engine_input(work_unit: WorkUnit) -> EngineInput:
    run = work_unit.run
    engine = work_unit.engine
    cfg = run.config_version
    engines = cfg.engines or (cfg.payload or {}).get("engines", {})
    raw = engines.get(engine, {}) if isinstance(engines, dict) else {}
    params = raw.get("params", {}) if isinstance(raw, dict) else {}
    version = run.engine_versions[engine]
    return EngineInput(
        idempotency_key=work_unit.idempotency_key,
        run_id=run.pk,
        snapshot_id=run.snapshot_id,
        engine=engine,
        engine_version=version,
        config=EngineConfig(engine, str(cfg.pk), True, params),
        seed=run.seed,
        shard_index=work_unit.shard_index,
        units=shard_units(work_unit),
    )


def prepare_work_unit(work_unit: WorkUnit) -> dict[str, Any]:
    """Seed ledger (idempotent) và trả payload Celery của shard."""
    engine_input = build_engine_input(work_unit)
    seed_ledger(engine_input.run_id, engine_input.engine, engine_input.units)
    return engine_input_to_payload(engine_input)


@shared_task(name="orchestration.run_work_unit", acks_late=True, reject_on_worker_lost=True)
def run_work_unit(work_unit_id: int) -> str:
    """Chạy một WorkUnit; idempotent: unit đã commit hoặc run đã huỷ thì không làm gì."""
    with transaction.atomic():
        unit = (
            WorkUnit.objects.select_for_update()
            .select_related("run", "run__config_version")
            .get(pk=work_unit_id)
        )
        if unit.run.cancel_requested_at or unit.status in (
            WorkUnit.Status.CANCELLED,
            WorkUnit.Status.COMPLETED,
        ):
            return unit.status
        unit.status = WorkUnit.Status.RUNNING
        unit.started_at = unit.started_at or timezone.now()
        unit.save(update_fields=["status", "started_at"])
        mark_run_running(unit.run_id)
    payload = prepare_work_unit(unit)
    try:
        run_engine_shard.apply(args=(payload,)).get(propagate=True)
    except Exception as exc:
        WorkUnit.objects.filter(pk=unit.pk).update(
            status=WorkUnit.Status.FAILED, last_error=str(exc)[:1000], finished_at=timezone.now()
        )
        refresh_run(unit.run_id)
        raise
    WorkUnit.objects.filter(pk=unit.pk).update(
        status=WorkUnit.Status.COMPLETED, last_error="", finished_at=timezone.now()
    )
    refresh_run(unit.run_id)
    return WorkUnit.Status.COMPLETED


def dispatch_run(run_id: int) -> int:
    """Xếp mọi WorkUnit pending của run vào queue. Gọi lại an toàn (task idempotent)."""
    run = QCRun.objects.get(pk=run_id)
    pending = list(run.work_units.filter(status=WorkUnit.Status.PENDING).select_related("run"))
    for unit in pending:  # chốt mẫu số ledger của cả run trước khi shard đầu tiên chạy
        prepare_work_unit(unit)
    for unit in pending:
        run_work_unit.delay(unit.pk)
    return len(pending)


def committed_shards(run_id: int) -> int:
    return ShardCommit.objects.filter(run_id=run_id).count()
