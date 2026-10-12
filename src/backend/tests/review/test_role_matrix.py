"""Role-matrix verification for D04 rework and D05 run detail endpoints (Issue #244).

Endpoints verified:
- GET /api/rework/ (dataset_id required, status, cursor, counts, round_count)
- GET /api/rework/{id}/ (review_state, timeline[])
- GET /api/runs/{id}/ (verification_lineage, selected_final_sources, operational_source)

Role matrix:
- annotator: assigned only; 404 for foreign assigned object; 403 for missing dataset scope
- reviewer: scoped by dataset_id (allowed within assigned dataset; 403 outside)
- verifier (reviewer/super_admin): different from author/editor
- qa_lead: allowed within assigned dataset; 403 outside
- qc_admin: system-wide reader on runs; 403 on rework without dataset assignment
- outsider / other roles (product_owner, data_model_owner, no role): 403 / denied
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from tests.review.test_finalization import _resolved_scope
from tests.review.test_queue_lease import world  # noqa: F401

pytest_plugins = ["tests.review.test_queue_lease"]


def _client_for(user: User) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=user)
    return api


@pytest.fixture
def role_matrix_world(world):  # noqa: F811
    _issue, _fixed, verification = _resolved_scope(world)
    rework = verification.rework
    dataset_id = 42

    # 1. Annotator (assigned): world["author"] has Role.ANNOTATOR on dataset 42
    annotator_assigned = world["author"]

    # 2. Annotator (unassigned on same dataset):
    annotator_foreign = User.objects.create_user("annotator_foreign_matrix")
    RoleAssignment.objects.create(
        user=annotator_foreign, role=Role.ANNOTATOR, dataset_id=dataset_id
    )

    # 3. Annotator (different dataset):
    annotator_other_ds = User.objects.create_user("annotator_other_ds_matrix")
    RoleAssignment.objects.create(user=annotator_other_ds, role=Role.ANNOTATOR, dataset_id=99)

    # 4. Reviewer (in dataset): world["reviewer"] has Role.REVIEWER on dataset 42
    reviewer_in_ds = world["reviewer"]

    # 5. Reviewer (different dataset):
    reviewer_other_ds = User.objects.create_user("reviewer_other_ds_matrix")
    RoleAssignment.objects.create(user=reviewer_other_ds, role=Role.REVIEWER, dataset_id=99)

    # 6. QA Lead (in dataset):
    qa_lead_in_ds = User.objects.create_user("qalead_matrix")
    RoleAssignment.objects.create(user=qa_lead_in_ds, role=Role.QA_LEAD, dataset_id=dataset_id)

    # 7. QA Lead (different dataset):
    qa_lead_other_ds = User.objects.create_user("qalead_other_ds_matrix")
    RoleAssignment.objects.create(user=qa_lead_other_ds, role=Role.QA_LEAD, dataset_id=99)

    # 8. QC Admin (system-wide):
    qc_admin_global = User.objects.create_user("qcadmin_matrix")
    RoleAssignment.objects.create(user=qc_admin_global, role=Role.QC_ADMIN, dataset_id=None)

    # 9. Super Admin:
    super_admin = User.objects.create_user("superadmin_matrix", is_superuser=True)
    RoleAssignment.objects.create(user=super_admin, role=Role.SUPER_ADMIN, dataset_id=None)

    # 10. Outsider (Product Owner / Data Model Owner / Unassigned):
    po_user = User.objects.create_user("po_matrix")
    RoleAssignment.objects.create(user=po_user, role=Role.PRODUCT_OWNER, dataset_id=dataset_id)

    dmo_user = User.objects.create_user("dmo_matrix")
    RoleAssignment.objects.create(user=dmo_user, role=Role.DATA_MODEL_OWNER, dataset_id=dataset_id)

    outsider_none = User.objects.create_user("outsider_no_role")

    return {
        **world,
        "rework": rework,
        "dataset_id": dataset_id,
        "annotator_assigned": annotator_assigned,
        "annotator_foreign": annotator_foreign,
        "annotator_other_ds": annotator_other_ds,
        "reviewer_in_ds": reviewer_in_ds,
        "reviewer_other_ds": reviewer_other_ds,
        "qa_lead_in_ds": qa_lead_in_ds,
        "qa_lead_other_ds": qa_lead_other_ds,
        "qc_admin_global": qc_admin_global,
        "super_admin": super_admin,
        "po_user": po_user,
        "dmo_user": dmo_user,
        "outsider_none": outsider_none,
    }


@pytest.mark.django_db
def test_rework_list_role_matrix(role_matrix_world):
    ds = role_matrix_world["dataset_id"]
    rework_id = role_matrix_world["rework"].pk

    # 1. Annotator assigned: sees own rework
    res = _client_for(role_matrix_world["annotator_assigned"]).get(f"/api/rework/?dataset_id={ds}")
    assert res.status_code == 200
    assert [r["id"] for r in res.data["results"]] == [rework_id]

    # 2. Annotator foreign (same dataset): sees 0 results (filtered to own)
    res = _client_for(role_matrix_world["annotator_foreign"]).get(f"/api/rework/?dataset_id={ds}")
    assert res.status_code == 200
    assert res.data["results"] == []

    # 3. Annotator other dataset: 403 OUT_OF_SCOPE
    res = _client_for(role_matrix_world["annotator_other_ds"]).get(f"/api/rework/?dataset_id={ds}")
    assert res.status_code == 403

    # 4. Reviewer in dataset: sees all rework in dataset
    res = _client_for(role_matrix_world["reviewer_in_ds"]).get(f"/api/rework/?dataset_id={ds}")
    assert res.status_code == 200
    assert [r["id"] for r in res.data["results"]] == [rework_id]

    # 5. Reviewer other dataset: 403 OUT_OF_SCOPE
    res = _client_for(role_matrix_world["reviewer_other_ds"]).get(f"/api/rework/?dataset_id={ds}")
    assert res.status_code == 403

    # 6. QA Lead in dataset: sees all rework in dataset
    res = _client_for(role_matrix_world["qa_lead_in_ds"]).get(f"/api/rework/?dataset_id={ds}")
    assert res.status_code == 200
    assert [r["id"] for r in res.data["results"]] == [rework_id]

    # 7. QA Lead other dataset: 403 OUT_OF_SCOPE
    res = _client_for(role_matrix_world["qa_lead_other_ds"]).get(f"/api/rework/?dataset_id={ds}")
    assert res.status_code == 403

    # 8. QC Admin global: QC_ADMIN is not in _READ_ROLES for rework -> 403 FORBIDDEN
    res = _client_for(role_matrix_world["qc_admin_global"]).get(f"/api/rework/?dataset_id={ds}")
    assert res.status_code == 403

    # 9. Super Admin: sees all rework
    res = _client_for(role_matrix_world["super_admin"]).get(f"/api/rework/?dataset_id={ds}")
    assert res.status_code == 200
    assert [r["id"] for r in res.data["results"]] == [rework_id]

    # 10. PO / DMO / Outsider: 403
    for u in (
        role_matrix_world["po_user"],
        role_matrix_world["dmo_user"],
        role_matrix_world["outsider_none"],
    ):
        res = _client_for(u).get(f"/api/rework/?dataset_id={ds}")
        assert res.status_code == 403


@pytest.mark.django_db
def test_rework_detail_role_matrix(role_matrix_world):
    rework_id = role_matrix_world["rework"].pk

    # 1. Annotator assigned: 200 OK
    res = _client_for(role_matrix_world["annotator_assigned"]).get(f"/api/rework/{rework_id}/")
    assert res.status_code == 200
    assert res.data["id"] == rework_id
    assert "review_state" in res.data and "timeline" in res.data

    # 2. Annotator foreign (same dataset): 404 NOT_FOUND (prevent object discovery)
    res = _client_for(role_matrix_world["annotator_foreign"]).get(f"/api/rework/{rework_id}/")
    assert res.status_code == 404
    assert res.data["code"] == "NOT_FOUND"

    # 3. Annotator other dataset: 403 OUT_OF_SCOPE
    res = _client_for(role_matrix_world["annotator_other_ds"]).get(f"/api/rework/{rework_id}/")
    assert res.status_code == 403

    # 4. Reviewer in dataset: 200 OK
    res = _client_for(role_matrix_world["reviewer_in_ds"]).get(f"/api/rework/{rework_id}/")
    assert res.status_code == 200
    assert res.data["id"] == rework_id

    # 5. Reviewer other dataset: 403 OUT_OF_SCOPE
    res = _client_for(role_matrix_world["reviewer_other_ds"]).get(f"/api/rework/{rework_id}/")
    assert res.status_code == 403

    # 6. QA Lead in dataset: 200 OK
    res = _client_for(role_matrix_world["qa_lead_in_ds"]).get(f"/api/rework/{rework_id}/")
    assert res.status_code == 200

    # 7. QA Lead other dataset: 403 OUT_OF_SCOPE
    res = _client_for(role_matrix_world["qa_lead_other_ds"]).get(f"/api/rework/{rework_id}/")
    assert res.status_code == 403

    # 8. QC Admin global: 403 FORBIDDEN (rework is scoped to annotator/reviewer/qa_lead/super_admin)
    res = _client_for(role_matrix_world["qc_admin_global"]).get(f"/api/rework/{rework_id}/")
    assert res.status_code == 403

    # 9. Super Admin: 200 OK
    res = _client_for(role_matrix_world["super_admin"]).get(f"/api/rework/{rework_id}/")
    assert res.status_code == 200

    # 10. PO / DMO / Outsider: 403
    for u in (
        role_matrix_world["po_user"],
        role_matrix_world["dmo_user"],
        role_matrix_world["outsider_none"],
    ):
        res = _client_for(u).get(f"/api/rework/{rework_id}/")
        assert res.status_code == 403


@pytest.mark.django_db
def test_run_detail_role_matrix(role_matrix_world):
    run_id = role_matrix_world["run"].pk

    # 1. Annotator: not in allowed_roles for runs (reviewer, qa_lead, qc_admin, super_admin) -> 403
    for ann in (
        role_matrix_world["annotator_assigned"],
        role_matrix_world["annotator_foreign"],
        role_matrix_world["annotator_other_ds"],
    ):
        res = _client_for(ann).get(f"/api/runs/{run_id}/")
        assert res.status_code == 403

    # 2. Reviewer in dataset: 200 OK, includes lineage fields
    res = _client_for(role_matrix_world["reviewer_in_ds"]).get(f"/api/runs/{run_id}/")
    assert res.status_code == 200
    assert "verification_lineage" in res.data
    assert "selected_final_sources" in res.data
    assert "operational_source" in res.data

    # 3. Reviewer other dataset: 403 OUT_OF_SCOPE
    res = _client_for(role_matrix_world["reviewer_other_ds"]).get(f"/api/runs/{run_id}/")
    assert res.status_code == 403

    # 4. QA Lead in dataset: 200 OK
    res = _client_for(role_matrix_world["qa_lead_in_ds"]).get(f"/api/runs/{run_id}/")
    assert res.status_code == 200

    # 5. QA Lead other dataset: 403 OUT_OF_SCOPE
    res = _client_for(role_matrix_world["qa_lead_other_ds"]).get(f"/api/runs/{run_id}/")
    assert res.status_code == 403

    # 6. QC Admin (global): 200 OK
    res = _client_for(role_matrix_world["qc_admin_global"]).get(f"/api/runs/{run_id}/")
    assert res.status_code == 200

    # 7. Super Admin: 200 OK
    res = _client_for(role_matrix_world["super_admin"]).get(f"/api/runs/{run_id}/")
    assert res.status_code == 200

    # 8. PO / DMO / Outsider: 403
    for u in (
        role_matrix_world["po_user"],
        role_matrix_world["dmo_user"],
        role_matrix_world["outsider_none"],
    ):
        res = _client_for(u).get(f"/api/runs/{run_id}/")
        assert res.status_code == 403
