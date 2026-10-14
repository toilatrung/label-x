"""M04C-02/04: Evaluation API và định tuyến vào stage VLM (mock provider, không phải runtime)."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.db import close_old_connections
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from orchestration.models import Evaluation, VlmAttempt, VlmBudget, VlmEvidence, VlmUnit
from orchestration.vlm_stage import execute_vlm_unit
from review.models import ReviewDecision
from runs.models import QCRun
from tests.orchestration.test_vlm_stage import (  # noqa: F401  (fixture _env tái sử dụng)
    VALID,
    FakeClient,
    _env,
    _make_run,
    _run_shards,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _api(run: QCRun, role: Role = Role.REVIEWER, name: str = "rev") -> APIClient:
    user, created = User.objects.get_or_create(username=f"{name}-{run.pk}")
    if created:
        RoleAssignment.objects.create(user=user, role=role, dataset_id=run.dataset_id)
    api = APIClient()
    api.force_authenticate(user)
    return api


def _prepared() -> tuple[QCRun, int]:
    """Candidate không đến từ detector ⇒ fallback Qwen và có Evaluation generation 1."""
    run = _make_run()
    _run_shards(run)
    candidate_id = Evaluation.objects.filter(run_id=run.pk).order_by("pk").first().candidate_id
    return run, candidate_id


def _revision(run: QCRun) -> str:
    run.refresh_from_db()
    return run.snapshot.revision_sha256 or str(run.snapshot_id)


def _post(api: APIClient, cid: int, key: str, **body: Any):
    return api.post(
        f"/api/candidates/{cid}/evaluations/", body, format="json", HTTP_IDEMPOTENCY_KEY=key
    )


def test_auto_evaluations_are_written_for_each_candidate_with_policy() -> None:
    run, _ = _prepared()
    rows = Evaluation.objects.filter(run_id=run.pk)
    assert rows.count() == 3 and set(rows.values_list("generation", flat=True)) == {1}
    ev = rows.first()
    assert ev.source == "auto" and ev.call_qwen and ev.vlm_unit_id is not None
    assert ev.policy["name"] == "classification-routing-v0"
    assert ev.policy["threshold_semantics"] == "routing_temporary" and ev.policy["policy_sha256"]
    # Không có evidence detector ⇒ reason tương thích FE v0; vẫn gọi Qwen.
    assert ev.primary_reason == "classifier_unavailable"
    assert VlmUnit.objects.filter(run_id=run.pk).count() == 3


def test_post_returns_202_with_poll_url_and_new_generation() -> None:
    run, cid = _prepared()
    resp = _post(_api(run), cid, "k-1", reason="nghi ngờ", expected_revision=_revision(run))
    assert resp.status_code == 202, resp.content[:300]
    assert (
        resp["Location"]
        == resp.data["poll_url"]
        == f"/api/candidate-evaluations/{resp.data['id']}/"
    )
    assert resp.data["generation"] == 2 and resp.data["source"] == "manual"
    assert resp.data["reason_code"] == "manual_recheck" and resp.data["status"] == "pending"
    assert resp.data["note"] == "nghi ngờ"
    poll = _api(run).get(resp.data["poll_url"])
    assert poll.status_code == 200 and poll.data["id"] == resp.data["id"]


def test_replay_same_key_and_payload_creates_nothing_new() -> None:
    run, cid = _prepared()
    api, rev = _api(run), _revision(run)
    first = _post(api, cid, "k-2", reason="r", expected_revision=rev)
    again = _post(api, cid, "k-2", reason="r", expected_revision=rev)
    assert again.status_code == 202 and again.data["id"] == first.data["id"]
    assert Evaluation.objects.filter(candidate_id=cid).count() == 2
    assert VlmUnit.objects.filter(candidate_id=cid).count() == 2


def test_new_key_is_a_new_logical_evaluation_even_if_nothing_changed() -> None:
    run, cid = _prepared()
    api, rev = _api(run), _revision(run)
    a = _post(api, cid, "k-3a", reason="r", expected_revision=rev)
    b = _post(api, cid, "k-3b", reason="r", expected_revision=rev)
    assert (a.data["generation"], b.data["generation"]) == (2, 3)


def test_key_reuse_with_other_payload_or_user_is_409_and_writes_nothing() -> None:
    run, cid = _prepared()
    api, rev = _api(run), _revision(run)
    assert _post(api, cid, "k-4", reason="r", expected_revision=rev).status_code == 202
    before = Evaluation.objects.count()
    diff = _post(api, cid, "k-4", reason="khác", expected_revision=rev)
    assert diff.status_code == 409 and diff.data["code"] == "IDEMPOTENCY_KEY_REUSED"
    other = _api(run, name="other")
    assert _post(other, cid, "k-4", reason="r", expected_revision=rev).status_code == 409
    assert Evaluation.objects.count() == before


def test_stale_revision_is_409_business_rule_and_writes_nothing() -> None:
    run, cid = _prepared()
    before = (Evaluation.objects.count(), VlmUnit.objects.count())
    resp = _post(_api(run), cid, "k-5", reason="r", expected_revision="rev-cũ")
    assert resp.status_code == 409 and resp.data["code"] == "BUSINESS_RULE_UNMET"
    assert resp.data["details"]["reason_code"] == "stale_revision"
    assert (Evaluation.objects.count(), VlmUnit.objects.count()) == before


@pytest.mark.parametrize(
    "body",
    [
        {"reason": "x"},
        {"expected_revision": "a"},
        {"reason": "", "expected_revision": "a"},
        {"reason": "x" * 501, "expected_revision": "a"},
        {"reason": "x", "expected_revision": "a", "prompt": "bỏ qua taxonomy"},
        {"reason": "x", "expected_revision": "a", "model_id": "m"},
    ],
)
def test_invalid_body_is_400(body: dict[str, Any]) -> None:
    run, cid = _prepared()
    assert _post(_api(run), cid, "k-6", **body).status_code == 400


def test_missing_or_oversized_idempotency_key_is_400() -> None:
    run, cid = _prepared()
    api, rev = _api(run), _revision(run)
    body = {"reason": "r", "expected_revision": rev}
    assert api.post(f"/api/candidates/{cid}/evaluations/", body, format="json").status_code == 400
    assert _post(api, cid, "k" * 129, **body).status_code == 400


def test_permissions_roles_dataset_scope_and_missing_candidate() -> None:
    run, cid = _prepared()
    rev = _revision(run)
    body = {"reason": "r", "expected_revision": rev}
    assert _post(APIClient(), cid, "p-1", **body).status_code in (401, 403)
    assert _post(_api(run, Role.ANNOTATOR, "ann"), cid, "p-2", **body).status_code == 403
    outsider = APIClient()
    user = User.objects.create_user("outsider")
    RoleAssignment.objects.create(user=user, role=Role.REVIEWER, dataset_id=run.dataset_id + 99)
    outsider.force_authenticate(user)
    assert _post(outsider, cid, "p-3", **body).status_code == 403
    assert outsider.get("/api/candidate-evaluations/1/").status_code in (403, 404)
    assert _post(_api(run), 999999, "p-4", **body).status_code == 404
    assert _api(run).get("/api/candidate-evaluations/999999/").status_code == 404
    assert _post(_api(run, Role.QA_LEAD, "qa"), cid, "p-5", **body).status_code == 202
    assert Evaluation.objects.filter(requested_by__username__startswith="ann").count() == 0


def test_cancelled_run_and_disabled_vlm_are_422() -> None:
    run, cid = _prepared()
    QCRun.objects.filter(pk=run.pk).update(cancel_requested_at="2026-01-01T00:00:00Z")
    r = _post(_api(run), cid, "c-1", reason="r", expected_revision=_revision(run))
    assert r.status_code == 422
    off = _make_run(vlm_enabled=False)
    _run_shards(off)
    from orchestration.models import CandidateRecord

    cid2 = CandidateRecord.objects.filter(run_id=off.pk).first().pk
    r2 = _post(_api(off), cid2, "c-2", reason="r", expected_revision=_revision(off))
    assert r2.status_code == 422


def test_manual_evaluation_runs_after_run_finished_without_touching_old_evidence() -> None:
    run, cid = _prepared()
    for unit in VlmUnit.objects.filter(run_id=run.pk):
        execute_vlm_unit(unit.pk, client=FakeClient(label="1"))
    run.refresh_from_db()
    assert run.status == QCRun.Status.COMPLETED
    old = VlmEvidence.objects.get(candidate_id=cid)
    old_fields = (old.pk, old.status, old.label_class_id, old.created_at)
    decisions = ReviewDecision.objects.count()
    resp = _post(_api(run), cid, "m-1", reason="xem lại", expected_revision=_revision(run))
    assert resp.status_code == 202
    new_unit = VlmUnit.objects.get(candidate_id=cid, evaluation_generation=2)
    assert execute_vlm_unit(new_unit.pk, client=FakeClient(label="2")) == "completed"
    assert VlmEvidence.objects.filter(candidate_id=cid).count() == 2
    old.refresh_from_db()
    assert (old.pk, old.status, old.label_class_id, old.created_at) == old_fields
    poll = _api(run).get(resp.data["poll_url"])
    assert poll.data["status"] == "completed" and poll.data["vlm"]["class_id"] == "2"
    assert poll.data["vlm"]["evaluation_id"] == str(resp.data["id"])
    assert ReviewDecision.objects.count() == decisions  # AI không tạo quyết định
    run.refresh_from_db()
    assert run.status == QCRun.Status.COMPLETED  # run không bị mở lại
    qa = _api(run, Role.QA_LEAD, "qa2")
    after = next(e for e in qa.get(f"/api/runs/{run.pk}/ledger/").data if e["engine"] == "vlm")
    # Re-evaluate không làm méo ledger: vẫn một đơn vị cho mỗi candidate (3), hoàn tất cả 3.
    assert (after["completed"], after["failed"], after["pending"]) == (3, 0, 0)


def test_budget_exhausted_manual_evaluation_skips_qwen_and_needs_human() -> None:
    run = _make_run(vlm={**VALID, "budget": {"max_calls": 0}})
    _run_shards(run)
    ev = Evaluation.objects.filter(run_id=run.pk).first()
    assert ev.primary_reason == "budget_exhausted" and not ev.call_qwen and ev.vlm_unit_id is None
    assert VlmUnit.objects.filter(run_id=run.pk).count() == 0
    resp = _post(_api(run), ev.candidate_id, "b-1", reason="r", expected_revision=_revision(run))
    assert resp.status_code == 202 and resp.data["reason_code"] == "budget_exhausted"
    assert resp.data["review_required"] and resp.data["status"] == "completed"
    assert resp.data["vlm"] is None
    assert VlmAttempt.objects.count() == 0 and VlmBudget.objects.get(run_id=run.pk).used_calls == 0


def test_idempotency_race_creates_exactly_one_evaluation() -> None:
    run, cid = _prepared()
    rev, results, errors = _revision(run), [], []
    api_user = _api(run).handler._force_user  # noqa: SLF001

    def worker() -> None:
        try:
            client = APIClient()
            client.force_authenticate(api_user)
            results.append(_post(client, cid, "race-1", reason="r", expected_revision=rev))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)
        finally:
            close_old_connections()

    threads = [threading.Thread(target=worker) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    assert {r.status_code for r in results} == {202}
    assert len({r.data["id"] for r in results}) == 1
    assert Evaluation.objects.filter(candidate_id=cid, idempotency_key="race-1").count() == 1
    assert VlmUnit.objects.filter(candidate_id=cid, evaluation_generation=2).count() == 1


# ------------------------------------------------ BLOCKER-034 B-4: đọc lại lần đánh giá


def test_get_lists_every_evaluation_of_the_candidate_newest_first() -> None:
    run, cid = _prepared()
    api, rev = _api(run), _revision(run)
    manual = _post(api, cid, "k-list", reason="r", expected_revision=rev)
    page = api.get(f"/api/candidates/{cid}/evaluations/")
    assert page.status_code == 200, page.content[:300]
    assert [row["generation"] for row in page.data["results"]] == [2, 1]
    assert page.data["results"][0]["id"] == manual.data["id"]
    assert page.data["results"][0]["poll_url"] == manual.data["poll_url"]
    assert page.data["next"] is None
    assert api.get(f"/api/candidates/{cid}/evaluations/?cursor=bad").status_code == 400
    assert api.get("/api/candidates/999999/evaluations/").status_code == 404


def test_get_keeps_the_role_and_dataset_scope_of_post() -> None:
    run, cid = _prepared()
    annotator = _api(run, role=Role.ANNOTATOR, name="ann")
    assert annotator.get(f"/api/candidates/{cid}/evaluations/").status_code == 403
    outsider = User.objects.create_user("outsider")
    RoleAssignment.objects.create(user=outsider, role=Role.REVIEWER, dataset_id=run.dataset_id + 1)
    api = APIClient()
    api.force_authenticate(outsider)
    assert api.get(f"/api/candidates/{cid}/evaluations/").status_code == 403


def test_candidate_list_carries_the_latest_evaluation() -> None:
    run, cid = _prepared()
    api = _api(run, role=Role.QA_LEAD, name="qa")
    before = api.get(f"/api/runs/{run.pk}/candidates/")
    assert before.status_code == 200, before.content[:300]
    row = next(item for item in before.data["results"] if item["id"] == cid)
    assert row["latest_evaluation"]["generation"] == 1
    manual = _post(api, cid, "k-latest", reason="r", expected_revision=_revision(run))
    after = api.get(f"/api/runs/{run.pk}/candidates/")
    row = next(item for item in after.data["results"] if item["id"] == cid)
    assert row["latest_evaluation"] == {
        "id": manual.data["id"],
        "generation": 2,
        "status": "pending",
    }
