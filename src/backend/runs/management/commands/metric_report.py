"""Export the persisted metric counts with coverage and provenance."""

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from engines.metric import summarize_metric_details
from orchestration.models import LedgerUnit
from runs.kpi import ledger_entries
from runs.models import QCRun


class Command(BaseCommand):
    help = "Export Detector Precision/Recall by class/slice for a QC run as JSON"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("run_id", type=int)

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            run = QCRun.objects.get(pk=options["run_id"])
        except QCRun.DoesNotExist as exc:
            raise CommandError("QC run not found") from exc
        rows = list(
            LedgerUnit.objects.filter(run=run, engine="metric").order_by(
                "cvat_task_id", "frame_number"
            )
        )
        details = [row.details for row in rows if row.outcome == "completed" and row.details]
        report = {
            "run_id": run.pk,
            "coverage": next((e for e in ledger_entries(run) if e["engine"] == "metric"), None),
            "metrics": summarize_metric_details(details),
            "frames": [
                {
                    "cvat_task_id": row.cvat_task_id,
                    "frame_number": row.frame_number,
                    "outcome": row.outcome,
                    "reason": row.not_checked_reason,
                    **row.details,
                }
                for row in rows
            ],
        }
        self.stdout.write(json.dumps(report, sort_keys=True, allow_nan=False))
