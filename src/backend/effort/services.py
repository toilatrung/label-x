from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction

from effort.models import EffortEvent
from review.models import FrameReview


class EffortEventConflictError(RuntimeError):
    pass


class EffortPolicyError(RuntimeError):
    """The event cannot be evaluated under the deployed policy (unset or stale version)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# idle spans count only above t_idle; the others are excluded in full, immediately (DEC-019 P03).
GAP_REASONS = ("idle", "blur", "hidden", "pause")


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
    policy.setdefault("version", derived_policy_version(policy))
    return policy


def derived_policy_version(policy: dict[str, Any]) -> str:
    """Stable content-derived version used when deployment does not name one."""
    body = {key: value for key, value in policy.items() if key != "version"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def excluded_ms(
    *,
    started_at: datetime,
    ended_at: datetime,
    gaps: list[dict[str, Any]],
    t_idle_seconds: int | None,
) -> int:
    """Total time removed from the event: union of excluded gaps, so overlaps count once."""
    spans: list[tuple[datetime, datetime]] = []
    for gap in gaps:
        start, end = max(gap["started_at"], started_at), min(gap["ended_at"], ended_at)
        if end <= start:
            continue
        if gap["reason"] == "idle":
            if t_idle_seconds is None:
                raise EffortPolicyError(
                    "POLICY_NOT_CONFIGURED",
                    "Idle threshold is not configured; cannot apply idle gap.",
                )
            if (end - start).total_seconds() <= t_idle_seconds:
                continue
        spans.append((start, end))
    total = timedelta(0)
    current: tuple[datetime, datetime] | None = None
    for start, end in sorted(spans):
        if current is None or start > current[1]:
            if current is not None:
                total += current[1] - current[0]
            current = (start, end)
        else:
            current = (current[0], max(current[1], end))
    if current is not None:
        total += current[1] - current[0]
    return int(total.total_seconds() * 1000)


def _normalized_gaps(gaps: list[dict[str, Any]]) -> list[dict[str, str]]:
    return sorted(
        (
            {
                "started_at": gap["started_at"].isoformat(),
                "ended_at": gap["ended_at"].isoformat(),
                "reason": gap["reason"],
            }
            for gap in gaps
        ),
        key=lambda gap: (gap["started_at"], gap["ended_at"], gap["reason"]),
    )


def _same_event(
    event: EffortEvent,
    *,
    actor: User,
    frame_id: int,
    activity: str,
    started_at: datetime,
    ended_at: datetime,
    gaps: list[dict[str, str]],
) -> bool:
    stored_gaps = event.config_snapshot.get("lifecycle", {}).get("gaps", [])
    return (
        event.actor_id == actor.pk
        and event.frame_id == frame_id
        and event.activity == activity
        and event.started_at == started_at
        and event.ended_at == ended_at
        and stored_gaps == gaps
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
        claimed_version = payload.get("policy_version")
        if claimed_version is not None and claimed_version != policy["version"]:
            raise EffortPolicyError(
                "POLICY_VERSION_MISMATCH",
                f"Event measured under policy {claimed_version}; current is {policy['version']}.",
            )
        raw_gaps = list(payload.get("gaps", []))
        gaps = _normalized_gaps(raw_gaps)
        wall_ms = int((ended_at - started_at).total_seconds() * 1000)
        removed_ms = excluded_ms(
            started_at=started_at,
            ended_at=ended_at,
            gaps=raw_gaps,
            t_idle_seconds=policy["t_idle_seconds"],
        )
        defaults = {
            "actor": actor,
            "frame": frame,
            "dataset_id": frame.run.dataset_id,
            "activity": payload["activity"],
            "started_at": started_at,
            "ended_at": ended_at,
            "active_ms": wall_ms - removed_ms,
            "config_source": str(policy["source"]),
            "t_idle_seconds": policy["t_idle_seconds"],
            "config_snapshot": {
                **policy,
                "lifecycle": {"gaps": gaps, "wall_ms": wall_ms, "excluded_ms": removed_ms},
            },
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
            gaps=gaps,
        ):
            raise EffortEventConflictError(
                f"client_event_id {event_id} was already used for a different event"
            )
        duplicates += 1
    return EffortReceipt(accepted=accepted, duplicates=duplicates)
