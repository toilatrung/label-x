"""Đồng bộ EngineResult và trạng thái QCRun từ ledger/WorkUnit sau mỗi shard (FR-AGG-04/05)."""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from engines.interface import public_status
from orchestration.services import ledger_counts
from runs.models import QCRun, WorkUnit

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
        units = list(run.work_units.all())
        for result in run.engine_results.all():
            ledger = ledger_counts(run_id, result.engine)
            if ledger.total == 0:
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
        if run.cancel_requested_at or any(u.status in _OPEN for u in units):
            return
        failed = sum(u.status == WorkUnit.Status.FAILED for u in units)
        done = sum(u.status == WorkUnit.Status.COMPLETED for u in units)
        if failed == 0:
            run.status = QCRun.Status.COMPLETED
        elif done == 0:
            run.status = QCRun.Status.FAILED
        else:
            run.status = QCRun.Status.PARTIAL
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])
