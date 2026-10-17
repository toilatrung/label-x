"""Nối orchestrator với QCRun/WorkUnit của T-024: dựng input, chạy shard, cập nhật trạng thái."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import timedelta
from typing import Any

from celery import shared_task
from celery.exceptions import Retry
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from engines.interface import EngineConfig, EngineInput, EngineUnitRef, FrameKey
from orchestration.fail_fast import enabled as fail_fast_enabled
from orchestration.fail_fast import stop_failed_engines
from orchestration.models import ShardCommit, VlmUnit
from orchestration.resources import ResourceWaiting, retry_delay
from orchestration.retry import default_policy
from orchestration.runsync import refresh_run
from orchestration.services import (
    ShardOutputError,
    StaleLeaseError,
    engine_input_to_payload,
    mark_shard_failed,
    seed_ledger,
)
from orchestration.tasks import execute_shard
from orchestration.vlm_stage import dispatch_vlm_units_safely
from runs.gpu_worker import WorkerUnavailable
from runs.models import QCRun, WorkUnit
from snapshots.models import SnapshotFrame

logger = logging.getLogger("labelx.orchestration")
_FRAMES = re.compile(r"^job:(?P<job>\d+):frames:(?P<start>\d+)-(?P<end>\d+)(?::retry:\d+)?$")


def shard_units(work_unit: WorkUnit) -> tuple[EngineUnitRef, ...]:
    """Đơn vị frame của shard theo shard_key (`job:<id>:frames:<a>-<b>`); shard rỗng -> không có."""
    match = _FRAMES.match(work_unit.shard_key)
    if match is None:
        return ()
    # Chỉ lấy khoá frame: tải cả cột JSON (shapes/media) làm mỗi shard mất ~4 s (đo thật trên 588
    # frame), nhân với số shard trong request tạo run.
    frames = (
        SnapshotFrame.objects.filter(
            snapshot_job__snapshot_id=work_unit.run.snapshot_id,
            snapshot_job__cvat_job_id=int(match["job"]),
            frame_index__gte=int(match["start"]),
            frame_index__lte=int(match["end"]),
        )
        .order_by("frame_index")
        .values_list("snapshot_job__cvat_task_id", "frame_index")
    )
    return tuple(EngineUnitRef("frame", FrameKey(task_id, index)) for task_id, index in frames)


def build_engine_input(work_unit: WorkUnit) -> EngineInput:
    run = work_unit.run
    engine = work_unit.engine
    cfg = run.config_version
    engines = cfg.engines or (cfg.payload or {}).get("engines", {})
    raw = engines.get(engine, {}) if isinstance(engines, dict) else {}
    params = raw.get("params", {}) if isinstance(raw, dict) else {}
    if engine == "metric" and run.metric_reference_id:
        params = {**params, "reference_id": run.metric_reference_id}
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
    if work_unit.engine == "detector" and work_unit.deadline_at is None:
        work_unit.deadline_at = timezone.now() + timedelta(
            seconds=getattr(settings, "ENGINE_WAIT_TIMEOUT_SECONDS", 1800)
        )
        WorkUnit.objects.filter(pk=work_unit.pk, deadline_at__isnull=True).update(
            deadline_at=work_unit.deadline_at
        )
    engine_input = build_engine_input(work_unit)
    seed_ledger(engine_input.run_id, engine_input.engine, engine_input.units)
    return engine_input_to_payload(engine_input)


_PERMANENT_ERRORS = (ShardOutputError, LookupError, ValueError)
_ACTIVE_RUN = (QCRun.Status.QUEUED, QCRun.Status.RUNNING)


def _finish_unit(unit_id: int, token: str, status: str, error: str = "") -> bool:
    """Chốt WorkUnit chỉ khi còn RUNNING **và** còn là chủ lease: unit đã CANCELLED, hoặc đã bị
    worker khác nhận lại (lease đổi), thì lần chốt này là no-op (trả False)."""
    return bool(
        WorkUnit.objects.filter(
            pk=unit_id, status=WorkUnit.Status.RUNNING, lease_token=token
        ).update(status=status, last_error=error[:1000], finished_at=timezone.now())
    )


def _running_stale_seconds() -> float:
    return float(getattr(settings, "ORCHESTRATION_RUNNING_STALE_SECONDS", 1800))


def _claim(work_unit_id: int, presented_token: str | None) -> tuple[WorkUnit | None, str, str]:
    """Nhận lease của shard. Trả (unit, token, status_hiện_tại); unit=None nếu không được chạy.

    Thứ tự khoá cố định **QCRun -> WorkUnit** (giống cancel_qc_run) để không deadlock với huỷ.
    Một owner duy nhất chạy shard: delivery trùng khi lease còn hạn bị bỏ qua; retry hợp lệ của
    chính owner (mang `lease_token`) và shard bị bỏ rơi (lease quá hạn) thì được nhận.
    """
    run_id = WorkUnit.objects.filter(pk=work_unit_id).values_list("run_id", flat=True).first()
    if run_id is None:
        return None, "", "missing"
    with transaction.atomic():
        run = QCRun.objects.select_for_update().select_related("config_version").get(pk=run_id)
        stop_failed_engines(run)
        unit = WorkUnit.objects.select_for_update().get(pk=work_unit_id)
        unit.run = run
        if run.retry_engine and unit.engine != run.retry_engine:
            return None, "", unit.status
        if (
            run.cancel_requested_at
            or run.status not in _ACTIVE_RUN
            or unit.status
            in (WorkUnit.Status.CANCELLED, WorkUnit.Status.COMPLETED, WorkUnit.Status.FAILED)
        ):
            return None, "", unit.status
        now = timezone.now()
        if unit.retry_at and unit.retry_at > now:
            return None, "", "waiting_retry"
        if unit.engine == "detector" and unit.deadline_at is None:
            unit.deadline_at = now + timedelta(
                seconds=getattr(settings, "ENGINE_WAIT_TIMEOUT_SECONDS", 1800)
            )
            unit.save(update_fields=["deadline_at"])
        token = uuid.uuid4().hex  # mỗi lần nhận: token mới; token cũ (kể cả của retry) hết hiệu lực
        if unit.status == WorkUnit.Status.RUNNING:
            fresh = unit.started_at is not None and unit.started_at > now - timedelta(
                seconds=_running_stale_seconds()
            )
            retry_ticket = bool(presented_token) and presented_token == unit.lease_token
            if fresh and not retry_ticket:
                return None, "", "running"  # delivery trùng: đã có owner đang chạy
        unit.status = WorkUnit.Status.RUNNING
        unit.retry_at = None
        unit.started_at = now  # lease: làm mới mỗi lần nhận, sweeper dựa vào đây
        unit.lease_token = token
        unit.save(update_fields=["status", "started_at", "lease_token", "retry_at"])
        if run.status == QCRun.Status.QUEUED:  # run đã khoá ở trên: cập nhật an toàn
            run.status = QCRun.Status.RUNNING
            run.started_at = now
            run.save(update_fields=["status", "started_at"])
        return unit, token, WorkUnit.Status.RUNNING


def _settle(
    unit: WorkUnit,
    token: str,
    status: str,
    error: str = "",
    engine_input: EngineInput | None = None,
    attempts: int = 1,
) -> bool:
    """Chốt shard + (nếu lỗi) ledger trong một transaction, khoá QCRun trước (cùng thứ tự với
    claim/cancel/commit). Chỉ chủ lease mới chốt được; không phải chủ thì không đụng gì."""
    with transaction.atomic():
        QCRun.objects.select_for_update().only("id").get(pk=unit.run_id)
        finished = _finish_unit(unit.pk, token, status, error)
        if not finished and status == WorkUnit.Status.COMPLETED:
            # commit_shard_output (fencing) đã chốt COMPLETED trong cùng transaction ghi kết quả.
            finished = WorkUnit.objects.filter(
                pk=unit.pk, status=WorkUnit.Status.COMPLETED, lease_token=token
            ).exists()
        if not finished:
            return False
        if status == WorkUnit.Status.FAILED and engine_input is not None:
            mark_shard_failed(engine_input, attempts=attempts)
    refresh_run(unit.run_id)
    return True


@shared_task(
    bind=True,
    name="orchestration.run_work_unit",
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_work_unit(self: Any, work_unit_id: int, lease_token: str | None = None) -> str:
    """Chạy một WorkUnit; idempotent: unit đã commit/huỷ/đang có owner thì bỏ qua.

    - Một owner duy nhất chạy shard (lease). Lỗi tạm thời -> `self.retry` thật (2/4/8s, tối đa
      `max_retries`) kèm vé `lease_token` dùng một lần: nhận retry đổi token nên bản sao của
      cùng retry bị bỏ qua.
    - Lỗi cố định hoặc hết retry -> unit FAILED (chỉ chủ lease chốt được).
    - Worker chết: broker giao lại (acks_late) hoặc sweeper thu hồi lease quá hạn.
    - Ghi kết quả có fencing token trong chính transaction ghi (worker cũ bị thu hồi không ghi
      được); ShardCommit unique chặn ghi trùng.
    """
    unit, token, current = _claim(work_unit_id, lease_token)
    if unit is None:
        if current in (WorkUnit.Status.COMPLETED, WorkUnit.Status.FAILED):
            # Worker có thể chết sau khi commit nhưng trước khi chốt run: giao lại thì chốt nốt.
            run_id = WorkUnit.objects.filter(pk=work_unit_id).values_list("run_id", flat=True)[0]
            refresh_run(run_id)
        return current
    policy = default_policy()
    engine_input: EngineInput | None = None
    try:
        engine_input = build_engine_input(unit)
        seed_ledger(engine_input.run_id, engine_input.engine, engine_input.units)
        if unit.engine == "detector":
            if unit.deadline_at and timezone.now() >= unit.deadline_at:
                raise WorkerUnavailable("Đã hết thời hạn xử lý Detector.", code="deadline_exceeded")
        execute_shard(engine_input, fence=(unit.pk, token))
    except (ResourceWaiting, WorkerUnavailable) as exc:
        if unit.engine != "detector":
            _settle(unit, token, WorkUnit.Status.FAILED, str(exc), engine_input)
            raise
        waiting = isinstance(exc, ResourceWaiting)
        calls = unit.request_attempts + int(
            not waiting and getattr(exc, "code", "") not in ("worker_busy", "deadline_exceeded")
        )
        retryable = isinstance(exc, ResourceWaiting) or exc.retryable
        deadline = unit.deadline_at or timezone.now()
        delay = (
            exc.seconds
            if isinstance(exc, ResourceWaiting)
            else max(exc.retry_after, policy.backoff(max(1, calls)))
        )
        delay = retry_delay(delay)
        error_code = exc.code
        if (
            not retryable
            or calls > policy.max_retries
            or timezone.now() + timedelta(seconds=delay) >= deadline
        ):
            WorkUnit.objects.filter(pk=unit.pk, lease_token=token).update(
                request_attempts=calls, error_code=error_code, retry_at=None
            )
            _settle(
                unit, token, WorkUnit.Status.FAILED, str(exc), engine_input, attempts=max(1, calls)
            )
            return WorkUnit.Status.FAILED
        retry_at = timezone.now() + timedelta(seconds=delay)
        updated = WorkUnit.objects.filter(
            pk=unit.pk, status=WorkUnit.Status.RUNNING, lease_token=token
        ).update(
            status=WorkUnit.Status.PENDING,
            lease_token="",
            retry_at=retry_at,
            error_code=error_code,
            last_error=str(exc)[:1000],
            request_attempts=calls,
        )
        if updated:
            logger.info(
                "detector retry scheduled",
                extra={
                    "qc_run_id": unit.run_id,
                    "work_unit_id": unit.pk,
                    "error_code": error_code,
                    "retry_at": retry_at.isoformat(),
                    "attempts": calls,
                },
            )
            if getattr(settings, "ORCHESTRATION_AUTO_DISPATCH", True):
                try:
                    run_work_unit.apply_async(args=(unit.pk,), countdown=delay)
                except Exception:
                    logger.exception(
                        "detector retry publish failed", extra={"qc_run_id": unit.run_id}
                    )
        return "waiting_retry"
    except StaleLeaseError:
        return "stale"  # đã bị thu hồi: không ghi gì, không chốt, không retry
    except Exception as exc:
        permanent = isinstance(exc, _PERMANENT_ERRORS)
        if fail_fast_enabled() or permanent or policy.exhausted(self.request.retries):
            _settle(
                unit,
                token,
                WorkUnit.Status.FAILED,
                str(exc),
                engine_input,
                attempts=self.request.retries + 1,
            )
            raise
        ticket = uuid.uuid4().hex  # vé retry dùng một lần: nhận retry sẽ đổi token (xem _claim)
        if not WorkUnit.objects.filter(
            pk=unit.pk, status=WorkUnit.Status.RUNNING, lease_token=token
        ).update(lease_token=ticket):
            raise  # không còn là chủ lease: không lên lịch retry
        try:
            self.retry(
                exc=exc,
                kwargs={"lease_token": ticket},
                countdown=policy.backoff(self.request.retries + 1),
                max_retries=policy.max_retries,
            )
        except Retry:
            raise
        except Exception:
            # Không gửi được message retry: trả unit về PENDING (chỉ khi còn là chủ lease) để
            # lệnh/task redispatch nhặt lại.
            WorkUnit.objects.filter(
                pk=unit.pk, status=WorkUnit.Status.RUNNING, lease_token=ticket
            ).update(status=WorkUnit.Status.PENDING)
            raise
    if unit.engine == "detector":
        WorkUnit.objects.filter(pk=unit.pk, lease_token=token).update(
            request_attempts=unit.request_attempts + 1, retry_at=None, error_code="", last_error=""
        )
    _settle(unit, token, WorkUnit.Status.COMPLETED)
    unit.refresh_from_db(fields=["status"])
    return unit.status


def dispatch_run(run_id: int, stale_after: float | None = None) -> int:
    """Xếp WorkUnit pending của run vào queue. Gọi lại an toàn (task idempotent).

    `stale_after` (giây): chỉ gửi lại unit chưa từng gửi hoặc gửi đã quá hạn, tránh nhân message
    khi queue đang backlog (sweeper). Không truyền thì gửi mọi unit pending (dispatch đầu tiên).

    Run đã huỷ/terminal thì bỏ qua. Lỗi gửi broker của một unit không làm hỏng unit khác:
    unit đó vẫn PENDING để `redispatch_pending` nhặt lại. Trả số unit đã xếp hàng được.
    """
    refresh_run(run_id)
    run = QCRun.objects.get(pk=run_id)
    if run.cancel_requested_at or run.status not in _ACTIVE_RUN:
        return 0
    pending_qs = run.work_units.filter(status=WorkUnit.Status.PENDING).filter(
        Q(retry_at__isnull=True) | Q(retry_at__lte=timezone.now())
    )
    if run.retry_engine:
        pending_qs = pending_qs.filter(engine=run.retry_engine)
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
            # Broker không với tới được: dừng sớm, không đợi timeout cho từng shard (đo thật:
            # 18 shard x ~3 s làm POST /api/runs/ mất ~55 s). Phần còn lại giữ PENDING cho sweeper.
            break
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
    from runs.ground_truth import cleanup_finished_uploads

    cleanup_finished_uploads()
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
    VlmUnit.objects.filter(
        status=VlmUnit.Status.RUNNING,
        started_at__lte=running_cutoff,
        run__status__in=_ACTIVE_RUN,
        run__cancel_requested_at__isnull=True,
    ).update(status=VlmUnit.Status.PENDING)
    # Re-evaluate thủ công (generation > 1) chạy cả sau khi run kết thúc: cũng thu hồi lease cũ.
    VlmUnit.objects.filter(
        status=VlmUnit.Status.RUNNING,
        started_at__lte=running_cutoff,
        evaluation_generation__gt=1,
        run__cancel_requested_at__isnull=True,
    ).update(status=VlmUnit.Status.PENDING)
    run_ids = list(
        QCRun.objects.filter(
            status__in=_ACTIVE_RUN, cancel_requested_at__isnull=True, created_at__lte=cutoff
        ).values_list("pk", flat=True)
    )
    manual_run_ids = list(
        VlmUnit.objects.filter(
            status=VlmUnit.Status.PENDING,
            evaluation_generation__gt=1,
            run__cancel_requested_at__isnull=True,
        )
        .exclude(run_id__in=run_ids)
        .values_list("run_id", flat=True)
        .distinct()
    )
    return {
        "runs": len(run_ids),
        "queued": sum(
            dispatch_run_safely(pk, older_than_seconds)
            + dispatch_vlm_units_safely(pk, older_than_seconds)
            for pk in run_ids
        )
        + sum(dispatch_vlm_units_safely(pk, older_than_seconds) for pk in manual_run_ids),
    }


@shared_task(name="orchestration.redispatch_pending")
def redispatch_pending_task() -> dict[str, int]:
    return redispatch_pending()


def committed_shards(run_id: int) -> int:
    return ShardCommit.objects.filter(run_id=run_id).count()
