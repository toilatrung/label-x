"""Versioned review-policy read model (DEC-019 P02/P03, pilot values from deployment config)."""

from __future__ import annotations

from typing import Any

from django.conf import settings

from effort.services import current_idle_policy


class ReviewPolicyNotConfigured(RuntimeError):
    """A required lease/idle value is unset; the API fails closed instead of inventing one."""


def _positive(name: str) -> int:
    raw = getattr(settings, name, None)
    if isinstance(raw, bool) or raw is None or not str(raw).isdigit() or int(raw) <= 0:
        raise ReviewPolicyNotConfigured(f"{name} is not configured")
    return int(raw)


def current_review_policy() -> dict[str, Any]:
    """Single source the lease service, effort ingestion and the UI collector all agree on."""

    idle = current_idle_policy()
    threshold = idle["t_idle_seconds"]
    if threshold is None:
        raise ReviewPolicyNotConfigured("EFFORT_IDLE_POLICY.t_idle_seconds is not configured")
    return {
        "policy_version": idle["version"],
        "source": idle["source"],
        "decision_status": idle["decision_status"],
        "lease_ttl_seconds": _positive("REVIEW_LEASE_TTL_SECONDS"),
        "resume_reservation_seconds": _positive("REVIEW_INCOMPLETE_RESERVATION_SECONDS"),
        "idle_threshold_seconds": threshold,
        "idle_gap_rule": "exclude_whole_gap_over_threshold",
        "immediate_exclusion_reasons": ["blur", "hidden", "pause"],
        "renew_on": "user_activity",
    }
