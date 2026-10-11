from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction

from effort.models import EffortEvent
from review.models import FrameReview


class EffortEventConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class EffortReceipt:
    accepted: int
    duplicates: int


def current_idle_policy() -> dict[str, Any]:
    """Return the approved policy snapshot without inventing a TBD-11 value."""
    configured = getattr(settings, "EFFORT_IDLE_POLICY", None)
    policy = dict(configured) if isinstance(configured, dict) else {}
    policy.setdefault("source", "TBD-11 / m03-review-workflow-v1")
    policy.setdefault("decision_status", "requires_product_owner_decision")
    policy.setdefault("t_idle_seconds", None)
    threshold = policy["t_idle_seconds"]
    invalid_threshold = (
        isinstance(threshold, bool) or not isinstance(threshold, int) or threshold <= 0
    )
    if threshold is not None and invalid_threshold:
        raise ValueError("EFFORT_IDLE_POLICY.t_idle_seconds must be null or a positive integer")
    return policy


def _same_event(
    event: EffortEvent,
    *,
    actor: User,
    frame_id: int,
    activity: str,
    started_at: datetime,
    ended_at: datetime,
) -> bool:
    return (
        event.actor_id == actor.pk
        and event.frame_id == frame_id
        and event.activity == activity
        and event.started_at == started_at
        and event.ended_at == ended_at
    )


@transaction.atomic
def ingest_effort_events(*, actor: User, events: list[dict[str, Any]]) -> EffortReceipt:
    frame_ids = {int(event["frame_id"]) for event in events}
    frames = {
        frame.pk: frame
        for frame in FrameReview.objects.select_related("run").filter(pk__in=frame_ids)
    }
    if set(frames) != frame_ids:
        raise FrameReview.DoesNotExist

    policy = current_idle_policy()
    accepted = 0
    duplicates = 0
    for payload in events:
        event_id = payload["client_event_id"]
        if not isinstance(event_id, UUID):
            event_id = UUID(str(event_id))
        frame = frames[int(payload["frame_id"])]
        started_at = payload["started_at"]
        ended_at = payload["ended_at"]
        defaults = {
            "actor": actor,
            "frame": frame,
            "dataset_id": frame.run.dataset_id,
            "activity": payload["activity"],
            "started_at": started_at,
            "ended_at": ended_at,
            "active_ms": int((ended_at - started_at).total_seconds() * 1000),
            "config_source": str(policy["source"]),
            "t_idle_seconds": policy["t_idle_seconds"],
            "config_snapshot": policy,
        }
        stored, created = EffortEvent.objects.get_or_create(
            client_event_id=event_id,
            defaults=defaults,
        )
        if created:
            accepted += 1
            continue
        if not _same_event(
            stored,
            actor=actor,
            frame_id=frame.pk,
            activity=payload["activity"],
            started_at=started_at,
            ended_at=ended_at,
        ):
            raise EffortEventConflictError(
                f"client_event_id {event_id} was already used for a different event"
            )
        duplicates += 1
    return EffortReceipt(accepted=accepted, duplicates=duplicates)
