"""Tạo lại hàng đợi review (RunRanking) cho run đã kết thúc nhưng chưa có ranking. Idempotent."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from orchestration.fail_fast import enabled as fail_fast_enabled
from runs.models import QCRun
from runs.ranking import persist_terminal_run_rankings


class Command(BaseCommand):
    help = (
        "Tạo ranking cho run COMPLETED (hoặc PARTIAL khi fail-fast) chưa có RunRanking, ví dụ khi "
        "worker bị kill giữa lúc run kết thúc và lúc lưu ranking. Chạy lại an toàn: ranking đã "
        "có cùng nội dung được giữ nguyên, khác nội dung thì dừng và báo lỗi."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("run_ids", nargs="*", type=int, help="Chỉ xử lý các run này.")
        parser.add_argument(
            "--dry-run", action="store_true", help="Chỉ liệt kê run thiếu ranking, không ghi."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        statuses = [QCRun.Status.COMPLETED]
        if fail_fast_enabled():
            statuses.append(QCRun.Status.PARTIAL)
        runs = QCRun.objects.filter(status__in=statuses, rankings__isnull=True).order_by("pk")
        if options["run_ids"]:
            runs = runs.filter(pk__in=options["run_ids"])
        run_ids = list(runs.values_list("pk", flat=True))
        if not run_ids:
            self.stdout.write("Không có run nào thiếu ranking.")
            return
        failed = 0
        for run_id in run_ids:
            if options["dry_run"]:
                self.stdout.write(f"run {run_id}: thiếu ranking")
                continue
            try:
                rankings = persist_terminal_run_rankings(run_id)
            except Exception as exc:  # noqa: BLE001 - report each run, keep going
                failed += 1
                self.stderr.write(f"run {run_id}: LỖI {type(exc).__name__}: {exc}")
            else:
                self.stdout.write(f"run {run_id}: đã tạo {len(rankings)} ranking")
        if failed:
            raise SystemExit(1)
