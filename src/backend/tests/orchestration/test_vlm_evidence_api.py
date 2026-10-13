"""M04A-04: evidence append-only và read model VLM của candidate qua API (mock, không mạng)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.db.utils import DatabaseError
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from orchestration.models import (
    CandidateRecord,
    VlmEvidence,
    VlmEvidenceImmutableError,
    VlmUnit,
)
from orchestration.vlm_stage import execute_vlm_unit
from runs.models import QCRun
from runs.services import cancel_qc_run
from tests.orchestration.test_vlm_stage import (  # noqa: F401  (fixture _env tái sử dụng)
    VALID,
    FakeClient,
    _env,
    _make_run,
    _run_shards,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _client(run: QCRun) -> APIClient:
    user, created = User.objects.get_or_create(username=f"vlm-api-{run.pk}")
    if created:
        RoleAssignment.objects.create(user=user, role=Role.REVIEWER, dataset_id=run.dataset_id)
    api = APIClient()
    api.force_authenticate(user)
    return api


def _candidates(run: QCRun) -> list[dict[str, Any]]:
    resp = _client(run).get(f"/api/runs/{run.pk}/candidates/")
    assert resp.status_code == 200, resp.content[:300]
    return list(resp.data["results"])


def test_checked_unit_writes_one_evidence_with_provenance_and_api_exposes_it() -> None:
    run = _make_run()
    _run_shards(run)
    unit = VlmUnit.objects.filter(run_id=run.pk).order_by("pk").first()
    client = FakeClient(label="1")
    assert execute_vlm_unit(unit.pk, client=client) == "completed"
    evidence = VlmEvidence.objects.get(unit=unit)
    assert (evidence.status, evidence.label_class_id, evidence.class_name) == (
        "checked",
        "1",
        "car",
    )
    assert evidence.model == "qwen3-vl-plus" and evidence.prompt_version == "vlm-prompt-v0"
    assert evidence.policy_version == "vlm-trigger-v0" and evidence.snapshot_revision
    assert (
        evidence.provider == "dashscope" and evidence.provider_host == "dashscope-intl.aliyuncs.com"
    )
    assert len(evidence.crop_sha256) == 64 and evidence.attempts == 1
    assert evidence.config["host"] == "dashscope-intl.aliyuncs.com" and "api_key" not in json.dumps(
        evidence.config
    )
    rows = {row["id"]: row for row in _candidates(run)}
    vlm = rows[unit.candidate_id]["vlm"]
    assert vlm["state"] == "checked" and vlm["engine_status"] == "checked"
    assert vlm["conclusion"] == "confirmed" and vlm["source"] == "qwen"
    assert (vlm["class_id"], vlm["class_name"]) == ("1", "car")
    assert vlm["evidence_id"] == evidence.pk and vlm["model_version"] == "qwen3-vl-plus"
    assert vlm["prompt_version"] == "vlm-prompt-v0" and vlm["policy_version"] == "vlm-trigger-v0"
    assert vlm["snapshot_revision"] == evidence.snapshot_revision
    assert vlm["provider_host"] == "dashscope-intl.aliyuncs.com" and vlm["attempts"] == 1
    assert vlm["reason_code"] is None and vlm["evaluation_id"] is None
    assert "sk-test-not-real" not in json.dumps(vlm, default=str)


def test_redelivery_never_adds_evidence_and_evidence_is_append_only() -> None:
    run = _make_run()
    _run_shards(run)
    unit = VlmUnit.objects.filter(run_id=run.pk).first()
    execute_vlm_unit(unit.pk, client=FakeClient(label="1"))
    for _ in range(3):
        execute_vlm_unit(unit.pk, client=FakeClient(label="2"))
    assert VlmEvidence.objects.filter(unit=unit).count() == 1
    evidence = VlmEvidence.objects.get(unit=unit)
    assert evidence.label_class_id == "1"  # không bị ghi đè
    evidence.label_class_id = "2"
    with pytest.raises(VlmEvidenceImmutableError):
        evidence.save()
    with pytest.raises(VlmEvidenceImmutableError):
        evidence.delete()
    # DB trigger chặn cả đường vòng qua SQL/queryset.
    with pytest.raises(DatabaseError), connection.cursor() as cursor:
        cursor.execute("UPDATE orchestration_vlmevidence SET status = 'failed'")
    with pytest.raises(DatabaseError), connection.cursor() as cursor:
        cursor.execute("DELETE FROM orchestration_vlmevidence")
    with pytest.raises(DatabaseError):
        VlmEvidence.objects.filter(pk=evidence.pk).update(rationale="x")


def test_failed_unit_evidence_has_reason_and_no_label() -> None:
    run = _make_run(vlm={**VALID, "max_attempts": 1})
    _run_shards(run)
    unit = VlmUnit.objects.filter(run_id=run.pk).first()
    execute_vlm_unit(unit.pk, client=FakeClient(["không phải json"]))  # parse failure
    evidence = VlmEvidence.objects.get(unit=unit)
    assert (evidence.status, evidence.reason_code, evidence.label_class_id) == (
        "failed",
        "parse_failure",
        "",
    )
    row = {r["id"]: r for r in _candidates(run)}[unit.candidate_id]["vlm"]
    assert row["state"] == "failed" and row["engine_status"] == "failed"
    assert row["reason_code"] == "parse_failure" and row["conclusion"] is None
    assert row["class_id"] is None and row["evidence_id"] == evidence.pk


def test_uncertain_is_ai_conclusion_not_a_class() -> None:
    run = _make_run()
    _run_shards(run)
    unit = VlmUnit.objects.filter(run_id=run.pk).first()
    execute_vlm_unit(unit.pk, client=FakeClient(label="uncertain"))
    row = {r["id"]: r for r in _candidates(run)}[unit.candidate_id]["vlm"]
    assert row["state"] == "uncertain" and row["conclusion"] == "uncertain"
    assert row["class_id"] is None and row["class_name"] is None
    assert row["engine_status"] == "checked"


def test_pending_state_before_execution_and_cancelled_after_cancel() -> None:
    run = _make_run()
    _run_shards(run)
    states = {r["vlm"]["state"] for r in _candidates(run)}
    assert states == {"pending"}
    assert {r["vlm"]["engine_status"] for r in _candidates(run)} == {"running"}
    assert all(r["vlm"]["evidence_id"] is None for r in _candidates(run))
    cancel_qc_run(run_id=run.pk, actor=User.objects.create_user("canceller"))
    assert {r["vlm"]["state"] for r in _candidates(run)} == {"cancelled"}


def test_engine_level_states_are_distinguishable() -> None:
    disabled = _make_run(vlm_enabled=False)
    _run_shards(disabled)
    assert {r["vlm"]["state"] for r in _candidates(disabled)} == {"disabled"}
    no_model = _make_run(vlm={})
    _run_shards(no_model)
    assert {r["vlm"]["state"] for r in _candidates(no_model)} == {"no_model"}
    no_taxonomy = _make_run(with_taxonomy=False)
    _run_shards(no_taxonomy)
    assert {r["vlm"]["state"] for r in _candidates(no_taxonomy)} == {"not_applicable"}
    for run in (disabled, no_model, no_taxonomy):
        row = _candidates(run)[0]["vlm"]
        assert row["engine_status"] == "not_checked" and row["evidence_id"] is None
        assert row["conclusion"] is None and row["model_version"] is None


def test_candidate_has_stable_id_and_no_secret_or_image_in_payload() -> None:
    run = _make_run()
    _run_shards(run)
    for unit in VlmUnit.objects.filter(run_id=run.pk):
        execute_vlm_unit(unit.pk, client=FakeClient(label="1"))
    rows = _candidates(run)
    ids = [r["id"] for r in rows]
    assert ids == sorted(CandidateRecord.objects.filter(run_id=run.pk).values_list("pk", flat=True))
    blob = json.dumps(rows, default=str)
    assert "sk-test" not in blob and "base64" not in blob and "api_key" not in blob.lower()


def test_candidate_list_is_scoped_and_vlm_batches_queries(
    django_assert_max_num_queries: Any,
) -> None:
    run = _make_run()
    _run_shards(run)
    api = _client(run)
    with django_assert_max_num_queries(25):
        assert api.get(f"/api/runs/{run.pk}/candidates/").status_code == 200
    outsider = APIClient()
    outsider.force_authenticate(User.objects.create_user("outsider"))
    assert outsider.get(f"/api/runs/{run.pk}/candidates/").status_code in (401, 403, 404)
