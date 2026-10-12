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


# ---------------------------------------------------------------------------
# AC audit supplement: tests added by #246 audit to fill evidence gaps
# ---------------------------------------------------------------------------


@override_settings(EFFORT_IDLE_POLICY=POLICY)
def test_effort_accepted_after_lease_complete_documents_client_responsibility(world) -> None:
    """AC-1 evidence: server records effort even after frame complete.

    By design (DEC-019/P03, PR #254) effort is client-side telemetry.
    The server does NOT enforce lease state; the client is responsible
    for stopping effort recording when lease ends (complete/expiry/lost).
    This test documents that design choice.
    Data: tổng hợp (synthetic test fixtures).
    """
    api = _client(world["reviewer"])
    claim = api.post("/api/queues/risk/next/", {"run_id": world["run"].pk}, format="json")
    assert claim.status_code == 200
    lease_id = claim.data["lease"]["id"]
    frame_id = claim.data["frame"]["id"]

    # Issue + decision to enable complete
    issue = api.post(
        "/api/issues/",
        {
            "frame_id": frame_id,
            "lease_id": lease_id,
            "family": "E1",
            "description": "Effort audit issue",
            "anchor": {
                "kind": "manual_region",
                "objects": [],
                "bbox": {"x1": 1, "y1": 1, "x2": 10, "y2": 10},
                "policy_version": "anchor-v1",
            },
        },
        format="json",
    )
    assert issue.status_code == 201
    api.post(
        f"/api/issues/{issue.data['id']}/decisions/",
        {
            "lease_id": lease_id,
            "action": "confirm",
            "revision": world["run"].snapshot.revision_sha256,
            "family": "E1",
            "severity": "medium",
        },
        format="json",
    )

    # Complete the frame
    completed = api.post(f"/api/frames/{frame_id}/complete/", {"lease_id": lease_id}, format="json")
    assert completed.status_code == 200

    # Effort event AFTER complete — server still accepts (by design)
    payload = _payload(
        frame_id,
        started_at=T0.isoformat(),
        ended_at=(T0 + timedelta(seconds=120)).isoformat(),
    )
    after_complete = api.post("/api/effort-events/", payload, format="json")
    assert after_complete.status_code == 202
    assert after_complete.data["accepted"] == 1
    assert EffortEvent.objects.filter(frame_id=frame_id).count() == 1


@override_settings(EFFORT_IDLE_POLICY=POLICY)
def test_adjudicate_events_stored_separately_for_kpi_filtering() -> None:
    """AC-2 evidence: adjudicate activity is filterable from KPI-2b numerator.

    Stores review_issue and adjudicate events, then proves that a simple
    .exclude(activity="adjudicate") query yields only reviewer-confirm
    events suitable for KPI-2b numerator.
    Data: tổng hợp (synthetic test fixtures).
    """
    reviewer = _user("kpi-filter", Role.REVIEWER, 42)
    frame = _frame(reviewer)
    api = _client(reviewer)

    # Record review_issue (counts toward KPI-2b)
    review_payload = _payload(
        frame.pk,
        activity="review_issue",
        started_at=T0.isoformat(),
        ended_at=(T0 + timedelta(seconds=120)).isoformat(),
    )
    assert api.post("/api/effort-events/", review_payload, format="json").status_code == 202

    # Record adjudicate (MUST NOT count toward KPI-2b)
    adj_payload = _payload(
        frame.pk,
        activity="adjudicate",
        started_at=(T0 + timedelta(seconds=200)).isoformat(),
        ended_at=(T0 + timedelta(seconds=320)).isoformat(),
    )
    assert api.post("/api/effort-events/", adj_payload, format="json").status_code == 202

    # Total stored
    assert EffortEvent.objects.filter(actor=reviewer).count() == 2

    # KPI-2b query: exclude adjudicate
    kpi_qs = EffortEvent.objects.filter(actor=reviewer).exclude(activity="adjudicate")
    assert kpi_qs.count() == 1
    assert kpi_qs.first().activity == "review_issue"


@override_settings(EFFORT_IDLE_POLICY=POLICY)
def test_view_frame_activity_stored_for_workspace_tracking() -> None:
    """AC-2 evidence: view_frame activity records workspace viewing time.
    Data: tổng hợp (synthetic test fixtures).
    """
    reviewer = _user("workspace", Role.REVIEWER, 42)
    frame = _frame(reviewer)
    payload = _payload(
        frame.pk,
        activity="view_frame",
        started_at=T0.isoformat(),
        ended_at=(T0 + timedelta(seconds=60)).isoformat(),
    )
    resp = _client(reviewer).post("/api/effort-events/", payload, format="json")
    assert resp.status_code == 202
    stored = EffortEvent.objects.get()
    assert stored.activity == "view_frame"
    assert stored.actor == reviewer
    assert stored.frame_id == frame.pk
    assert stored.active_ms == 60_000
    assert stored.config_source == "DEC-019/P03"


@override_settings(EFFORT_IDLE_POLICY=POLICY)
def test_config_snapshot_records_full_policy_provenance() -> None:
    """AC-4 evidence: config_snapshot captures all policy fields and lifecycle details.

    Proves the stored event records source, decision_status, version,
    t_idle_seconds, and lifecycle breakdown — sufficient for audit trail.
    Data: tổng hợp (synthetic test fixtures).
    """
    reviewer = _user("provenance", Role.REVIEWER, 42)
    frame = _frame(reviewer)
    payload = _payload(
        frame.pk,
        started_at=T0.isoformat(),
        ended_at=(T0 + timedelta(seconds=300)).isoformat(),
        gaps=[_wire(50, 200), _wire(180, 220, "blur")],
        policy_version="m03-pilot-v1",
    )
    resp = _client(reviewer).post("/api/effort-events/", payload, format="json")
    assert resp.status_code == 202
    stored = EffortEvent.objects.get()
    snap = stored.config_snapshot

    # Policy provenance
    assert snap["source"] == "DEC-019/P03"
    assert snap["decision_status"] == "approved_for_pilot"
    assert snap["t_idle_seconds"] == 120
    assert snap["version"] == "m03-pilot-v1"

    # Lifecycle details
    lifecycle = snap["lifecycle"]
    assert lifecycle["wall_ms"] == 300_000
    assert lifecycle["excluded_ms"] > 0
    assert isinstance(lifecycle["gaps"], list)
    assert len(lifecycle["gaps"]) == 2

    # Stored fields match policy
    assert stored.t_idle_seconds == 120
    assert stored.config_source == "DEC-019/P03"
    assert stored.active_ms == 300_000 - lifecycle["excluded_ms"]


def test_policy_reads_from_settings_defaults_not_fixture() -> None:
    """AC-4 evidence: current_idle_policy() reads from Django settings.

    Without @override_settings, it reads the production defaults
    configured in settings.py (DEC-019/P03 pilot values).
    Policy pilot values are NOT scientific acceptance values (DEC-019).
    Data: tổng hợp (synthetic test, reads live settings).
    """
    from effort.services import current_idle_policy

    policy = current_idle_policy()
    # Settings default: source=DEC-019/P03, t_idle_seconds=120, version=pilot-1
    assert policy["source"] == "DEC-019/P03"
    assert policy["t_idle_seconds"] == 120
    assert policy["version"] == "pilot-1"
    assert policy["decision_status"] == "approved_for_pilot"
    # Not a fixture — reads from settings.EFFORT_IDLE_POLICY directly
    assert isinstance(policy, dict)
