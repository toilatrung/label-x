"""Celery task chạy một shard: idempotent, retry/backoff theo policy (T-025, AC-02)."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from engines.interface import EngineInput
from orchestration.models import ShardCommit
from orchestration.registry import EngineRegistry, registry
from orchestration.retry import RetryPolicy, default_policy
from orchestration.services import (
    ShardOutputError,
    commit_shard_output,
    engine_input_from_payload,
    mark_shard_failed,
)

logger = logging.getLogger("labelx.orchestration")


def execute_shard(engine_input: EngineInput, *, engines: EngineRegistry = registry) -> bool:
    """Chạy engine rồi commit. Trả True nếu commit mới; ném lỗi để task retry."""
    if ShardCommit.objects.filter(
        run_id=engine_input.run_id, idempotency_key=engine_input.idempotency_key
    ).exists():
        return False  # giao lại sau khi worker chết sau commit: không chạy lại engine
    runner = engines.runner(engine_input.engine, engine_input.engine_version)
    return commit_shard_output(engine_input, runner(engine_input))


@shared_task(
    bind=True,
    name="orchestration.run_engine_shard",
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_engine_shard(self: Any, payload: dict[str, Any]) -> bool:
    engine_input = engine_input_from_payload(payload)
    policy: RetryPolicy = default_policy()
    try:
        return execute_shard(engine_input)
    except (ShardOutputError, LookupError, ValueError) as exc:
        # Lỗi cố định (input/engine sai): retry không giúp, đóng shard là failed.
        mark_shard_failed(engine_input, attempts=self.request.retries + 1)
        logger.error("shard failed permanently", extra={"error": str(exc)})
        raise
    except Exception as exc:
        if policy.exhausted(self.request.retries):
            mark_shard_failed(engine_input, attempts=self.request.retries + 1)
            raise
        raise self.retry(
            exc=exc,
            countdown=policy.backoff(self.request.retries + 1),
            max_retries=policy.max_retries,
        ) from exc
