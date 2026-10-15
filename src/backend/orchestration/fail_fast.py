"""Stop an engine after its first failure without discarding successful engines."""

from django.conf import settings
from django.utils import timezone

from orchestration.models import LedgerUnit
from runs.models import QCRun, WorkUnit

ENGINE_STOPPED_MESSAGE = "Engine đã dừng sau lỗi; bỏ qua phần còn lại."


def enabled() -> bool:
    return bool(getattr(settings, "ORCHESTRATION_FAIL_FAST", True))


def stop_failed_engines(run: QCRun) -> None:
    """Caller holds the run lock. Revoke leases so late results cannot commit."""
    if not enabled() or run.status not in (QCRun.Status.QUEUED, QCRun.Status.RUNNING):
        return
    if run.retry_engine:
        return  # An explicit retry settles each selected unit independently.
    failed = set(
        run.work_units.filter(status=WorkUnit.Status.FAILED).values_list("engine", flat=True)
    )
    failed.discard("detector")  # Independent shards keep their successful results.
    now = timezone.now()
    for engine in failed:
        run.work_units.filter(
            engine=engine, status__in=(WorkUnit.Status.PENDING, WorkUnit.Status.RUNNING)
        ).update(
            status=WorkUnit.Status.FAILED,
            lease_token="",
            finished_at=now,
            last_error=ENGINE_STOPPED_MESSAGE,
        )
        LedgerUnit.objects.filter(
            run_id=run.pk, engine=engine, outcome__in=("pending", "running", "retrying")
        ).update(outcome="failed", not_checked_reason="")
