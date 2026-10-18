"""#397: real API waiver boundaries; report/export support remains distinct from E2E."""

from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import CvatIdentity, Role, RoleAssignment
from audit.models import AuditEvent
from runs.kpi import THRESHOLDS, _active_waiver, gate_conditions, overall_status
from runs.models import Waiver
from tests.review.test_queue_lease import client
from tests.review.test_queue_lease import world as world
from tests.runs.test_kpi_api import _evaluate, _locked_reference, _post
from tests.runs.test_kpi_api import qa as qa


@pytest.mark.django_db
def test_gte02_waiver_approval_identity_expiry_condition_scope(world, qa, monkeypatch):
    now = timezone.now()
    monkeypatch.setattr("runs.kpi.timezone.now", lambda: now)
    run = world["run"]
    requester, approver = world["reviewer"], qa["a"]
    body = {
        "run_id": run.pk,
        "condition": "agreement",
        "reason": "insufficient sample",
        "evidence": "test evidence",
        "expires_at": (now + timedelta(hours=1)).isoformat(),
    }
    assert (
        _post(
            requester, "/api/waivers/", {**body, "condition": "residual"}, "invalid-condition"
        ).status_code
        == 422
    )
    created = _post(requester, "/api/waivers/", body, "waiver")
    assert created.status_code == 201, created.data
    pk = created.data["id"]
    assert _active_waiver([run.pk], "agreement") is None
    assert (
        _post(
            requester, f"/api/waivers/{pk}/approve/", {"approved": True, "reason": "self"}, "own"
        ).status_code
        == 403
    )
    # An administrator remains bound by the same separation-of-duties rule.
    RoleAssignment.objects.create(user=requester, role=Role.SUPER_ADMIN, dataset_id=None)
    own_admin = _post(
        requester, f"/api/waivers/{pk}/approve/", {"approved": True, "reason": "admin"}, "own-admin"
    )
    assert own_admin.status_code == 403 and own_admin.data["code"] == "SAME_REQUESTER_APPROVER"
    # A different account mapped to the same verified person also cannot approve.
    reviewer_identity = CvatIdentity.objects.get(user=requester)
    CvatIdentity.objects.create(
        user=approver, cvat_user_id=1801, employee=reviewer_identity.employee
    )
    alias = _post(
        approver, f"/api/waivers/{pk}/approve/", {"approved": True, "reason": "alias"}, "alias"
    )
    assert alias.status_code == 403 and alias.data["code"] == "SAME_REQUESTER_APPROVER"
    assert Waiver.objects.get(pk=pk).status == "pending"
    assert not AuditEvent.objects.filter(action="waiver.approve", object_id=str(pk)).exists()
    # A separate authorized reviewer of the request can approve exactly once.
    response = _post(
        qa["b"],
        f"/api/waivers/{pk}/approve/",
        {"approved": True, "reason": "independent"},
        "approved",
    )
    assert response.status_code == 200, response.data
    approved = Waiver.objects.get(pk=pk)
    assert approved.approved_by_id == qa["b"].pk and approved.decided_at == now
    assert AuditEvent.objects.filter(action="waiver.approve", object_id=str(pk)).count() == 1
    assert _active_waiver([run.pk], "agreement").pk == pk
    assert _active_waiver([run.pk + 99999], "agreement") is None
    assert _active_waiver([run.pk], "coverage") is None
    monkeypatch.setattr("runs.kpi.timezone.now", lambda: now + timedelta(hours=1))
    assert _active_waiver([run.pk], "agreement") is None  # exact expiry is excluded
    gate = client(qa["b"]).get(f"/api/runs/{run.pk}/gate/")
    assert gate.status_code == 200
    assert all(row["status"] != "waived" for row in gate.data["conditions"])


@pytest.mark.django_db
def test_rpt01_report_preserves_metric_provenance_and_separate_streams(world, qa):
    from runs.models import RunRankingEntry

    run = world["run"]
    # Distinct sample sizes catch accidental reuse of the risk stream for random audit.
    RunRankingEntry.objects.filter(ranking__run=run, ranking__source="random_audit").delete()
    reference_id = _locked_reference(world, qa)
    evaluation = _evaluate(world, qa["a"], reference_id)
    assert evaluation.status_code == 202, evaluation.data
    response = client(qa["a"]).get(f"/api/reports/{evaluation.data['id']}/")
    assert response.status_code == 200, response.data
    data = response.data
    assert data["input_snapshot_id"] == run.snapshot_id
    assert data["reference_id"] == reference_id
    assert data["source_run_id"] == run.pk
    assert data["source_reason"]
    assert data["score_version"] == evaluation.data["score_version"]
    assert data["metrics"] == evaluation.data["metrics"]
    assert data["risk_queue"]["frames_ranked"] == 1
    assert data["random_queue"]["frames_ranked"] == 0
    # Missing engine-reference scores have no fabricated point estimate or interval.
    for key in ["KPI-1", "KPI-2", "KPI-2b", "G-1"]:
        row = data["metrics"][key]
        assert row["value"] is None and row["confidence_interval"] is None
        assert row["status"] in {"not_checked", "insufficient_sample"}
        assert row["sample_size"] == 0 and row["denominator"] == 0
        assert row["method"] == "gt_payload_not_stored"
    assert data["metrics"]["G-3"]["method"] == "reviewer_vs_adjudicator"
    assert data["metrics"]["G-3"]["value"] is None
    assert {row["engine"] for row in data["engine_coverage"]} == {
        row.engine for row in run.engine_results.all()
    }
    assert data["metrics"]["G-1"]["method"] != data["metrics"]["G-3"]["method"]


def _gate(**over):
    base = {
        "coverage": 0.95,
        "source_completed": True,
        "open_critical": 0,
        "rework": 1.0,
        "residual": 0.05,
        "agreement": 0.9,
        "reason": None,
    }
    conditions = gate_conditions(**{**base, **over})
    return {row["name"]: row["status"] for row in conditions}, conditions


def test_gte01_pilot_thresholds_boundaries_missing_and_partial_reference():
    # FR-GTE-01: 95% / 0 / 100% / 5% / 90% do chính policy, không có hằng số thứ hai.
    assert THRESHOLDS == {
        "coverage": 0.95,
        "open_critical_issues": 0.0,
        "rework_verified": 1.0,
        "residual": 0.05,
        "agreement": 0.9,
    }
    at_boundary, conditions = _gate()
    assert set(at_boundary.values()) == {"passed"}
    assert overall_status(conditions, complete=True) == "passed"
    assert [row["threshold"] for row in conditions] == list(THRESHOLDS.values())

    cases = [  # (condition, field, ngay dưới ngưỡng, ngay trên ngưỡng)
        ("coverage", "coverage", 0.9499, 0.9501),
        ("open_critical_issues", "open_critical", 1, 0),
        ("rework_verified", "rework", 0.9999, 1.0),
        ("residual", "residual", 0.0501, 0.0499),
        ("agreement", "agreement", 0.8999, 0.9001),
    ]
    for name, field, bad, good in cases:
        statuses, rows = _gate(**{field: bad})
        assert statuses[name] == "failed", (name, bad)
        assert {k: v for k, v in statuses.items() if k != name} == {
            k: "passed" for k in statuses if k != name
        }
        assert overall_status(rows, complete=True) == "failed"
        statuses, rows = _gate(**{field: good})
        assert statuses[name] == "passed", (name, good)
        assert overall_status(rows, complete=True) == "passed"

    # FR-GTE-02: thiếu dữ liệu là chưa đạt, không tự đạt và không bị agreement che.
    for field in ("coverage", "residual", "agreement"):
        statuses, rows = _gate(**{field: None})
        assert statuses[field] == "not_checked"
        assert overall_status(rows, complete=True) == "not_checked"
    statuses, rows = _gate(coverage=None, agreement=1.0)
    assert statuses["coverage"] == "not_checked" and statuses["agreement"] == "passed"
    assert overall_status(rows, complete=True) != "passed"

    # Run cuối Partial/Failed: coverage 100% vẫn không đạt và gate tổng không đạt.
    statuses, rows = _gate(coverage=1.0, source_completed=False, reason="selected_partial")
    assert statuses["coverage"] == "failed"
    assert next(row for row in rows if row["name"] == "coverage")["reason"] == "selected_partial"
    assert overall_status(rows, complete=False) == "failed"
    # Đủ mọi điều kiện nhưng run cuối chưa hoàn tất vẫn không phát hành kết quả đạt.
    passed_rows = _gate()[1]
    assert overall_status(passed_rows, complete=False) == "failed"
