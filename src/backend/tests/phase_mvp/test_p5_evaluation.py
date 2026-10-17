"""Issue #396 supplemental evidence; no fabricated evaluation approval/bindings."""

from datetime import UTC, datetime, timedelta

import pytest
from django.db import connection

from accounts.models import Role
from effort.models import EffortEvent
from engines.interface import EngineConfig, EngineInput, EngineUnitRef, FrameKey
from engines.metric import count_detections, run_metric_engine
from tests.effort.test_effort_events import _client, _frame, _payload, _user


def test_missing_reference_is_not_checked_and_empty_truth_is_not_perfect():
    inp = EngineInput(
        "missing-ref",
        1,
        2,
        "metric",
        "1.0.0",
        EngineConfig("metric", "v1", True, {}),
        42,
        0,
        (EngineUnitRef("frame", FrameKey(9, 0)),),
    )
    output = run_metric_engine(inp)
    assert output.candidates == ()
    (result,) = output.unit_results
    assert result.unit == inp.units[0]
    assert result.outcome == "not_checked"
    assert result.not_checked_reason == "no_reference"
    # No empty-ground-truth result can be interpreted as a 0% or perfect score.
    assert count_detections([], [], tau_m=0.5) == {}


@pytest.mark.django_db(transaction=True)
def test_effort_review_and_recheck_timeline_keeps_idle_provenance_and_retry(settings):
    """A synthetic pilot fixture; not an approval of held-out acceptance policy."""
    assert connection.vendor == "postgresql"
    settings.EFFORT_IDLE_POLICY = {
        "source": "test-fixture/issue396",
        "decision_status": "approved_for_pilot",
        "t_idle_seconds": 120,
        "version": "issue396-fixture-v1",
    }
    reviewer = _user("issue396-reviewer", Role.REVIEWER, 42)
    frame = _frame(reviewer)
    api = _client(reviewer)
    start = datetime(2026, 10, 11, 2, 0, tzinfo=UTC)
    review = _payload(
        frame.pk,
        started_at=start.isoformat(),
        ended_at=(start + timedelta(seconds=600)).isoformat(),
        policy_version="issue396-fixture-v1",
        gaps=[
            {
                "started_at": (start + timedelta(seconds=100)).isoformat(),
                "ended_at": (start + timedelta(seconds=300)).isoformat(),
                "reason": "idle",
            },
            {
                "started_at": (start + timedelta(seconds=200)).isoformat(),
                "ended_at": (start + timedelta(seconds=250)).isoformat(),
                "reason": "hidden",
            },
        ],
    )
    recheck = _payload(
        frame.pk,
        activity="recheck_verify",
        started_at=(start + timedelta(seconds=600)).isoformat(),
        ended_at=(start + timedelta(seconds=660)).isoformat(),
        policy_version="issue396-fixture-v1",
    )
    for payload in (review, recheck):
        accepted = api.post("/api/effort-events/", payload, format="json")
        assert accepted.status_code == 202, accepted.data
        assert accepted.data == {"accepted": 1, "duplicates": 0}
        retry = api.post("/api/effort-events/", payload, format="json")
        assert retry.status_code == 202
        assert retry.data == {"accepted": 0, "duplicates": 1}
    rows = EffortEvent.objects.filter(frame=frame).order_by("started_at")
    assert list(rows.values_list("activity", "active_ms")) == [
        ("review_issue", 400_000),
        ("recheck_verify", 60_000),
    ]
    assert sum(event.active_ms for event in rows) == 460_000
    assert all(event.config_snapshot["version"] == "issue396-fixture-v1" for event in rows)
    assert all(event.config_source == "test-fixture/issue396" for event in rows)
