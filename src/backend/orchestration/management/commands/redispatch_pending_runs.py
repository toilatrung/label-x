"""Xếp lại shard PENDING của run QUEUED/RUNNING bị kẹt (broker lỗi/mất message). Idempotent."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from orchestration.dispatch import redispatch_pending


class Command(BaseCommand):
    help = "Redispatch shard PENDING của run QUEUED/RUNNING quá tuổi; không đụng run đã huỷ."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--older-than",
            type=float,
            default=None,
            help="Chỉ run tạo quá N giây trước (mặc định ORCHESTRATION_REDISPATCH_AFTER_SECONDS).",
        )
        parser.add_argument(
            "--running-older-than",
            type=float,
            default=None,
            help="Thu hồi RUNNING quá N giây (mặc định ORCHESTRATION_RUNNING_STALE_SECONDS).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        result = redispatch_pending(options["older_than"], options["running_older_than"])
        self.stdout.write(f"runs={result['runs']} queued={result['queued']}")
