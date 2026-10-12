"""Durable Celery entry points for final-scope QC creation."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q

from review.finalization_service import (
    FinalRunNotReady,
    build_final_run,
    complete_scope_frames,
)
from review.models import ReworkRequest
from runs.models import QCRun

logger = logging.getLogger("labelx.review")


@shared_task(
    bind=True,
    name="qc.build_final_run",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def build_final_run_task(self: Any, origin_run_id: int, actor_id: int) -> int | None:
    del self
    try:
        actor = User.objects.get(pk=actor_id)
        run, _created = build_final_run(origin_run_id=origin_run_id, actor=actor)
        return run.pk
    except FinalRunNotReady:
        # Readiness is normal while other reviewers are still working. The last
        # verification and the periodic sweeper both re-evaluate it.
        return None


def enqueue_final_run(origin_run_id: int, actor_id: int) -> None:
    """Publish after commit without turning a committed verification into HTTP 500."""

    if not getattr(settings, "FINAL_RUN_AUTO_DISPATCH", True):
        return
    try:
        build_final_run_task.delay(origin_run_id, actor_id)
    except Exception:
        logger.exception(
            "could not enqueue final run; periodic sweeper will retry",
            extra={"qc_run_id": origin_run_id},
        )


@shared_task(name="review.sweep_ready_final_runs")
def sweep_ready_final_runs() -> int:
    """Recover a broker publish failure and retry terminal failed/cancelled attempts."""

    candidates = (
        QCRun.objects.filter(
            is_final=False,
            origin_run__isnull=True,
            frame_reviews__issues__rework_requests__isnull=False,
        )
        .exclude(
            frame_reviews__issues__rework_requests__status__in=[
                ReworkRequest.Status.FIX_PENDING,
                ReworkRequest.Status.RECHECK_PENDING,
                ReworkRequest.Status.REOPENED,
            ]
        )
        .filter(Q(status=QCRun.Status.COMPLETED))
        .distinct()
    )
    queued = 0
    for run in candidates:
        enqueue_final_run(run.pk, run.created_by_id)
        queued += 1
    complete_scope_frames_sweep()
    return queued


@shared_task(name="review.complete_scope_frames")
def complete_scope_frames_sweep() -> int:
    """Complete frames of origin runs whose final run is now a valid operational source.

    Idempotent: only AWAITING_FOLLOWUP frames of fully resolved scopes change state.
    """

    origin_ids = (
        QCRun.objects.filter(
            is_final=False,
            origin_run__isnull=True,
            rework_runs__is_final=True,
            rework_runs__status=QCRun.Status.COMPLETED,
        )
        .values_list("pk", flat=True)
        .distinct()
    )
    return sum(complete_scope_frames(origin_id) for origin_id in origin_ids)
