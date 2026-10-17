"""MBE-01: GET /api/frames/{id}/workspace/ và GET /api/runs/{id}/lineage/.

Dữ liệu dựng trực tiếp (không gọi Qwen thật): evidence AI trong test là bản ghi tổng hợp.
"""

import pytest
from django.core.files.storage import storages

from orchestration.models import (
    CandidateRecord,
    Evaluation,
    LedgerUnit,
    ShardCommit,
    VlmEvidence,
    VlmUnit,
)
from review.models import Lease, ReviewDecision
from runs.models import QCRun
from tests.review.test_queue_lease import client, next_url

pytest_plugins = ["tests.review.test_queue_lease"]


@pytest.fixture(autouse=True)
def _storage(monkeypatch):
    monkeypatch.setattr(storages["snapshots"], "url", lambda name: f"https://storage.test/{name}")


def _candidate(run, key="b"):
    shard = ShardCommit.objects.create(
        idempotency_key=f"ws-shard-{key}",
        run=run,
        snapshot_id=run.snapshot_id,
        engine="detector",
        engine_version="v1",
        shard_index=0,
        output_sha256="a" * 64,
    )
    LedgerUnit.objects.create(
        run=run, engine="detector", kind="frame", cvat_task_id=200, frame_number=0, outcome="failed"
    )
    return CandidateRecord.objects.create(
        run=run,
        dedup_key=key * 64,
        shard=shard,
        engine="detector",
        engine_version="v1",
        family="E2",
        cvat_task_id=200,
        frame_number=0,
        anchor={
            "kind": "prediction_region",
            "objects": [{"namespace": "detector", "id": "1:0"}],
            "rule_id": None,
            "bbox": {"x1": 1, "y1": 1, "x2": 10, "y2": 10},
            "policy_version": "anchor-v1",
        },
        policy_version="anchor-v1",
        evidence={"engine": "detector", "source": "detector"},
        evidence_sha256="c" * 64,
    )


def _evaluation(
    run,
    candidate,
    *,
    qwen: bool,
    generation=1,
    status="completed",
    result="checked",
    model="qwen-test",
):
    unit = None
    if qwen:
        unit = VlmUnit.objects.create(
            run=run,
            candidate=candidate,
            idempotency_key=f"k{generation}",
            evaluation_generation=generation,
            policy_version="p1",
            model=model,
            prompt_version="v1",
            status=status,
            result={"status": result},
        )
        VlmEvidence.objects.create(
            unit=unit,
            run=run,
            candidate=candidate,
            status=result,
            class_name="car",
            rationale="giống xe",
            provider="mock",
            model=model,
            prompt_version="v1",
            policy_version="p1",
            snapshot_revision="rev",
            crop_sha256="d" * 64,
        )
    return Evaluation.objects.create(
        run=run,
        candidate=candidate,
        generation=generation,
        source="auto" if generation == 1 else "manual",
        snapshot_revision="rev",
        primary_reason="label_conflict" if qwen else "classifier_confident",
        reasons=["label_conflict"] if qwen else [],
        call_qwen=qwen,
        human_review_required=False,
        policy={"name": "p"},
        vlm_unit=unit,
    )


def _claim(world):
    response = client(world["reviewer"]).post(
        next_url(), {"run_id": world["run"].pk}, format="json"
    )
    assert response.status_code == 200, response.data
    return response.data["lease"]["id"], response.data["frame"]["id"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("model", "source"), [("qwen-test", "qwen"), ("gemini-3.8-flash", "gemini")]
)
def test_workspace_has_issues_lease_queue_and_ai_evidence(world, model, source):
    candidate = _candidate(world["run"])
    _evaluation(world["run"], candidate, qwen=True, model=model)
    lease_id, frame_id = _claim(world)
    response = client(world["reviewer"]).get(f"/api/frames/{frame_id}/workspace/")
    assert response.status_code == 200, response.data
    data = response.data
    assert data["lease"]["id"] == lease_id and data["queue"] == "risk"
    assert data["undecided_issue_count"] == 1
    assert data["snapshot_revision"] == world["run"].snapshot.revision_sha256
    assert data["anchor_policy_version"] == "anchor-v1"
    (entry,) = data["ai_evidence"]
    assert entry["source"] == source and entry["reason_code"] == "label_conflict"
    assert entry["issue_id"] == data["issues"][0]["id"]
    assert entry["evidence_refs"]["crop_sha256"] == "d" * 64
    assert entry["evidence_refs"]["model"] == model
    assert entry["suggestion"]["status"] == "checked"
    assert entry["review_required"] is False
    # Qwen chỉ đề xuất: không tạo quyết định review.
    assert ReviewDecision.objects.count() == 0


@pytest.mark.django_db
def test_workspace_classifier_only_and_latest_generation_wins(world):
    candidate = _candidate(world["run"])
    _evaluation(world["run"], candidate, qwen=False)
    _, frame_id = _claim(world)
    api = client(world["reviewer"])
    (entry,) = api.get(f"/api/frames/{frame_id}/workspace/").data["ai_evidence"]
    assert entry["source"] == "classifier" and entry["evidence_refs"] is None
    _evaluation(world["run"], candidate, qwen=True, generation=2, result="uncertain")
    (entry,) = api.get(f"/api/frames/{frame_id}/workspace/").data["ai_evidence"]
    assert entry["generation"] == 2 and entry["source"] == "qwen"
    assert entry["review_required"] is True  # Qwen uncertain


@pytest.mark.django_db
def test_workspace_without_lease_manual_issue_and_permissions(world):
    _, frame_id = _claim(world)
    Lease.objects.all().update(closed_at=world["run"].created_at)
    response = client(world["reviewer"]).get(f"/api/frames/{frame_id}/workspace/")
    assert response.status_code == 200
    assert response.data["lease"] is None and response.data["queue"] is None
    assert response.data["ai_evidence"] == []
    assert client(world["author"]).get(f"/api/frames/{frame_id}/workspace/").status_code == 403
    assert client(world["reviewer"]).get("/api/frames/999999/workspace/").status_code in (403, 404)


@pytest.mark.django_db
def test_run_lineage_chain_and_permissions(world):
    origin = world["run"]
    recheck = QCRun.objects.create(
        snapshot=origin.snapshot,
        config_version=origin.config_version,
        seed=1,
        status=QCRun.Status.COMPLETED,
        dataset_id=origin.dataset_id,
        scope_hash="e" * 64,
        created_by=world["admin"],
        origin_run=origin,
    )
    api = client(world["reviewer"])
    from_origin = api.get(f"/api/runs/{origin.pk}/lineage/")
    assert from_origin.status_code == 200, from_origin.data
    assert from_origin.data["origin_run_id"] is None and from_origin.data["final_run_id"] is None
    assert [n["kind"] for n in from_origin.data["chain"]] == ["original", "rework_verification"]
    assert [n["run_id"] for n in from_origin.data["chain"]] == [origin.pk, recheck.pk]
    from_recheck = api.get(f"/api/runs/{recheck.pk}/lineage/")
    assert from_recheck.data["origin_run_id"] == origin.pk
    assert from_recheck.data["chain"] == from_origin.data["chain"]
    assert client(world["author"]).get(f"/api/runs/{origin.pk}/lineage/").status_code == 403
    assert api.get("/api/runs/999999/lineage/").status_code in (403, 404)
