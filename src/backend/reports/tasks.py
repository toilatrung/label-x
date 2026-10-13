from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from reports.models import ReportExport
from reports.services import build_run_report, render_report
from storage.client import ObjectStorage

logger = logging.getLogger("labelx.reports")


@shared_task(name="reports.generate_export")
def generate_report_export(export_id: int) -> int:
    with transaction.atomic():
        export = ReportExport.objects.select_for_update().select_related("run").get(pk=export_id)
        if export.status == ReportExport.Status.COMPLETED:
            return export.pk
        export.status = ReportExport.Status.RUNNING
        export.started_at = export.started_at or timezone.now()
        export.error = None
        export.save(update_fields=["status", "started_at", "error"])

    try:
        content, content_type = render_report(build_run_report(export.run), export.format)
        blob = ObjectStorage.from_django_settings("reports").put(
            content, extension=export.format, content_type=content_type
        )
    except Exception as exc:
        ReportExport.objects.filter(pk=export_id).update(
            status=ReportExport.Status.FAILED,
            error=str(exc)[:255],
            finished_at=timezone.now(),
        )
        raise

    ReportExport.objects.filter(pk=export_id).update(
        status=ReportExport.Status.COMPLETED,
        storage_key=blob.key,
        sha256=blob.sha256,
        size_bytes=blob.size,
        error=None,
        finished_at=timezone.now(),
    )
    return export_id


def enqueue_report_export(export_id: int) -> None:
    if not getattr(settings, "REPORT_EXPORT_AUTO_DISPATCH", True):
        return
    try:
        generate_report_export.delay(export_id)
    except Exception:
        logger.exception("could not enqueue report export", extra={"report_export_id": export_id})
