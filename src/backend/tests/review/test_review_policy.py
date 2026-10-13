"""M03-R10 backend: versioned review-policy read (pilot values injected via settings only)."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import path
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from review.policy_views import ReviewPolicyView

urlpatterns = [path("api/review-policy/", ReviewPolicyView.as_view())]

PILOT = {
    "source": "DEC-019/P03",
    "decision_status": "approved_for_pilot",
    "t_idle_seconds": 120,
    "version": "m03-pilot-v1",
}


def _api(role: Role | None = Role.REVIEWER) -> APIClient:
    user = User.objects.create_user(f"policy-{role}")
    if role is not None:
        RoleAssignment.objects.create(user=user, role=role, dataset_id=42)
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.mark.django_db
@override_settings(
    ROOT_URLCONF="tests.review.test_review_policy",
    REVIEW_LEASE_TTL_SECONDS=900,
    REVIEW_INCOMPLETE_RESERVATION_SECONDS=300,
    EFFORT_IDLE_POLICY=PILOT,
)
def test_policy_read_returns_versioned_pilot_values():
    body = _api().get("/api/review-policy/").json()
    assert body["policy_version"] == "m03-pilot-v1"
    assert (body["lease_ttl_seconds"], body["resume_reservation_seconds"]) == (900, 300)
    assert body["idle_threshold_seconds"] == 120
    assert body["idle_gap_rule"] == "exclude_whole_gap_over_threshold"
    assert body["immediate_exclusion_reasons"] == ["blur", "hidden", "pause"]
    assert body["decision_status"] == "approved_for_pilot"


@pytest.mark.django_db
@override_settings(
    ROOT_URLCONF="tests.review.test_review_policy",
    REVIEW_LEASE_TTL_SECONDS=900,
    REVIEW_INCOMPLETE_RESERVATION_SECONDS=300,
    EFFORT_IDLE_POLICY={k: v for k, v in PILOT.items() if k != "version"},
)
def test_version_is_derived_and_changes_with_content():
    first = _api().get("/api/review-policy/").json()["policy_version"]
    assert first.startswith("sha256:")
    changed = {k: v for k, v in PILOT.items() if k != "version"} | {"t_idle_seconds": 90}
    with override_settings(EFFORT_IDLE_POLICY=changed):
        assert _api(Role.QA_LEAD).get("/api/review-policy/").json()["policy_version"] != first


@pytest.mark.django_db
@override_settings(
    ROOT_URLCONF="tests.review.test_review_policy",
    REVIEW_LEASE_TTL_SECONDS=None,
    REVIEW_INCOMPLETE_RESERVATION_SECONDS=300,
    EFFORT_IDLE_POLICY=PILOT,
)
def test_missing_value_fails_closed_instead_of_inventing_default():
    response = _api().get("/api/review-policy/")
    assert response.status_code == 503
    assert response.json()["code"] == "POLICY_NOT_CONFIGURED"


@pytest.mark.django_db
@override_settings(
    ROOT_URLCONF="tests.review.test_review_policy",
    REVIEW_LEASE_TTL_SECONDS=900,
    REVIEW_INCOMPLETE_RESERVATION_SECONDS=300,
    EFFORT_IDLE_POLICY={"source": "x", "t_idle_seconds": None},
)
def test_unset_idle_threshold_is_not_served():
    assert _api().get("/api/review-policy/").status_code == 503


@pytest.mark.django_db
@override_settings(
    ROOT_URLCONF="tests.review.test_review_policy",
    REVIEW_LEASE_TTL_SECONDS=900,
    REVIEW_INCOMPLETE_RESERVATION_SECONDS=300,
    EFFORT_IDLE_POLICY=PILOT,
)
def test_role_gate_and_authentication():
    assert _api(None).get("/api/review-policy/").status_code == 403
    assert APIClient().get("/api/review-policy/").status_code in (401, 403)
    assert _api(Role.ANNOTATOR).get("/api/review-policy/").status_code == 200
