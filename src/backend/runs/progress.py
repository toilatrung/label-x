"""Operational progress is separate from quality/coverage and model evidence."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from django.db.models import Count, OuterRef, Subquery
from django.utils import timezone

from orchestration.models import VlmUnit
from runs.models import QCRun, WorkUnit


def engine_progress(
    run: QCRun,
    engine: str,
    *,
    work_units: list[WorkUnit] | None = None,
) -> dict[str, Any]:
    rows: list[Mapping[str, Any]]
    if engine == "vlm":
        latest = (
            VlmUnit.objects.filter(run=run, candidate_id=OuterRef("candidate_id"))
            .order_by("-evaluation_generation")
            .values("pk")[:1]
        )
        qs = VlmUnit.objects.filter(run=run, pk=Subquery(latest)).annotate(
            sent_calls=Count("attempt_rows")
        )
        rows = list(
            qs.values(
                "status",
                "retry_at",
                "deadline_at",
                "error_code",
                "started_at",
                "finished_at",
                "sent_calls",
            )
        )
        calls = sum(row["sent_calls"] for row in rows)
    else:
        selected = [
            unit
            for unit in (work_units if work_units is not None else run.work_units.all())
            if unit.engine == engine
        ]
        calls = sum(unit.request_attempts for unit in selected)
        rows = [
            {
                "status": unit.status,
                "retry_at": unit.retry_at,
                "deadline_at": unit.deadline_at,
                "error_code": unit.error_code,
                "started_at": unit.started_at,
                "finished_at": unit.finished_at,
            }
            for unit in selected
        ]
    now = timezone.now()
    pending = [r for r in rows if r["status"] in ("pending", "running")]
    waiting = [r for r in pending if r["retry_at"] is not None]
    running = [r for r in pending if r["status"] == "running" and r["retry_at"] is None]
    events = [r[f] for r in rows for f in ("started_at", "finished_at") if r[f]]
    retry_times: list[datetime] = [r["retry_at"] for r in waiting]
    retry_at = min(retry_times, default=None)
    deadline = min((r["deadline_at"] for r in pending if r["deadline_at"]), default=None)
    stale = bool(deadline and deadline <= now)
    phase = (
        "overdue"
        if stale
        else "running"
        if running
        else "waiting_retry"
        if waiting
        else "queued"
        if pending
        else "finished"
        if rows
        else "preparing"
    )
    skipped = sum(r["status"] == "skipped" for r in rows)
    errors = [r["error_code"] for r in waiting if r["error_code"]]
    return {
        "phase": phase,
        "retry_at": retry_at.isoformat() if retry_at else None,
        "deadline_at": deadline.isoformat() if deadline else None,
        "last_activity_at": max(events).isoformat() if events else None,
        "error_code": errors[0] if errors else None,
        "pending": len(pending),
        "skipped": skipped,
        "failed": sum(r["status"] == "failed" for r in rows),
        "provider_calls": calls,
        "stale": stale,
    }
