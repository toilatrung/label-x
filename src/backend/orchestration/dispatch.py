"""Nối orchestrator với QCRun/WorkUnit của T-024: dựng input, chạy shard, cập nhật trạng thái."""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Any

from celery import shared_task
from celery.exceptions import Retry
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from engines.interface import EngineConfig, EngineInput, EngineUnitRef, FrameKey
from orchestration.models import ShardCommit
from orchestration.retry import default_policy
from orchestration.runsync import mark_run_running, refresh_run
from orchestration.services import (
    ShardOutputError,
    engine_input_to_payload,
    mark_shard_failed,
    seed_ledger,
)
from orchestration.tasks import execute_shard
from runs.models import QCRun, WorkUnit
from snapshots.models import SnapshotFrame

logger = logging.getLogger("labelx.orchestration")
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
    units = shard_units(work_unit)
    if not units and _FRAMES.match(work_unit.shard_key):
        # Shard khai báo frame mà snapshot không có: không được "pass" im lặng.
        raise ValueError(f"shard {work_unit.shard_key} không có frame trong snapshot")
    return EngineInput(
        idempotency_key=work_unit.idempotency_key,
        run_id=run.pk,
        snapshot_id=run.snapshot_id,
        engine=engine,
        engine_version=version,
        config=EngineConfig(engine, str(cfg.pk), True, params),
        seed=run.seed,
        shard_index=work_unit.shard_index,
        units=units,
    )


def prepare_work_unit(work_unit: WorkUnit) -> dict[str, Any]:
    """Seed ledger (idempotent) và trả payload Celery của shard."""
    engine_input = build_engine_input(work_unit)
    seed_ledger(engine_input.run_id, engine_input.engine, engine_input.units)
    return engine_input_to_payload(engine_input)


_PERMANENT_ERRORS = (ShardOutputError, LookupError, ValueError)
_ACTIVE_RUN = (QCRun.Status.QUEUED, QCRun.Status.RUNNING)


def _finish_unit(unit_id: int, status: str, error: str = "") -> bool:
    """Chốt WorkUnit chỉ khi còn RUNNING: unit đã CANCELLED (cancel_qc_run) không bị ghi đè."""
    return bool(
        WorkUnit.objects.filter(pk=unit_id, status=WorkUnit.Status.RUNNING).update(
            status=status, last_error=error[:1000], finished_at=timezone.now()
        )
    )


@shared_task(
    bind=True,
    name="orchestration.run_work_unit",
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_work_unit(self: Any, work_unit_id: int) -> str:
    """Chạy một WorkUnit; idempotent: unit đã commit hoặc run đã huỷ thì không làm gì.

    Lỗi tạm thời -> `self.retry` thật (broker giữ countdown 2/4/8s theo policy, tối đa
    `max_retries`); lỗi cố định hoặc hết retry -> unit FAILED. Worker chết giữa chừng thì
    broker giao lại (acks_late): ShardCommit đảm bảo shard chỉ ghi một lần.
    """
    with transaction.atomic():
        unit = (
            WorkUnit.objects.select_for_update(
                of=("self",)
            )  # không khoá run: tránh đảo thứ tự với cancel
            .select_related("run", "run__config_version")
            .get(pk=work_unit_id)
        )
        if (
            unit.run.cancel_requested_at
            or unit.run.status not in _ACTIVE_RUN
            or unit.status in (WorkUnit.Status.CANCELLED, WorkUnit.Status.COMPLETED)
        ):
            return unit.status
        unit.status = WorkUnit.Status.RUNNING
        unit.started_at = timezone.now()  # lease: mỗi lần nhận shard làm mới, sweeper dựa vào đây
        unit.save(update_fields=["status", "started_at"])
        mark_run_running(unit.run_id)
    policy = default_policy()
    engine_input: EngineInput | None = None
    try:
        engine_input = build_engine_input(unit)
        seed_ledger(engine_input.run_id, engine_input.engine, engine_input.units)
        execute_shard(engine_input)
    except Exception as exc:
        permanent = isinstance(exc, _PERMANENT_ERRORS)
        if permanent or policy.exhausted(self.request.retries):
            if engine_input is not None:
                mark_shard_failed(engine_input, attempts=self.request.retries + 1)
            _finish_unit(unit.pk, WorkUnit.Status.FAILED, str(exc))
            refresh_run(unit.run_id)
            raise
        try:
            self.retry(
                exc=exc,
                countdown=policy.backoff(self.request.retries + 1),
                max_retries=policy.max_retries,
            )
        except Retry:
            raise
        except Exception:
            # Không gửi được message retry: trả unit về PENDING để lệnh/task redispatch nhặt lại.
            WorkUnit.objects.filter(pk=unit.pk, status=WorkUnit.Status.RUNNING).update(
                status=WorkUnit.Status.PENDING
            )
            raise
    _finish_unit(unit.pk, WorkUnit.Status.COMPLETED)
    refresh_run(unit.run_id)
    unit.refresh_from_db(fields=["status"])
    return unit.status


def dispatch_run(run_id: int, stale_after: float | None = None) -> int:
    """Xếp WorkUnit pending của run vào queue. Gọi lại an toàn (task idempotent).

    `stale_after` (giây): chỉ gửi lại unit chưa từng gửi hoặc gửi đã quá hạn, tránh nhân message
    khi queue đang backlog (sweeper). Không truyền thì gửi mọi unit pending (dispatch đầu tiên).

    Run đã huỷ/terminal thì bỏ qua. Lỗi gửi broker của một unit không làm hỏng unit khác:
    unit đó vẫn PENDING để `redispatch_pending` nhặt lại. Trả số unit đã xếp hàng được.
    """
    run = QCRun.objects.get(pk=run_id)
    if run.cancel_requested_at or run.status not in _ACTIVE_RUN:
        return 0
    pending_qs = run.work_units.filter(status=WorkUnit.Status.PENDING)
    if stale_after is not None:
        cutoff = timezone.now() - timedelta(seconds=stale_after)
        pending_qs = pending_qs.filter(Q(dispatched_at__isnull=True) | Q(dispatched_at__lte=cutoff))
    pending = list(pending_qs.select_related("run"))
    if not pending and not run.work_units.filter(status=WorkUnit.Status.RUNNING).exists():
        refresh_run(run_id)  # run không có shard (engine tắt/thiếu model) hoặc kẹt sau unit cuối
        return 0
    for unit in pending:  # chốt mẫu số ledger của cả run trước khi shard đầu tiên chạy
        prepare_work_unit(unit)
    queued = 0
    for unit in pending:
        try:
            run_work_unit.delay(unit.pk)
        except Exception:
            logger.exception(
                "dispatch failed", extra={"qc_run_id": run_id, "work_unit_id": unit.pk}
            )
        else:
            queued += 1
            WorkUnit.objects.filter(pk=unit.pk).update(dispatched_at=timezone.now())
    return queued


def dispatch_run_safely(run_id: int, stale_after: float | None = None) -> int:
    """Dùng trong transaction.on_commit: không bao giờ ném lỗi sau khi run đã commit."""
    try:
        return dispatch_run(run_id, stale_after)
    except Exception:
        logger.exception("dispatch failed", extra={"qc_run_id": run_id})
        return 0


def redispatch_pending(
    older_than_seconds: float | None = None, running_stale_seconds: float | None = None
) -> dict[str, int]:
    """Xếp lại shard PENDING của run QUEUED/RUNNING đã quá tuổi (broker mất message/gửi lỗi).

    Không đụng run đã huỷ. Idempotent: ledger seed ignore_conflicts, ShardCommit chặn ghi đôi.
    Unit PENDING chỉ được gửi lại nếu lần gửi trước đã quá `older_than_seconds` (không nhân
    message khi backlog). Unit RUNNING chỉ bị thu hồi khi lease (`started_at`, làm mới mỗi lần
    worker nhận) quá `running_stale_seconds` — phải lớn hơn thời gian chạy tối đa của một shard.
    Lưu ý: message gửi lại bắt đầu với retries=0 nên ngân sách retry tính lại theo từng lần gửi.
    """
    if older_than_seconds is None:
        older_than_seconds = getattr(settings, "ORCHESTRATION_REDISPATCH_AFTER_SECONDS", 300)
    if running_stale_seconds is None:
        running_stale_seconds = getattr(settings, "ORCHESTRATION_RUNNING_STALE_SECONDS", 1800)
    cutoff = timezone.now() - timedelta(seconds=older_than_seconds)
    running_cutoff = timezone.now() - timedelta(seconds=running_stale_seconds)
    # Shard RUNNING bỏ rơi (worker chết/mất message): đưa về PENDING để xếp lại. An toàn vì task
    # idempotent (ShardCommit chặn ghi đôi); unit đang chạy thật chưa quá hạn nên không bị đụng.
    WorkUnit.objects.filter(
        status=WorkUnit.Status.RUNNING,
        started_at__lte=running_cutoff,
        run__status__in=_ACTIVE_RUN,
        run__cancel_requested_at__isnull=True,
    ).update(status=WorkUnit.Status.PENDING)
    run_ids = list(
        QCRun.objects.filter(
            status__in=_ACTIVE_RUN, cancel_requested_at__isnull=True, created_at__lte=cutoff
        ).values_list("pk", flat=True)
    )
    return {
        "runs": len(run_ids),
        "queued": sum(dispatch_run_safely(pk, older_than_seconds) for pk in run_ids),
    }


@shared_task(name="orchestration.redispatch_pending")
def redispatch_pending_task() -> dict[str, int]:
    return redispatch_pending()


def committed_shards(run_id: int) -> int:
    return ShardCommit.objects.filter(run_id=run_id).count()
