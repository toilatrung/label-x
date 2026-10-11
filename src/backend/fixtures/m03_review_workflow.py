"""Materialize the shared M-03 seed at a scenario's explicit clock.

Consumers should seed this result rather than combining raw rows with a scenario
at a different time. This is fixture preparation, not a runtime review service.
"""

from copy import deepcopy
from datetime import datetime
from typing import Any


def _clock(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def materialize_scenario(seed: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    """Apply lease expiry while preserving saved decisions and the original seed."""
    fixture = deepcopy(seed)
    as_of = _clock(scenario["as_of"])
    frames = {frame["id"]: frame for frame in fixture["frames"]}
    for lease in fixture["leases"]:
        frame = frames[lease["frame_id"]]
        issues = [issue for issue in fixture["issues"] if issue["frame_id"] == frame["id"]]
        if _clock(lease["expires_at"]) > as_of:
            lease["fixture_state"] = "active"
            frame["review_state"] = "in_review"
            continue
        saved = any(issue["review_decisions"] for issue in issues)
        lease["fixture_state"] = "expired_with_saved_decision" if saved else "expired"
        if frame["review_state"] == "in_review":
            frame["review_state"] = "incomplete" if saved else "unreviewed"
            frame["previous_reviewer_user_id"] = lease["holder_user_id"]
            for issue in issues:
                if not issue["review_decisions"] and issue["state"] == "in_review":
                    issue["state"] = "pending_review"
    fixture["as_of"] = scenario["as_of"]
    return fixture
