"""#242 follow-up: read-only per-round rework timeline (synthetic fixtures)."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from accounts.models import Role, RoleAssignment
from review import rework_service
from review.models import FrameReview, ReworkRequest
from tests.review.test_queue_lease import client
from tests.review.test_rework import (  # noqa: F401
    _run_for,
    _submit,
    _verify,
    changed_snapshot,
    confirmed,
    create_request,
    cvat_base_url,
    second_snapshot,
)

pytest_plugins = ["tests.review.test_queue_lease"]


@pytest.fixture
def two_rounds(confirmed, world, monkeypatch):  # noqa: F811
    rework = ReworkRequest.objects.get(pk=create_request(confirmed, world).data["id"])
    first, second = changed_snapshot(world), second_snapshot(world)
    runs = {first.pk: _run_for(world, first), second.pk: _run_for(world, second)}
    current = {"snapshot": first}
    monkeypatch.setattr(
        rework_service,
        "_build_recheck_artifacts",
        lambda **_kwargs: (current["snapshot"], runs[current["snapshot"].pk]),
    )
    assert _submit(world, rework, first).status_code == 202
    assert _verify(world, rework, first, False).status_code == 200
    current["snapshot"] = second
    assert _submit(world, rework, second).status_code == 202
    return {"rework": rework, "first": first, "second": second, "runs": runs, **world}


def _detail(user, rework):
    return client(user).get(f"/api/rework/{rework.pk}/")


@pytest.mark.django_db
def test_timeline_lists_rounds_in_order_with_results(two_rounds):
    rework, first, second = two_rounds["rework"], two_rounds["first"], two_rounds["second"]
    body = _detail(two_rounds["reviewer"], rework).json()
    assert body["status"] == "recheck_pending" and body["round_count"] == 2
    assert body["review_state"] == FrameReview.State.AWAITING_FOLLOWUP
    one, two = body["timeline"]
    assert (one["round"], one["revision"], one["result_status"]) == (
        1,
        first.revision_sha256,
        "fix_pending",
    )
    assert one["verification"]["outcome"] == "fail"
    assert one["verification"]["reason"] == "Still wrong"
    assert one["verification"]["verifier_user_id"] == two_rounds["other"].pk
    assert one["recheck_run_id"] == two_rounds["runs"][first.pk].pk
    assert (two["round"], two["revision"], two["result_status"]) == (
        2,
        second.revision_sha256,
        "recheck_pending",
    )
    assert two["verification"] is None and two["submitted_at"] is not None

    assert _verify(two_rounds, rework, second, True).status_code == 200
    final = _detail(two_rounds["reviewer"], rework).json()
    assert final["status"] == "resolved"
    assert [r["result_status"] for r in final["timeline"]] == ["fix_pending", "resolved"]
    assert final["timeline"][1]["verification"]["outcome"] == "pass"


@pytest.mark.django_db
def test_list_reports_round_count_and_annotator_scope(two_rounds):
    reviewer_list = client(two_rounds["reviewer"]).get("/api/rework/?dataset_id=42").json()
    assert [row["round_count"] for row in reviewer_list["results"]] == [2]
    assert "timeline" not in reviewer_list["results"][0]
    own = client(two_rounds["author"])
    assert own.get(f"/api/rework/{two_rounds['rework'].pk}/").json()["round_count"] == 2

    stranger = User.objects.create_user("annotator-stranger")
    RoleAssignment.objects.create(user=stranger, role=Role.ANNOTATOR, dataset_id=42)
    assert _detail(stranger, two_rounds["rework"]).status_code == 404
    outsider = User.objects.create_user("reviewer-elsewhere")
    RoleAssignment.objects.create(user=outsider, role=Role.REVIEWER, dataset_id=7)
    assert _detail(outsider, two_rounds["rework"]).status_code == 403


@pytest.mark.django_db
def test_get_does_not_write(two_rounds):
    from audit.models import AuditEvent
    from review.models import ReworkRecheck, ReworkVerification

    before = (
        list(ReworkRequest.objects.values_list("pk", "updated_at", "status")),
        ReworkRecheck.objects.count(),
        ReworkVerification.objects.count(),
        AuditEvent.objects.count(),
    )
    for _ in range(2):
        assert _detail(two_rounds["reviewer"], two_rounds["rework"]).status_code == 200
        assert client(two_rounds["reviewer"]).get("/api/rework/?dataset_id=42").status_code == 200
    assert before == (
        list(ReworkRequest.objects.values_list("pk", "updated_at", "status")),
        ReworkRecheck.objects.count(),
        ReworkVerification.objects.count(),
        AuditEvent.objects.count(),
    )


@pytest.mark.django_db
def test_legacy_verification_without_recheck_row_still_listed(world):
    from tests.review.test_finalization import _resolved_scope

    _issue, fixed, verification = _resolved_scope(world)
    body = _detail(world["reviewer"], verification.rework).json()
    assert body["round_count"] == 1
    [round_one] = body["timeline"]
    assert round_one["revision"] == fixed.revision_sha256
    assert round_one["submitted_at"] is None and round_one["result_status"] == "resolved"
