"""Retry one failed engine while preserving successful output and published Review queues."""

from __future__ import annotations

import hashlib

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Max, OuterRef, Subquery

from audit.services import append_audit_event
from orchestration.models import Evaluation, LedgerUnit, VlmBudget, VlmUnit
from runs.models import QCRun, WorkUnit
from runs.services import BusinessRuleUnmetError, InvalidTransitionError, RunDomainError


def retry_failed_engine(*, run_id: int, engine: str, actor: User) -> QCRun:
    with transaction.atomic():
        run = (
            QCRun.objects.select_for_update()
            .select_related("config_version", "snapshot")
            .filter(pk=run_id)
            .first()
        )
        if run is None:
            raise RunDomainError("Run không tồn tại.")
        if run.status not in (
            QCRun.Status.PARTIAL,
            QCRun.Status.FAILED,
            QCRun.Status.COMPLETED,
            QCRun.Status.CANCELLED,
        ):
            raise InvalidTransitionError("Chờ run kết thúc trước khi chạy lại một engine lỗi.")
        if run.is_final:
            raise BusinessRuleUnmetError("Không chạy lại engine của run cuối tổng hợp.")
        if VlmUnit.objects.filter(run=run, status__in=("pending", "running")).exists():
            raise InvalidTransitionError("Run đang có tác vụ VLM chưa kết thúc; hãy chờ hoàn tất.")
        result = run.engine_results.filter(engine=engine).first()
        if result is None or not (
            result.failed_units > 0 or result.status in ("partial", "failed")
        ):
            raise BusinessRuleUnmetError("Engine được chọn không có đơn vị lỗi để chạy lại.")
        if engine == "vlm":
            requeued = _retry_vlm(run, actor)
        else:
            requeued = _retry_shards(run, engine)
        if requeued == 0:
            raise BusinessRuleUnmetError("Engine được chọn không có đơn vị lỗi để chạy lại.")
        old_status = run.status
        old_cancel_requested_at = run.cancel_requested_at
        run.retry_engine = engine
        run.status = QCRun.Status.RUNNING
        run.finished_at = None
        # This explicit request authorizes only the failed selected units to resume.
        # Cancelled units retain their status and leases; the original cancellation is audited.
        run.cancel_requested_at = None
        run.save(update_fields=["retry_engine", "status", "finished_at", "cancel_requested_at"])
        result.status = "running"
        result.failed_units = 0
        result.save(update_fields=["status", "failed_units"])
        append_audit_event(
            actor=actor,
            action="run.retry_failed",
            object_type="run",
            object_id=run.pk,
            before={
                "status": old_status,
                "cancel_requested_at": (
                    old_cancel_requested_at.isoformat() if old_cancel_requested_at else None
                ),
            },
            after={"status": run.status, "engine": engine, "requeued_units": requeued},
            revision=str(run.pk),
        )
        from django.conf import settings

        if getattr(settings, "ORCHESTRATION_AUTO_DISPATCH", True):
            transaction.on_commit(lambda: _dispatch(run.pk, engine))
        return run


def _dispatch(run_id: int, engine: str) -> None:
    from orchestration.dispatch import dispatch_run_safely
    from orchestration.vlm_stage import dispatch_vlm_units_safely

    if engine == "vlm":
        dispatch_vlm_units_safely(run_id)
    else:
        dispatch_run_safely(run_id)


def _retry_shards(run: QCRun, engine: str) -> int:
    from orchestration.dispatch import shard_units
    from snapshots.models import SnapshotFrame

    failed = list(run.work_units.filter(engine=engine, status="failed"))
    covered = {
        (ref.frame.cvat_task_id, ref.frame.frame_number)
        for unit in failed
        for ref in shard_units(unit)
    }
    failed_rows = list(LedgerUnit.objects.filter(run=run, engine=engine, outcome="failed"))
    index = run.work_units.filter(engine=engine).aggregate(m=Max("shard_index"))["m"] or 0
    created = 0
    # An engine can commit a shard with failed frame outcomes. Retry only those frames
    # in new shards, retaining the original commit and all successful frame evidence.
    for row in failed_rows:
        identity = (row.cvat_task_id, row.frame_number)
        if identity in covered:
            continue
        frame = (
            SnapshotFrame.objects.filter(
                snapshot_job__snapshot_id=run.snapshot_id,
                snapshot_job__cvat_task_id=row.cvat_task_id,
                frame_index=row.frame_number,
            )
            .select_related("snapshot_job")
            .first()
        )
        if frame is None:
            raise BusinessRuleUnmetError("Không tìm được frame lỗi trong snapshot của run.")
        index += 1
        key = (
            f"job:{frame.snapshot_job.cvat_job_id}:frames:"
            f"{row.frame_number}-{row.frame_number}:retry:{index}"
        )
        WorkUnit.objects.create(
            run=run,
            engine=engine,
            shard_key=key,
            shard_index=index,
            idempotency_key=hashlib.sha256(f"retry:{run.pk}:{engine}:{index}".encode()).hexdigest(),
        )
        covered.add(identity)
        created += 1
    for unit in failed:
        unit.status = WorkUnit.Status.PENDING
        unit.attempt += 1
        unit.last_error = unit.lease_token = ""
        unit.started_at = unit.finished_at = unit.dispatched_at = None
        unit.save(
            update_fields=[
                "status",
                "attempt",
                "last_error",
                "lease_token",
                "started_at",
                "finished_at",
                "dispatched_at",
            ]
        )
    LedgerUnit.objects.filter(run=run, engine=engine, outcome="failed").update(outcome="pending")
    return len(failed) + created


def _retry_vlm(run: QCRun, actor: User) -> int:
    from orchestration.evaluation_service import _vlm_unit_for
    from orchestration.vlm_stage import run_vlm_config
    from vlm.config import parse_vlm_config

    raw = run_vlm_config(run)
    if raw is None:
        raise BusinessRuleUnmetError("Run không có cấu hình VLM hợp lệ.")
    budget = VlmBudget.objects.filter(run=run).first()
    if budget is None or budget.used_calls >= budget.max_calls:
        raise BusinessRuleUnmetError("Run đã hết ngân sách VLM; không thể gọi thêm provider.")
    latest = (
        VlmUnit.objects.filter(run=run, candidate_id=OuterRef("candidate_id"))
        .order_by("-evaluation_generation")
        .values("pk")[:1]
    )
    failed = list(
        VlmUnit.objects.filter(run=run, pk=Subquery(latest), status="failed").select_related(
            "candidate", "evaluation"
        )
    )
    config = parse_vlm_config(raw)
    for previous in failed:
        evaluation = getattr(previous, "evaluation", None)
        if evaluation is None:
            raise BusinessRuleUnmetError("Thiếu thông tin evaluation của ảnh VLM lỗi.")
        last_generation = (
            Evaluation.objects.filter(candidate=previous.candidate).aggregate(m=Max("generation"))[
                "m"
            ]
            or previous.evaluation_generation
        )
        generation = max(last_generation, previous.evaluation_generation) + 1
        unit = _vlm_unit_for(previous.candidate, run, config, generation)
        unit.save()
        Evaluation.objects.create(
            run=run,
            candidate=previous.candidate,
            generation=generation,
            source=Evaluation.Source.MANUAL,
            requested_by=actor,
            note="Chạy lại engine VLM lỗi",
            expected_revision=evaluation.snapshot_revision,
            snapshot_revision=evaluation.snapshot_revision,
            primary_reason=evaluation.primary_reason,
            reasons=evaluation.reasons,
            call_qwen=True,
            human_review_required=evaluation.human_review_required,
            policy=evaluation.policy,
            checkpoint_status=evaluation.checkpoint_status,
            vlm_unit=unit,
        )
    return len(failed)
