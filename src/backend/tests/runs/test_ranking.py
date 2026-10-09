"""Persistence and HTTP integration tests for T-031 run rankings."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from ranking import SCORE_V0
from runs.models import ConfigVersion, RunRanking, RunRankingEntry
from runs.ranking import RankingPersistenceError, persist_run_rankings
from runs.services import create_qc_run
from snapshots.models import Snapshot
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot


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
