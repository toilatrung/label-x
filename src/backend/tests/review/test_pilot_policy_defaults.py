"""Pilot policy defaults (DEC-019 P02/P03: 900 s lease, 300 s resume, 120 s idle) via the real API.

`tests/review/test_queue_lease.py` pins 60/120 only for its own tests (explicit
`approved_test_policy` fixture). Nothing here overrides settings, and time is moved by editing the
stored `Lease.expires_at`, never by patching a clock.
"""

from datetime import timedelta

import pytest
from django.conf import settings as django_settings
from django.utils import timezone

from review.models import FrameReview, Lease
from tests.review.test_queue_lease import client, next_url, persist_manual_decision

pytest_plugins = ["tests.review.test_queue_lease"]


def _claim(user, run_id):
    response = client(user).post(next_url(), {"run_id": run_id}, format="json")
    assert response.status_code == 200, response.data
    return Lease.objects.get(pk=response.data["lease"]["id"])


def test_other_modules_see_pilot_settings_not_the_short_test_policy():
    assert django_settings.REVIEW_LEASE_TTL_SECONDS == 900
    assert django_settings.REVIEW_INCOMPLETE_RESERVATION_SECONDS == 300
    assert django_settings.EFFORT_IDLE_POLICY["t_idle_seconds"] == 120
    assert django_settings.EFFORT_IDLE_POLICY["version"] == "pilot-1"


@pytest.mark.django_db
def test_policy_endpoint_exposes_pilot_values(world):
    body = client(world["reviewer"]).get("/api/review-policy/").json()
    assert body["lease_ttl_seconds"] == 900
    assert body["resume_reservation_seconds"] == 300
    assert body["idle_threshold_seconds"] == 120
    assert body["policy_version"] == "pilot-1"


@pytest.mark.django_db
def test_claim_grants_exactly_900_seconds_and_renew_extends_by_900(world):
    before = timezone.now()
    lease = _claim(world["reviewer"], world["run"].pk)
    after = timezone.now()
    assert before + timedelta(seconds=900) <= lease.expires_at <= after + timedelta(seconds=900)
    # t = 899 s after claim: stored expiry is one second away -> renew is still allowed.
    Lease.objects.filter(pk=lease.pk).update(expires_at=timezone.now() + timedelta(seconds=1))
    renewed = client(world["reviewer"]).post(f"/api/leases/{lease.pk}/renew/", {}, format="json")
    assert renewed.status_code == 200, renewed.data
    lease.refresh_from_db()
    now = timezone.now()
    assert now + timedelta(seconds=898) <= lease.expires_at <= now + timedelta(seconds=900)


@pytest.mark.django_db
def test_abandoned_lease_is_expired_after_900_seconds(world):
    lease = _claim(world["reviewer"], world["run"].pk)
    # t = 901 s after claim.
    Lease.objects.filter(pk=lease.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    response = client(world["reviewer"]).post(f"/api/leases/{lease.pk}/renew/", {}, format="json")
    assert response.status_code == 409 and response.data["code"] == "LEASE_CONFLICT"
    lease.refresh_from_db()
    assert lease.closed_at is not None
    frame = FrameReview.objects.get(pk=lease.frame_review_id)
    assert frame.state == FrameReview.State.UNREVIEWED  # no decision: back to the queue


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("elapsed_after_expiry", "other_status", "previous_resumes"),
    [(299, 204, True), (301, 200, False)],
)
def test_incomplete_reservation_is_300_seconds(
    world, elapsed_after_expiry, other_status, previous_resumes
):
    lease = _claim(world["reviewer"], world["run"].pk)
    persist_manual_decision(world, lease.pk)
    expired_at = timezone.now() - timedelta(seconds=elapsed_after_expiry)
    Lease.objects.filter(pk=lease.pk).update(expires_at=expired_at)

    other = client(world["other"]).post(next_url(), {"run_id": world["run"].pk}, format="json")
    assert other.status_code == other_status, other.data
    frame = FrameReview.objects.get(pk=lease.frame_review_id)
    if other_status == 200:
        assert other.data["resumed"] is False  # reservation over: another reviewer took over
        assert other.data["lease"]["holder_user_id"] == world["other"].pk
        return
    assert frame.state == FrameReview.State.INCOMPLETE
    assert frame.incomplete_since == expired_at
    assert frame.previous_reviewer_id == world["reviewer"].pk
    owner = client(world["reviewer"]).post(next_url(), {"run_id": world["run"].pk}, format="json")
    assert owner.status_code == 200 and owner.data["resumed"] is previous_resumes
