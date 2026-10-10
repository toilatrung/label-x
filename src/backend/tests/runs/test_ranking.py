"""Persistence and HTTP integration tests for T-031 run rankings."""

from __future__ import annotations

import json
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from orchestration.dispatch import run_work_unit
from orchestration.models import CandidateRecord, ShardCommit
from ranking import SCORE_V0
from runs.models import ConfigVersion, RunRanking, RunRankingEntry
from runs.ranking import RankingPersistenceError, persist_run_rankings
from runs.services import create_qc_run
from snapshots.models import Snapshot
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot

BDD100K_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "normalized-snapshot-v1.json"


@pytest.fixture
def qa_user(db: None) -> User:
    user = User.objects.create_user(username="ranking-qa", password="password123")
    RoleAssignment.objects.create(user=user, role=Role.QA_LEAD, dataset_id=42)
    return user


@pytest.fixture
def other_user(db: None) -> User:
    user = User.objects.create_user(username="ranking-other", password="password123")
    RoleAssignment.objects.create(user=user, role=Role.QA_LEAD, dataset_id=99)
    return user


@pytest.fixture
def snapshot(db: None, qa_user: User) -> Snapshot:
    shapes = [
        {
            "id": index + 10,
            "type": "rectangle",
            "frame": index,
            "label_id": 4,
            "points": [index, index, index + 10, index + 10],
        }
        for index in range(3)
    ]
    return create_locked_snapshot(
        dataset_id=42,
        created_by=qa_user,
        taxonomy_version="tax-v1",
        guideline_version="guide-v1",
        jobs=[
            JobExport(
                cvat_job_id=101,
                cvat_task_id=9,
                source_updated_at="2026-10-10T00:00:00Z",
                annotations={"shapes": shapes, "tracks": []},
                frames=[
                    FrameExport(
                        frame_index=index,
                        file_name=f"{index:06d}.jpg",
                        width=100,
                        height=100,
                        media_bytes=f"frame-{index}".encode(),
                        media_storage_key=f"frames/{index}.jpg",
                    )
                    for index in range(3)
                ],
            )
        ],
    )


@pytest.fixture
def config(db: None, qa_user: User) -> ConfigVersion:
    return ConfigVersion.objects.create(
        name="ranking-config",
        status=ConfigVersion.Status.PUBLISHED,
        payload={"shard_size": 10},
        created_by=qa_user,
        published_by=qa_user,
        published_at=timezone.now(),
    )


def _candidate(confidence: str = "0.8") -> dict[str, object]:
    return {
        "engine": "detector",
        "engine_version": "1.0.0",
        "family": "E1",
        "frame": {"cvat_task_id": 9, "frame_number": 0},
        "anchor": {
            "kind": "prediction_region",
            "objects": [{"namespace": "prediction", "id": "p-1"}],
            "policy_version": "1.0.0",
            "rule_id": "DET-01",
        },
        "evidence": {"engine": "detector", "confidence": confidence},
    }


def _run(snapshot: Snapshot, config: ConfigVersion, user: User):
    return create_qc_run(
        snapshot_id=snapshot.pk,
        config_version_id=config.pk,
        seed=31,
        created_by=user,
    )[0]


def _job_from_normalized(raw: dict[str, object]) -> JobExport:
    frames = raw["frames"]
    assert isinstance(frames, list)
    shapes = [shape for frame in frames for shape in frame["shapes"]]
    annotations = {
        "shapes": [
            {
                "id": shape["source"]["id"],
                "type": "rectangle",
                "frame": shape["frame_index"],
                "label_id": shape["label_id"],
                "points": shape["points"],
                "attributes": shape["attributes"],
                "occluded": shape["occluded"],
                "outside": shape["outside"],
                "rotation": shape["rotation"],
                "z_order": shape["z_order"],
            }
            for shape in shapes
        ]
        + [{"id": 999, "type": "polygon", "frame": 0, "label_id": 4}],
        "tracks": [],
    }
    return JobExport(
        cvat_job_id=int(raw["cvat_job_id"]),
        cvat_task_id=int(raw["cvat_task_id"]),
        source_updated_at=str(raw["source_updated_at"]),
        assignee_cvat_user_id=int(raw["assignee_cvat_user_id"]),
        annotations=annotations,
        frames=tuple(
            FrameExport(
                frame_index=int(frame["frame_index"]),
                source_frame_id=int(frame["source_frame_id"]),
                file_name=str(frame["file_name"]),
                width=int(frame["width"]),
                height=int(frame["height"]),
                media_bytes=f"frame-{frame['frame_index']}".encode(),
                media_storage_key=str(frame["media"]["storage_key"]),
                media_mime_type=str(frame["media"]["mime_type"]),
            )
            for frame in frames
        ),
    )


@pytest.mark.django_db
def test_persistence_is_idempotent_and_reproducible_across_runs(
    snapshot: Snapshot, config: ConfigVersion, qa_user: User
) -> None:
    first_run = _run(snapshot, config, qa_user)
    second_run = _run(snapshot, config, qa_user)

    first = persist_run_rankings(
        run_id=first_run.pk, candidates=[_candidate()], audit_percent=Decimal("50")
    )
    replay = persist_run_rankings(
        run_id=first_run.pk, candidates=[_candidate()], audit_percent=Decimal("50")
    )
    second = persist_run_rankings(
        run_id=second_run.pk, candidates=[_candidate()], audit_percent=Decimal("50")
    )

    assert [item.pk for item in first] == [item.pk for item in replay]
    assert {(item.source, item.content_hash, item.ranking_hash) for item in first} == {
        (item.source, item.content_hash, item.ranking_hash) for item in second
    }
    assert {item.source for item in first} == set(RunRanking.Source.values)
    assert len({item.ranking_hash for item in first}) == len(first)
    assert RunRankingEntry.objects.filter(ranking__run=first_run).count() == 14
    first_run.refresh_from_db()
    assert first_run.score_version == SCORE_V0

    with pytest.raises(RankingPersistenceError, match="different normalized content"):
        persist_run_rankings(
            run_id=first_run.pk,
            candidates=[_candidate("0.7")],
            audit_percent=Decimal("50"),
        )


@pytest.mark.django_db
def test_ranking_endpoint_serves_risk_and_random_with_scope_protection(
    snapshot: Snapshot,
    config: ConfigVersion,
    qa_user: User,
    other_user: User,
) -> None:
    run = _run(snapshot, config, qa_user)
    rankings = persist_run_rankings(
        run_id=run.pk, candidates=[_candidate()], audit_percent=Decimal("50")
    )
    by_source = {item.source: item for item in rankings}
    client = APIClient()
    client.force_authenticate(user=qa_user)

    risk = client.get(f"/api/runs/{run.pk}/ranking/")
    assert risk.status_code == 200
    assert risk.data["source"] == RunRanking.Source.RISK
    assert risk.data["content_hash"] == by_source[RunRanking.Source.RISK].content_hash
    assert risk.data["ranking_hash"] == by_source[RunRanking.Source.RISK].ranking_hash
    assert len(risk.data["results"]) == 3
    assert risk.data["results"][0]["score_version"] == SCORE_V0
    assert risk.data["results"][0]["explanation"]["contributions"]

    random_queue = client.get(f"/api/runs/{run.pk}/ranking/", {"queue": "random"})
    assert random_queue.status_code == 200
    assert random_queue.data["source"] == RunRanking.Source.RANDOM_AUDIT
    assert len(random_queue.data["results"]) == 2

    family = client.get(f"/api/runs/{run.pk}/ranking/", {"family": "E1"})
    assert family.status_code == 200
    assert len(family.data["results"]) == 1
    assert client.get(f"/api/runs/{run.pk}/ranking/", {"queue": "invalid"}).status_code == 400

    client.force_authenticate(user=other_user)
    assert client.get(f"/api/runs/{run.pk}/ranking/").status_code == 403


@pytest.mark.django_db
def test_ranking_endpoint_returns_404_until_ranking_is_persisted(
    snapshot: Snapshot, config: ConfigVersion, qa_user: User
) -> None:
    run = _run(snapshot, config, qa_user)
    client = APIClient()
    client.force_authenticate(user=qa_user)
    response = client.get(f"/api/runs/{run.pk}/ranking/")
    assert response.status_code == 404
    assert response.data["code"] == "NOT_FOUND"


@pytest.mark.django_db
def test_overlapping_jobs_and_structural_warning_preserve_complete_ranking(
    qa_user: User, config: ConfigVersion
) -> None:
    def job(job_id: int, frame_indexes: range) -> JobExport:
        return JobExport(
            cvat_job_id=job_id,
            cvat_task_id=9,
            source_updated_at="2026-10-10T00:00:00Z",
            annotations={
                "shapes": [
                    {
                        "id": index + 100,
                        "type": "rectangle",
                        "frame": index,
                        "label_id": 4,
                        "points": [0, 0, 10, 10],
                    }
                    for index in frame_indexes
                ],
                "tracks": [],
            },
            frames=tuple(
                FrameExport(
                    frame_index=index,
                    file_name=f"{index}.jpg",
                    width=100,
                    height=100,
                    media_bytes=f"frame-{index}".encode(),
                    media_storage_key=f"frames/{index}.jpg",
                )
                for index in frame_indexes
            ),
        )

    overlap = create_locked_snapshot(
        dataset_id=42,
        created_by=qa_user,
        taxonomy_version="tax-v1",
        guideline_version="guide-v1",
        jobs=[job(101, range(3)), job(102, range(2, 5))],
    )
    run = _run(overlap, config, qa_user)
    e3 = _candidate()
    e3["family"] = "E3"
    e3["anchor"] = {
        "kind": "annotation_cluster",
        "objects": [{"id": "a"}, {"id": "b"}],
    }
    warning = {
        **_candidate(),
        "family": "structural",
        "evidence": {"rule_id": "A-007", "actual": "missing"},
    }
    rankings = persist_run_rankings(
        run_id=run.pk,
        candidates=[e3, warning, warning],
        audit_percent=Decimal("40"),
    )

    risk = next(item for item in rankings if item.source == RunRanking.Source.RISK)
    assert risk.entries.count() == 5
    overlap_entry = risk.entries.get(snapshot_frame__frame_index=0)
    assert overlap_entry.issue_counts == {"E3": 1}
    assert len(overlap_entry.explanation["structural_warnings"]) == 1
    frame_two = risk.entries.get(snapshot_frame__frame_index=2)
    assert len(frame_two.explanation["snapshot_frame_provenance"]) == 2


@pytest.mark.django_db(transaction=True)
def test_bdd100k_worker_pipeline_persists_reproducible_ranking_and_api(
    qa_user: User,
) -> None:
    raw_bytes = BDD100K_FIXTURE.read_bytes()
    fixture = json.loads(raw_bytes)
    fixture_sha256 = sha256(raw_bytes).hexdigest()
    snapshot = create_locked_snapshot(
        dataset_id=fixture["dataset_id"],
        created_by=qa_user,
        taxonomy_version=fixture["taxonomy_version"],
        guideline_version=fixture["guideline_version"],
        jobs=[_job_from_normalized(fixture["jobs"][0])],
        provenance={"fixture": str(BDD100K_FIXTURE), "fixture_sha256": fixture_sha256},
    )
    config = ConfigVersion.objects.create(
        name="bdd100k-ranking-pipeline",
        status=ConfigVersion.Status.PUBLISHED,
        payload={
            "shard_size": 50,
            "sampling": {"random_audit_percent": 50},
            "engines": {"duplicate": {"enabled": True}},
        },
        engines={"duplicate": {"enabled": True}},
        created_by=qa_user,
        published_by=qa_user,
        published_at=timezone.now(),
    )

    runs = [_run(snapshot, config, qa_user), _run(snapshot, config, qa_user)]
    for run in runs:
        for unit in run.work_units.order_by("shard_index"):
            run_work_unit.apply(args=[unit.pk]).get()
        run.refresh_from_db()
        assert run.status == run.Status.COMPLETED
        assert run.score_version == SCORE_V0
        assert CandidateRecord.objects.filter(run=run, family="E3").exists()
        assert RunRanking.objects.filter(run=run).count() == len(RunRanking.Source.values)

    assert snapshot.provenance["fixture_sha256"] == fixture_sha256
    first_outputs = list(
        ShardCommit.objects.filter(run=runs[0])
        .order_by("engine", "shard_index")
        .values_list("output_sha256", flat=True)
    )
    second_outputs = list(
        ShardCommit.objects.filter(run=runs[1])
        .order_by("engine", "shard_index")
        .values_list("output_sha256", flat=True)
    )
    assert first_outputs == second_outputs
    first_hashes = list(
        RunRanking.objects.filter(run=runs[0])
        .order_by("source")
        .values_list("content_hash", "ranking_hash")
    )
    second_hashes = list(
        RunRanking.objects.filter(run=runs[1])
        .order_by("source")
        .values_list("content_hash", "ranking_hash")
    )
    assert first_hashes == second_hashes

    client = APIClient()
    client.force_authenticate(user=qa_user)
    response = client.get(f"/api/runs/{runs[0].pk}/ranking/")
    assert response.status_code == 200
    assert (
        response.data["ranking_hash"]
        == dict(RunRanking.objects.filter(run=runs[0]).values_list("source", "ranking_hash"))[
            RunRanking.Source.RISK
        ]
    )


def test_runtime_ranking_schema_matches_static_contract_types() -> None:
    schema = SchemaGenerator().get_schema(public=True)
    assert schema is not None
    operation = schema["paths"]["/api/runs/{id}/ranking/"]["get"]
    parameters = {item["name"]: item for item in operation["parameters"]}

    assert set(operation["responses"]) == {"200", "400", "403", "404"}
    assert parameters["cursor"]["schema"]["type"] == "string"
    assert set(parameters["family"]["schema"]["enum"]) == {
        "E1",
        "E2",
        "E3",
        "structural",
    }
    assert set(parameters["review_state"]["schema"]["enum"]) == {
        "unreviewed",
        "in_review",
        "incomplete",
        "reviewed",
        "awaiting_followup",
        "completed",
    }
    assert schema["components"]["schemas"]["RankedFrame"]["properties"]["lease_holder_user_id"] == {
        "type": "integer",
        "nullable": True,
        "readOnly": True,
    }
