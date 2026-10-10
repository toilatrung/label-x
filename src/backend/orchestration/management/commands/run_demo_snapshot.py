"""DEMO-ONLY command for M-DEMO01 / D-02."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError, CommandParser

from orchestration.demo_runner import run_snapshot_synchronously
from runs.services import RunDomainError


class Command(BaseCommand):
    help = "DEMO-ONLY: create/reuse a QC run and execute all pending shards synchronously."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("snapshot_id", type=int)
        parser.add_argument("--config-version-id", type=int, required=True)
        parser.add_argument("--created-by", required=True, metavar="USERNAME")
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--idempotency-key")

    def handle(self, *args: Any, **options: Any) -> None:
        username = options["created_by"]
        user = get_user_model().objects.filter(username=username).first()
        if user is None:
            raise CommandError(f"User {username!r} does not exist.")

        snapshot_id = options["snapshot_id"]
        config_version_id = options["config_version_id"]
        seed = options["seed"]
        idempotency_key = options["idempotency_key"] or (
            f"demo:snapshot:{snapshot_id}:config:{config_version_id}:seed:{seed}"
        )
        try:
            summary = run_snapshot_synchronously(
                snapshot_id=snapshot_id,
                config_version_id=config_version_id,
                seed=seed,
                created_by=user,
                idempotency_key=idempotency_key,
            )
        except (RunDomainError, TypeError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        action = "created" if summary.created else "reused"
        self.stdout.write(
            self.style.SUCCESS(
                f"run_id={summary.run_id} action={action} status={summary.status} "
                f"executed_work_units={summary.executed_work_units} "
                f"failed_work_units={summary.failed_work_units} "
                f"candidates={summary.candidate_count}"
            )
        )
        for frame in summary.ranked_frames:
            self.stdout.write(
                f"rank={frame.rank} frame={frame.frame_key} score={frame.score} "
                f"missing_evidence={str(frame.missing_evidence).lower()}"
            )
        self.stdout.write(f"score_version=score_v0 ranking_hash={summary.ranking_hash}")
