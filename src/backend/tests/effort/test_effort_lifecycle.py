"""M03-R10 backend: idle/blur/hidden/pause exclusion, overlap dedupe, policy version."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from django.test import override_settings

from accounts.models import Role
from effort.models import EffortEvent
from effort.services import EffortPolicyError, excluded_ms
from tests.effort.test_effort_events import _client, _frame, _payload, _user

pytestmark = pytest.mark.django_db(transaction=True)
pytest_plugins = ["tests.review.test_queue_lease"]

T0 = datetime(2026, 10, 11, 2, 0, tzinfo=UTC)
POLICY = {
    "source": "DEC-019/P03",
    "decision_status": "approved_for_pilot",
    "t_idle_seconds": 120,
    "version": "m03-pilot-v1",
}


def gap(start_s: int, end_s: int, reason: str = "idle") -> dict:
    return {
        "started_at": T0 + timedelta(seconds=start_s),
        "ended_at": T0 + timedelta(seconds=end_s),
        "reason": reason,
    }


def _wire(start_s: int, end_s: int, reason: str = "idle") -> dict:
    g = gap(start_s, end_s, reason)
    return {k: (v.isoformat() if k != "reason" else v) for k, v in g.items()}


def _excluded(gaps, t_idle=120, total=600):
    return excluded_ms(
        started_at=T0, ended_at=T0 + timedelta(seconds=total), gaps=gaps, t_idle_seconds=t_idle
    )


def test_idle_gap_at_or_below_threshold_is_kept_and_above_is_removed_whole():
    assert _excluded([gap(10, 130)]) == 0  # exactly 120 s: still active
    assert _excluded([gap(10, 131)]) == 121_000  # whole gap, not just the excess


def test_blur_hidden_pause_are_removed_immediately_even_when_short():
    for reason in ("blur", "hidden", "pause"):
        assert _excluded([gap(10, 12, reason)]) == 2_000


def test_overlapping_gaps_are_counted_once():
    gaps = [gap(10, 200), gap(100, 300, "blur"), gap(100, 150, "hidden"), gap(400, 410, "pause")]
    assert _excluded(gaps) == 300_000  # [10,300] + [400,410]


def test_gap_outside_event_is_clipped_and_idle_requires_threshold():
    assert _excluded([gap(-50, 20, "blur")]) == 20_000
    with pytest.raises(EffortPolicyError) as err:
        _excluded([gap(10, 400)], t_idle=None)
    assert err.value.code == "POLICY_NOT_CONFIGURED"


@override_settings(EFFORT_IDLE_POLICY=POLICY)
def test_active_ms_excludes_gaps_and_batch_retry_does_not_double_count():
    reviewer = _user("lifecycle", Role.REVIEWER, 42)
    frame = _frame(reviewer)
    event_id = uuid.uuid4()
    payload = _payload(
        frame.pk,
        event_id,
        started_at=T0.isoformat(),
        ended_at=(T0 + timedelta(seconds=600)).isoformat(),
        gaps=[_wire(100, 300), _wire(200, 250, "blur")],
        policy_version="m03-pilot-v1",
    )
    api = _client(reviewer)
    first = api.post("/api/effort-events/", payload, format="json")
    retry = api.post("/api/effort-events/", payload, format="json")
    assert first.data == {"accepted": 1, "duplicates": 0}
    assert retry.data == {"accepted": 0, "duplicates": 1}
    stored = EffortEvent.objects.get()
    assert stored.active_ms == 400_000
    assert stored.config_snapshot["lifecycle"]["excluded_ms"] == 200_000
    assert stored.config_snapshot["version"] == "m03-pilot-v1"
    assert stored.t_idle_seconds == 120

    changed = _payload(
        frame.pk,
        event_id,
        started_at=T0.isoformat(),
        ended_at=(T0 + timedelta(seconds=600)).isoformat(),
        gaps=[_wire(100, 160, "blur")],
    )
    conflict = api.post("/api/effort-events/", changed, format="json")
    assert conflict.status_code == 409 and EffortEvent.objects.count() == 1


@override_settings(EFFORT_IDLE_POLICY=POLICY)
def test_stale_policy_version_is_rejected_and_nothing_is_stored():
    reviewer = _user("stale", Role.REVIEWER, 42)
    frame = _frame(reviewer)
    response = _client(reviewer).post(
        "/api/effort-events/", _payload(frame.pk, policy_version="old-v0"), format="json"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "POLICY_VERSION_MISMATCH"
    assert not EffortEvent.objects.exists()


@override_settings(EFFORT_IDLE_POLICY=POLICY)
def test_gap_outside_event_and_each_consumer_activity_are_validated_and_stored():
    reviewer = _user("consumers", Role.REVIEWER, 42)
    frame = _frame(reviewer)
    api = _client(reviewer)
    bad = _payload(frame.pk, gaps=[_wire(-5, 10, "blur")])
    assert api.post("/api/effort-events/", bad, format="json").status_code == 400
    for activity in ("review_issue", "adjudicate", "recheck_verify"):
        ok = api.post("/api/effort-events/", _payload(frame.pk, activity=activity), format="json")
        assert ok.status_code == 202
    assert sorted(EffortEvent.objects.values_list("activity", flat=True)) == [
        "adjudicate",
        "recheck_verify",
        "review_issue",
    ]
