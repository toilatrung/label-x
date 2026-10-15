"""Đồng bộ EngineResult và trạng thái QCRun từ ledger/WorkUnit sau mỗi shard (FR-AGG-04/05)."""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from engines.interface import EngineStatus, NotCheckedReason, public_status
from orchestration.fail_fast import enabled as fail_fast_enabled
from orchestration.fail_fast import stop_failed_engines
from orchestration.models import VlmBudget, VlmUnit
from orchestration.services import ledger_counts, vlm_ledger_counts
from orchestration.vlm_stage import (
    VLM_ENGINE,
    start_vlm_stage,
    vlm_stage_started,
    vlm_units_open,
)
from runs.models import EngineResult, QCRun, WorkUnit
from runs.ranking import persist_terminal_run_rankings

logger = logging.getLogger("labelx.orchestration")
_OPEN = (WorkUnit.Status.PENDING, WorkUnit.Status.RUNNING)


def mark_run_running(run_id: int) -> None:
    QCRun.objects.filter(pk=run_id, status=QCRun.Status.QUEUED).update(
        status=QCRun.Status.RUNNING, started_at=timezone.now()
    )


def refresh_run(run_id: int) -> None:
    """Tính lại EngineResult theo ledger (mẫu số theo frame); chốt trạng thái run khi hết shard."""
    with transaction.atomic():
        run = QCRun.objects.select_for_update().get(pk=run_id)
        stop_failed_engines(run)
        units = list(run.work_units.all())
        units_open = any(u.status in _OPEN for u in units)
        if (
            not units_open
            and VLM_ENGINE in (run.engine_versions or {})
            and not run.cancel_requested_at
        ):
            # Candidate đã sinh xong: khởi động/bổ sung stage VLM (idempotent, trong khoá run).
            start_vlm_stage(run_id)
        for result in run.engine_results.all():
            if result.engine == VLM_ENGINE:
                _refresh_vlm_result(run_id, result)
                continue
            ledger = ledger_counts(run_id, result.engine)
            if ledger.total == 0:
                if any(
                    u.engine == result.engine and u.status == WorkUnit.Status.FAILED for u in units
                ):
                    result.status = EngineStatus.FAILED.value
                    result.save(update_fields=["status"])
                continue
            finished = not any(u.engine == result.engine and u.status in _OPEN for u in units)
            result.status = public_status(ledger, finished=finished).value
            reasons = ledger.not_checked_reasons
            result.reason = (
                max(sorted(reasons), key=lambda r: reasons[r]).value if reasons else None
            )
            result.eligible_units = ledger.eligible
            result.completed_units = ledger.completed
            result.failed_units = ledger.failed
            result.not_checked_units = ledger.not_checked
            result.save(
                update_fields=[
                    "status",
                    "reason",
                    "eligible_units",
                    "completed_units",
                    "failed_units",
                    "not_checked_units",
                ]
            )
        logger.info(
            "run progress",
            extra={
                "qc_run_id": run_id,
                "shards_open": sum(u.status in _OPEN for u in units),
                "shards_failed": sum(u.status == WorkUnit.Status.FAILED for u in units),
                "shards_total": len(units),
            },
        )
        if run.status not in (QCRun.Status.QUEUED, QCRun.Status.RUNNING):
            return
        if run.cancel_requested_at or units_open:
            return
        if VLM_ENGINE in (run.engine_versions or {}) and (
            not vlm_stage_started(run_id) or vlm_units_open(run_id)
        ):
            return  # VLM chưa xong (hoặc chưa khởi động): run vẫn đang chạy
        failed = sum(u.status == WorkUnit.Status.FAILED for u in units)
        if fail_fast_enabled():
            failed += VlmUnit.objects.filter(
                run_id=run_id, evaluation_generation=1, status=VlmUnit.Status.FAILED
            ).count()
        done = sum(u.status == WorkUnit.Status.COMPLETED for u in units)
        if failed == 0:
            run.status = QCRun.Status.COMPLETED
        elif done == 0:
            run.status = QCRun.Status.FAILED
        else:
            run.status = QCRun.Status.PARTIAL
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])
        # Fail-fast partial output is immutable once exposed to reviewers.
        if run.status == QCRun.Status.COMPLETED or (
            fail_fast_enabled() and run.status == QCRun.Status.PARTIAL
        ):
            transaction.on_commit(lambda: _persist_rankings_safely(run_id))
            if run.status == QCRun.Status.COMPLETED and run.metric_reference_id:
                from runs.ground_truth import cleanup_upload_safely

                reference_id = run.metric_reference_id
                transaction.on_commit(lambda: cleanup_upload_safely(reference_id))


def _refresh_vlm_result(run_id: int, result: EngineResult) -> None:
    """EngineResult của vlm tính từ VlmUnit (đơn vị = candidate), không từ LedgerUnit theo frame."""
    if not vlm_stage_started(run_id):
        return  # candidate chưa sinh xong: giữ nguyên trạng thái running ban đầu
    ledger = vlm_ledger_counts(run_id)
    completed, failed, pending = ledger.completed, ledger.failed, ledger.pending
    if ledger.total == 0:
        result.status = EngineStatus.NOT_CHECKED.value
        skipped = VlmBudget.objects.filter(run_id=run_id).values_list("skipped_reason", flat=True)
        result.reason = skipped.first() or NotCheckedReason.NOT_TRIGGERED.value
        result.eligible_units = 0
        result.completed_units = result.failed_units = result.not_checked_units = 0
    else:
        result.status = public_status(ledger, finished=not pending).value
        result.reason = None
        result.eligible_units = ledger.eligible
        result.completed_units = completed
        result.failed_units = failed
        result.not_checked_units = 0
    result.save(
        update_fields=[
            "status",
            "reason",
            "eligible_units",
            "completed_units",
            "failed_units",
            "not_checked_units",
        ]
    )


def _persist_rankings_safely(run_id: int) -> None:
    try:
        persist_terminal_run_rankings(run_id)
    except Exception:
        logger.exception("analysis finished but review ranking failed", extra={"qc_run_id": run_id})
