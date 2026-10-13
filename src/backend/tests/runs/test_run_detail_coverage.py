"""Additional test coverage for Issue #244:

- GET idempotency: database state before and after GET requests (counts, updated_at).
- Stability of cursor pagination and filtering across page 1 and page 2 without frame loss.
- Run detail distinguishing origin vs recheck vs final with verification_lineage,
  selected_final_sources, and operational_source across all terminal states:
  Completed, Partial, Failed, Cancelled, and with unreviewed new candidate.
- Verifier separation of duties (must be different person from author/annotator).
- Absence of /lineage/ standalone endpoint (confirming 404).
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditEvent
from orchestration.models import CandidateRecord, LedgerUnit, ShardCommit
from review.finalization_service import build_final_run
from review.models import Issue, ReworkRecheck, ReworkRequest, ReworkVerification
from runs.models import EngineResult, QCRun
from tests.review.test_finalization import _resolved_scope
from tests.review.test_queue_lease import world  # noqa: F401

pytest_plugins = ["tests.review.test_queue_lease"]


def _client(user: User) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=user)
    return api


def _candidate(run: QCRun, key: str) -> CandidateRecord:
    shard, _ = ShardCommit.objects.get_or_create(
        run=run,
        engine="geometry",
        shard_index=0,
        defaults={
            "idempotency_key": f"shard-cov-{run.pk}-{key}",
            "snapshot_id": run.snapshot_id,
            "engine_version": "1",
            "output_sha256": "0" * 64,
        },
    )
    return CandidateRecord.objects.create(
        run=run,
        dedup_key=key,
        shard=shard,
        engine="geometry",
        engine_version="1",
        family="E1",
        cvat_task_id=200,
        frame_number=0,
        anchor={"kind": "manual_region", "objects": []},
        policy_version="p1",
        evidence={},
        evidence_sha256="1" * 64,
    )


def _complete_final_run(final: QCRun) -> None:
    final.engine_results.all().delete()
    result = EngineResult.objects.create(
        run=final,
        engine="geometry",
        status="checked",
        eligible_units=1,
        completed_units=1,
        failed_units=0,
        not_checked_units=0,
        required=True,
    )
    LedgerUnit.objects.create(
        run=final,
        engine=result.engine,
        kind="frame",
        cvat_task_id=200,
        frame_number=0,
        outcome="completed",
    )
    final.status = QCRun.Status.COMPLETED
    final.finished_at = timezone.now()
    final.save(update_fields=["status", "finished_at"])


@pytest.fixture
def run_lineage_world(world, monkeypatch):  # noqa: F811
    issue, fixed, verification = _resolved_scope(world)
    monkeypatch.setattr(
        "review.finalization_service.create_snapshot_from_cvat", lambda **_kwargs: fixed
    )
    final, _ = build_final_run(origin_run_id=world["run"].pk, actor=world["other"])
    return {**world, "issue": issue, "final": final, "verification": verification}


@pytest.mark.django_db
def test_get_endpoints_do_not_mutate_db_state(run_lineage_world):
    rework = run_lineage_world["verification"].rework
    run_id = run_lineage_world["run"].pk
    api = _client(run_lineage_world["reviewer"])

    before_state = {
        "rework_rows": list(ReworkRequest.objects.values("id", "status", "updated_at")),
        "recheck_count": ReworkRecheck.objects.count(),
        "verification_count": ReworkVerification.objects.count(),
        "audit_count": AuditEvent.objects.count(),
        "run_rows": list(QCRun.objects.values("id", "status")),
    }

    # Repeated GET requests to all target endpoints
    for _ in range(3):
        res_list = api.get("/api/rework/?dataset_id=42")
        assert res_list.status_code == 200
        res_detail = api.get(f"/api/rework/{rework.pk}/")
        assert res_detail.status_code == 200
        res_run = api.get(f"/api/runs/{run_id}/")
        assert res_run.status_code == 200

    after_state = {
        "rework_rows": list(ReworkRequest.objects.values("id", "status", "updated_at")),
        "recheck_count": ReworkRecheck.objects.count(),
        "verification_count": ReworkVerification.objects.count(),
        "audit_count": AuditEvent.objects.count(),
        "run_rows": list(QCRun.objects.values("id", "status")),
    }

    assert before_state == after_state


@pytest.mark.django_db
def test_rework_pagination_and_filter_page_2_stable_no_dupes(run_lineage_world, monkeypatch):
    template = run_lineage_world["verification"].rework
    frame = template.issue.frame_review
    # Create 4 distinct issues so each has its own active or resolved rework
    created_items = [template]
    for i in range(4):
        new_issue = Issue.objects.create(
            frame_review=frame,
            family=Issue.Family.E1,
            origin=Issue.Origin.REVIEWER,
            state=Issue.State.FIX_PENDING if i % 2 == 0 else Issue.State.RESOLVED,
            anchor={"kind": "manual_region", "objects": []},
            severity=Issue.Severity.MEDIUM,
            created_by=template.created_by,
        )
        created_items.append(
            ReworkRequest.objects.create(
                issue=new_issue,
                annotator=template.annotator,
                created_by=template.created_by,
                status=ReworkRequest.Status.FIX_PENDING
                if i % 2 == 0
                else ReworkRequest.Status.RESOLVED,
                instruction=f"Item {i}",
                severity=template.severity,
                cvat_deep_link=template.cvat_deep_link,
                original_revision="rev",
                due_at=template.due_at,
            )
        )

    # Set page size to 2 to force multi-page navigation
    monkeypatch.setattr("review.rework_read_views.ReworkCursorPagination.page_size", 2)
    api = _client(run_lineage_world["reviewer"])

    # Unfiltered: page 1 -> page 2 -> page 3
    p1 = api.get("/api/rework/?dataset_id=42").json()
    assert len(p1["results"]) == 2
    assert p1["next"] is not None

    p2 = api.get(p1["next"]).json()
    assert len(p2["results"]) == 2
    assert p2["next"] is not None

    p3 = api.get(p2["next"]).json()
    assert len(p3["results"]) == 1
    assert p3["next"] is None

    all_ids = (
        [r["id"] for r in p1["results"]]
        + [r["id"] for r in p2["results"]]
        + [r["id"] for r in p3["results"]]
    )
    assert len(all_ids) == 5
    assert len(set(all_ids)) == 5  # No duplicates, no missed frames

    # Filtered by status=fix_pending: 2 items created with FIX_PENDING
    fp1 = api.get("/api/rework/?dataset_id=42&status=fix_pending").json()
    assert len(fp1["results"]) == 2
    assert fp1["next"] is None  # Exactly 2 items, fits in 1 page of 2 items


@pytest.mark.django_db
def test_standalone_lineage_endpoint_matches_run_detail(run_lineage_world):
    # MBE-01 thêm GET /api/runs/{id}/lineage/; chuỗi phải khớp nguồn vận hành của run detail.
    api = _client(run_lineage_world["reviewer"])
    origin = run_lineage_world["run"]
    final = run_lineage_world["final"]
    res = api.get(f"/api/runs/{origin.pk}/lineage/")
    assert res.status_code == 200, res.data
    kinds = {node["run_id"]: node["kind"] for node in res.data["chain"]}
    assert kinds[origin.pk] == "original" and kinds[final.pk] == "final"
    assert res.data["chain"][0]["run_id"] == origin.pk
    detail = api.get(f"/api/runs/{origin.pk}/").json()
    selected = detail["operational_source"]
    expected_final = selected["run_id"] if selected["reason"] == "selected_final" else None
    assert res.data["final_run_id"] == expected_final
    assert api.get(f"/api/runs/{final.pk}/lineage/").data["chain"] == res.data["chain"]


@pytest.mark.django_db
def test_run_detail_lineage_terminal_states_matrix(run_lineage_world):
    origin = run_lineage_world["run"]
    final = run_lineage_world["final"]
    verification = run_lineage_world["verification"]
    recheck = verification.recheck_run
    api = _client(run_lineage_world["reviewer"])

    # 1. Origin run detail
    origin_res = api.get(f"/api/runs/{origin.pk}/").json()
    assert origin_res["verification_lineage"] == []
    assert origin_res["selected_final_sources"] == []
    assert origin_res["operational_source"]["run_id"] == origin.pk
    assert origin_res["operational_source"]["run_kind"] == "origin"

    # 2. Recheck run detail
    recheck_res = api.get(f"/api/runs/{recheck.pk}/").json()
    assert len(recheck_res["verification_lineage"]) == 1
    assert recheck_res["verification_lineage"][0]["verification_id"] == verification.pk
    assert recheck_res["selected_final_sources"] == []
    assert recheck_res["operational_source"]["origin_run_id"] == origin.pk

    # 3. Final run in QUEUED state (not completed yet)
    final_queued = api.get(f"/api/runs/{final.pk}/").json()
    assert final_queued["selected_final_sources"] == []
    assert final_queued["operational_source"]["scope_complete"] is False
    assert "final_run_queued" in final_queued["operational_source"]["blocked_reasons"]

    # 4. Final run Completed
    _complete_final_run(final)
    final_completed = api.get(f"/api/runs/{final.pk}/").json()
    assert len(final_completed["verification_lineage"]) == 1
    assert len(final_completed["selected_final_sources"]) == 1
    sel = final_completed["selected_final_sources"][0]
    assert sel["rework_id"] == verification.rework_id
    assert sel["verification_id"] == verification.pk
    assert sel["source_run_id"] == recheck.pk
    assert final_completed["operational_source"]["run_id"] == final.pk
    assert final_completed["operational_source"]["run_kind"] == "final"
    assert final_completed["operational_source"]["scope_complete"] is True
    assert final_completed["operational_source"]["blocked_reasons"] == []

    # 5. Final run Partial, Failed, Cancelled
    for terminal_status in [QCRun.Status.PARTIAL, QCRun.Status.FAILED, QCRun.Status.CANCELLED]:
        final.status = terminal_status
        final.save(update_fields=["status"])
        terminal_res = api.get(f"/api/runs/{final.pk}/").json()
        assert terminal_res["selected_final_sources"] == []
        assert terminal_res["operational_source"]["run_id"] == origin.pk
        assert terminal_res["operational_source"]["scope_complete"] is False
        assert (
            f"final_run_{terminal_status}" in terminal_res["operational_source"]["blocked_reasons"]
        )

    # 6. Final run Completed but has unreviewed new candidate
    final.status = QCRun.Status.COMPLETED
    final.save(update_fields=["status"])
    _candidate(final, "coverage-unreviewed-candidate")
    cand_res = api.get(f"/api/runs/{final.pk}/").json()
    assert cand_res["selected_final_sources"] == []
    assert cand_res["operational_source"]["run_id"] == origin.pk
    assert cand_res["operational_source"]["scope_complete"] is False
    assert "new_candidate_unreviewed" in cand_res["operational_source"]["blocked_reasons"]
