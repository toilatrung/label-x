"""MBE-01: reference, KPI evaluation, gate, waiver và report theo contract.

Giới hạn: không có GT thật; KPI-1/2/2b/G-1 phải là not_checked, không được bịa số.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from accounts.models import Role, RoleAssignment
from runs.models import Reference
from tests.review.test_queue_lease import client

pytest_plugins = ["tests.review.test_queue_lease"]

CHECKSUM = "a" * 64


def _user(name: str, role: Role) -> User:
    user = User.objects.create_user(name)
    RoleAssignment.objects.create(user=user, role=role, dataset_id=42)
    return user


@pytest.fixture
def qa(world):
    return {"a": _user("qa-a", Role.QA_LEAD), "b": _user("qa-b", Role.QA_LEAD)}


def _post(user, url, body=None, key="k1"):
    return client(user).post(url, body or {}, format="json", HTTP_IDEMPOTENCY_KEY=key)


def _create_reference(world, user, key="ref-1"):
    return _post(
        user,
        "/api/references/",
        {
            "snapshot_id": world["run"].snapshot_id,
            "gt_source": "bdd100k",
            "gt_checksum": CHECKSUM,
            "mapping_version": "m1",
        },
        key,
    )


@pytest.mark.django_db
def test_reference_create_replay_conflict_and_roles(world, qa):
    first = _create_reference(world, qa["a"])
    assert first.status_code == 201, first.data
    assert first.data["status"] == "draft" and first.data["locked_by"] is None
    assert _create_reference(world, qa["a"]).data["id"] == first.data["id"]
    other_payload = _post(
        qa["a"],
        "/api/references/",
        {
            "snapshot_id": world["run"].snapshot_id,
            "gt_source": "x",
            "gt_checksum": CHECKSUM,
            "mapping_version": "m2",
        },
        "ref-1",
    )
    assert other_payload.status_code == 409
    assert other_payload.data["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert Reference.objects.count() == 1
    assert _create_reference(world, world["reviewer"], "ref-x").status_code == 403
    bad = _post(
        qa["a"],
        "/api/references/",
        {"snapshot_id": world["run"].snapshot_id, "gt_checksum": "zz"},
        "ref-bad",
    )
    assert bad.status_code == 400
    assert (
        _post(qa["a"], "/api/references/", {}, "").status_code == 404
    )  # không xác định được dataset


@pytest.mark.django_db
def test_reference_lock_needs_other_person_and_is_idempotent(world, qa):
    ref_id = _create_reference(world, qa["a"]).data["id"]
    same = _post(qa["a"], f"/api/references/{ref_id}/lock/")
    assert same.status_code == 403 and same.data["code"] == "SAME_REQUESTER_APPROVER"
    locked = _post(qa["b"], f"/api/references/{ref_id}/lock/")
    assert locked.status_code == 200 and locked.data["status"] == "locked"
    assert locked.data["locked_by"] == qa["b"].pk
    assert _post(qa["a"], f"/api/references/{ref_id}/lock/").data["status"] == "locked"
    assert _post(qa["b"], "/api/references/99999/lock/").status_code in (403, 404)


def _locked_reference(world, qa):
    ref_id = _create_reference(world, qa["a"]).data["id"]
    assert _post(qa["b"], f"/api/references/{ref_id}/lock/").status_code == 200
    return ref_id


def _evaluate(world, user, ref_id, key="ev-1", **over):
    body = {
        "snapshot_id": world["run"].snapshot_id,
        "run_id": world["run"].pk,
        "reference_id": ref_id,
        "score_version": "score-v0",
        "parameters": {},
        **over,
    }
    return _post(user, "/api/evaluations/", body, key)


@pytest.mark.django_db
def test_evaluation_requires_locked_reference_and_matching_snapshot(world, qa):
    draft = _create_reference(world, qa["a"]).data["id"]
    assert _evaluate(world, qa["a"], draft).status_code == 409
    ref_id = _locked_reference_from(world, qa, draft)
    mismatch = _evaluate(world, qa["a"], ref_id, key="ev-m", snapshot_id=999999)
    assert mismatch.status_code in (403, 404, 422)


def _locked_reference_from(world, qa, ref_id):
    assert _post(qa["b"], f"/api/references/{ref_id}/lock/").status_code == 200
    return ref_id


@pytest.mark.django_db
def test_evaluation_insufficient_sample_idempotent_and_no_fake_kpi(world, qa):
    ref_id = _locked_reference(world, qa)
    first = _evaluate(world, qa["a"], ref_id)
    assert first.status_code == 202, first.data
    assert first["Location"] == f"/api/evaluations/{first.data['id']}/"
    assert first.data["status"] == "insufficient_sample"
    assert first.data["leakage_check"] == "not_checked"
    metrics = first.data["metrics"]
    assert set(metrics) == {"KPI-1", "KPI-2", "KPI-2b", "G-1", "G-2", "G-3", "G-4", "P-1", "C-1"}
    assert metrics["P-1"]["status"] == "not_checked"
    assert metrics["C-1"]["status"] == "not_checked"
    assert all(metrics[k]["value"] is None for k in ("KPI-1", "KPI-2", "KPI-2b", "G-1"))
    assert metrics["KPI-2"]["status"] == "insufficient_sample"
    assert _evaluate(world, qa["a"], ref_id).data["id"] == first.data["id"]
    reused = _evaluate(world, qa["a"], ref_id, parameters={"e_min": 5})
    assert reused.status_code == 409 and reused.data["code"] == "IDEMPOTENCY_KEY_REUSED"
    bad = _evaluate(world, qa["a"], ref_id, key="ev-bad", parameters={"e_min": 0})
    assert bad.status_code == 400
    poll = client(qa["a"]).get(f"/api/evaluations/{first.data['id']}/")
    assert poll.status_code == 200 and poll.data["id"] == first.data["id"]
    assert client(world["reviewer"]).get(f"/api/evaluations/{first.data['id']}/").status_code == 403


@pytest.mark.django_db
def test_gate_waiver_flow_and_report(world, qa):
    run_id = world["run"].pk
    gate = client(qa["a"]).get(f"/api/runs/{run_id}/gate/")
    assert gate.status_code == 200, gate.data
    assert [c["name"] for c in gate.data["conditions"]] == [
        "coverage",
        "open_critical_issues",
        "rework_verified",
        "residual",
        "agreement",
    ]
    assert gate.data["status"] == "failed" and gate.data["source_run_id"] == run_id
    by_name = {c["name"]: c for c in gate.data["conditions"]}
    assert by_name["residual"]["status"] == "not_checked"  # chưa có mẫu random audit
    assert by_name["open_critical_issues"]["status"] == "passed"

    expires = (timezone.now() + timedelta(days=3)).isoformat()
    body = {
        "run_id": run_id,
        "condition": "agreement",
        "reason": "thiếu mẫu",
        "evidence": "ghi chú",
        "expires_at": expires,
    }
    bad = _post(world["reviewer"], "/api/waivers/", {**body, "condition": "residual"}, "w-bad")
    assert bad.status_code == 422
    past = _post(
        world["reviewer"],
        "/api/waivers/",
        {**body, "expires_at": (timezone.now() - timedelta(days=1)).isoformat()},
        "w-past",
    )
    assert past.status_code == 422
    created = _post(world["reviewer"], "/api/waivers/", body, "w-1")
    assert created.status_code == 201 and created.data["status"] == "pending"
    assert _post(world["reviewer"], "/api/waivers/", body, "w-1").data["id"] == created.data["id"]
    waiver_id = created.data["id"]
    decision = {"approved": True, "reason": "đồng ý"}
    # Chưa duyệt thì chưa có hiệu lực.
    pending = client(qa["a"]).get(f"/api/runs/{run_id}/gate/")
    assert {c["name"]: c for c in pending.data["conditions"]}["agreement"]["status"] != "waived"
    approved = _post(qa["a"], f"/api/waivers/{waiver_id}/approve/", decision, "a-1")
    assert approved.status_code == 200 and approved.data["status"] == "approved"
    assert approved.data["approved_by"] == qa["a"].pk
    again = _post(qa["a"], f"/api/waivers/{waiver_id}/approve/", decision, "a-1")
    assert again.status_code == 200
    assert _post(qa["b"], f"/api/waivers/{waiver_id}/approve/", decision, "a-2").status_code == 409
    waived = client(qa["a"]).get(f"/api/runs/{run_id}/gate/")
    agreement = {c["name"]: c for c in waived.data["conditions"]}["agreement"]
    assert agreement["status"] == "waived" and agreement["waiver_id"] == waiver_id
    assert waived.data["status"] == "failed"  # chưa có run cuối hợp lệ

    ref_id = _locked_reference(world, qa)
    ev = _evaluate(world, qa["a"], ref_id, key="ev-r")
    report = client(qa["a"]).get(f"/api/reports/{ev.data['id']}/")
    assert report.status_code == 200, report.data
    assert report.data["source_run_id"] == run_id and report.data["reference_id"] == ref_id
    assert set(report.data["metrics"]) == set(ev.data["metrics"])
    csv_resp = client(qa["a"]).get(f"/api/reports/{ev.data['id']}/?format=csv")
    assert csv_resp.status_code == 200 and csv_resp["Content-Type"].startswith("text/csv")
    assert b"KPI-1,insufficient_sample" in csv_resp.content
    assert client(qa["a"]).get(f"/api/reports/{ev.data['id']}/?format=pdf").status_code == 400
    assert client(qa["a"]).get(f"/api/reports/{ev.data['id']}/?format=xml").status_code == 400


@pytest.mark.django_db
def test_waiver_approver_cannot_be_requester_and_rejection(world, qa):
    run_id = world["run"].pk
    body = {
        "run_id": run_id,
        "condition": "coverage",
        "reason": "r",
        "evidence": "e",
        "expires_at": (timezone.now() + timedelta(days=1)).isoformat(),
    }
    waiver_id = _post(qa["a"], "/api/waivers/", body, "w-2").data["id"]
    decision = {"approved": True, "reason": "x"}
    own = _post(qa["a"], f"/api/waivers/{waiver_id}/approve/", decision, "o-1")
    assert own.status_code == 403 and own.data["code"] == "SAME_REQUESTER_APPROVER"
    rejected = _post(
        qa["b"], f"/api/waivers/{waiver_id}/approve/", {"approved": False, "reason": "no"}, "o-2"
    )
    assert rejected.status_code == 200 and rejected.data["status"] == "rejected"
    gate = client(qa["a"]).get(f"/api/runs/{run_id}/gate/")
    assert {c["name"]: c for c in gate.data["conditions"]}["coverage"]["status"] != "waived"


@pytest.mark.django_db
def test_global_super_admin_cannot_approve_own_waiver(world, qa):
    from audit.models import AuditEvent

    user = qa["a"]
    RoleAssignment.objects.create(user=user, role=Role.SUPER_ADMIN, dataset_id=None)
    response = _post(
        user,
        "/api/waivers/",
        {
            "run_id": world["run"].pk,
            "condition": "coverage",
            "reason": "Admin demo",
            "evidence": "Checked manually",
            "expires_at": (timezone.now() + timedelta(days=1)).isoformat(),
        },
        "admin-own-waiver",
    )
    assert response.status_code == 201, response.data
    waiver_id = response.data["id"]
    approved = _post(
        user,
        f"/api/waivers/{waiver_id}/approve/",
        {"approved": True, "reason": "Admin approval"},
        "admin-own-waiver-approve",
    )
    assert approved.status_code == 403, approved.data
    assert approved.data["code"] == "SAME_REQUESTER_APPROVER"
    assert not AuditEvent.objects.filter(action="waiver.approve", object_id=str(waiver_id)).exists()


# ---------------------------------------------------------------- BLOCKER-034 B-6: GET danh sách


def _get(user, url):
    return client(user).get(url)


@pytest.mark.django_db
def test_reference_list_scoped_by_dataset_filtered_by_status_newest_first(world, qa):
    draft = _create_reference(world, qa["a"], "ref-l1").data["id"]
    locked = _locked_reference_from(
        world, qa, _create_reference(world, qa["a"], "ref-l2").data["id"]
    )
    page = _get(qa["a"], "/api/references/?dataset_id=42")
    assert page.status_code == 200, page.data
    assert [row["id"] for row in page.data["results"]] == [locked, draft]
    assert page.data["next"] is None
    only_locked = _get(qa["a"], "/api/references/?dataset_id=42&status=locked")
    assert [row["id"] for row in only_locked.data["results"]] == [locked]
    assert _get(qa["a"], "/api/references/?dataset_id=42&status=x").status_code == 400
    assert _get(qa["a"], "/api/references/").status_code == 400
    assert _get(qa["a"], "/api/references/?dataset_id=abc").status_code == 400
    # Dataset ngoài phạm vi và vai trò không đọc KPI đều bị chặn ở API.
    assert _get(qa["a"], "/api/references/?dataset_id=43").status_code == 403
    assert _get(world["reviewer"], "/api/references/?dataset_id=42").status_code == 403
    po = _user("po", Role.PRODUCT_OWNER)
    assert _get(po, "/api/references/?dataset_id=42").status_code == 200


@pytest.mark.django_db
def test_evaluation_list_scoped_by_dataset_and_run(world, qa):
    ref_id = _locked_reference(world, qa)
    first = _evaluate(world, qa["a"], ref_id, key="ev-l1")
    second = _evaluate(world, qa["a"], ref_id, key="ev-l2", score_version="score-v1")
    assert first.status_code == 202 and second.status_code == 202
    page = _get(qa["a"], "/api/evaluations/?dataset_id=42")
    assert page.status_code == 200, page.data
    assert [row["id"] for row in page.data["results"]] == [second.data["id"], first.data["id"]]
    assert page.data["results"][0]["reference_id"] == ref_id
    by_run = _get(qa["a"], f"/api/evaluations/?dataset_id=42&run_id={world['run'].pk}")
    assert len(by_run.data["results"]) == 2
    other_run = _get(qa["a"], "/api/evaluations/?dataset_id=42&run_id=999999")
    assert other_run.status_code == 200 and other_run.data["results"] == []
    assert _get(qa["a"], "/api/evaluations/?dataset_id=42&run_id=0").status_code == 400
    assert _get(qa["a"], "/api/evaluations/?dataset_id=43").status_code == 403
    assert _get(world["reviewer"], "/api/evaluations/?dataset_id=42").status_code == 403
    assert _get(qa["a"], "/api/evaluations/?dataset_id=42&cursor=bad").status_code == 400
