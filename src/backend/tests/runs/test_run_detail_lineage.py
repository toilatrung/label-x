"""M03-R05/R10 integration: D05 lineage on Run detail and the registered review-policy URL."""

import pytest
from django.test import override_settings

from tests.review.test_queue_lease import client, world  # noqa: F401  (fixture)

PILOT = {
    "source": "DEC-019/P03",
    "decision_status": "approved_for_pilot",
    "t_idle_seconds": 120,
    "version": "m03-pilot-v1",
}


@pytest.mark.django_db
def test_run_detail_exposes_lineage_fields_but_list_stays_light(world):  # noqa: F811
    api = client(world["reviewer"])
    run_id = world["run"].pk
    detail = api.get(f"/api/runs/{run_id}/")
    assert detail.status_code == 200, detail.data
    for field in ("verification_lineage", "selected_final_sources", "operational_source"):
        assert field in detail.data
    operational = detail.data["operational_source"]
    assert "scope_complete" in operational and "blocked_reasons" in operational


@pytest.mark.django_db
@override_settings(
    REVIEW_LEASE_TTL_SECONDS=900,
    REVIEW_INCOMPLETE_RESERVATION_SECONDS=300,
    EFFORT_IDLE_POLICY=PILOT,
)
def test_review_policy_registered_in_root_urlconf(world):  # noqa: F811
    response = client(world["reviewer"]).get("/api/review-policy/?dataset_id=42")
    assert response.status_code == 200, response.data
    assert response.data["lease_ttl_seconds"] == 900
    assert response.data["resume_reservation_seconds"] == 300
    assert response.data["idle_threshold_seconds"] == 120
    assert response.data["policy_version"] == "m03-pilot-v1"
