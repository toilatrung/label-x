"""M03-R08 D04: GET /api/rework/ and /api/rework/{id}/ (synthetic DB fixtures)."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from review.models import ReworkRequest
from tests.review.test_finalization import _resolved_scope
from tests.review.test_queue_lease import world  # noqa: F401

pytest_plugins = ["tests.review.test_queue_lease"]


def _client(user: User) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=user)
    return api


@pytest.fixture
def scope(world):  # noqa: F811
    _issue, _fixed, verification = _resolved_scope(world)
    return {**world, "rework": verification.rework}


@pytest.mark.django_db
def test_reviewer_lists_dataset_with_counts_independent_of_filter(scope):
    api = _client(scope["reviewer"])
    body = api.get("/api/rework/?dataset_id=42").json()
    assert [row["id"] for row in body["results"]] == [scope["rework"].pk]
    assert body["counts"] == {
        "fix_pending": 0,
        "recheck_pending": 0,
        "resolved": 1,
        "reopened": 0,
    }
    row = body["results"][0]
    assert row["dataset_id"] == 42 and row["frame_id"] == scope["rework"].issue.frame_review_id
    assert row["submitted_at"] is not None and row["cvat_deep_link"]

    filtered = api.get("/api/rework/?dataset_id=42&status=fix_pending").json()
    assert filtered["results"] == [] and filtered["counts"]["resolved"] == 1
    assert api.get("/api/rework/?dataset_id=42&status=bogus").status_code == 400


@pytest.mark.django_db
def test_annotator_sees_only_own_and_foreign_detail_is_404(scope):
    other_annotator = User.objects.create_user("annotator-other")
    RoleAssignment.objects.create(user=other_annotator, role=Role.ANNOTATOR, dataset_id=42)
    own = _client(scope["author"])
    assert [r["id"] for r in own.get("/api/rework/?dataset_id=42").json()["results"]] == [
        scope["rework"].pk
    ]
    assert own.get(f"/api/rework/{scope['rework'].pk}/").status_code == 200

    foreign = _client(other_annotator)
    assert foreign.get("/api/rework/?dataset_id=42").json()["results"] == []
    assert foreign.get(f"/api/rework/{scope['rework'].pk}/").status_code == 404


@pytest.mark.django_db
def test_missing_scope_or_unknown_id_is_rejected(scope):
    outsider = User.objects.create_user("reviewer-other-dataset")
    RoleAssignment.objects.create(user=outsider, role=Role.REVIEWER, dataset_id=7)
    api = _client(outsider)
    assert api.get("/api/rework/?dataset_id=42").status_code == 403
    assert api.get(f"/api/rework/{scope['rework'].pk}/").status_code == 403
    assert _client(scope["reviewer"]).get("/api/rework/999999/").status_code == 404
    assert _client(scope["reviewer"]).get("/api/rework/").status_code == 403


@pytest.mark.django_db
def test_cursor_pages_are_stable_and_reads_do_not_mutate(scope, monkeypatch):
    template = scope["rework"]
    for _ in range(2):
        ReworkRequest.objects.create(
            issue=template.issue,
            annotator=template.annotator,
            created_by=template.created_by,
            status=ReworkRequest.Status.REOPENED,
            instruction="again",
            severity=template.severity,
            cvat_deep_link=template.cvat_deep_link,
            original_revision="r",
            due_at=template.due_at,
        )
    monkeypatch.setattr("review.rework_read_views.ReworkCursorPagination.page_size", 2)
    api = _client(scope["reviewer"])
    before = list(ReworkRequest.objects.values_list("pk", "updated_at", "status"))
    first = api.get("/api/rework/?dataset_id=42").json()
    second = api.get(first["next"]).json()
    ids = [r["id"] for r in first["results"]] + [r["id"] for r in second["results"]]
    assert len(ids) == 3 and len(set(ids)) == 3 and second["next"] is None
    assert second["counts"]["reopened"] == 2
    assert before == list(ReworkRequest.objects.values_list("pk", "updated_at", "status"))


@pytest.mark.django_db
def test_post_create_route_still_dispatches(scope):
    response = _client(scope["reviewer"]).post("/api/rework/", {}, format="json")
    assert response.status_code in (400, 403, 404)  # reaches ReworkCreateView, not 405
