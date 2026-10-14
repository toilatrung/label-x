"""MBE-06: real PostgreSQL aggregates; CVAT metadata is explicitly mocked."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from audit.services import append_audit_event
from orchestration.models import CandidateRecord, LedgerUnit, ShardCommit
from review.models import FrameReview, Issue, ReviewDecision
from runs.models import ConfigVersion, EngineResult, QCRun, WorkUnit
from snapshots.models import Snapshot
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot

pytestmark = pytest.mark.django_db


def validate_response(contract, schema_name, response):
    from jsonschema import Draft7Validator, FormatChecker

    def json_schema(value):
        if isinstance(value, list):
            return [json_schema(item) for item in value]
        if not isinstance(value, dict):
            return value
        converted = {key: json_schema(item) for key, item in value.items() if key != "nullable"}
        if value.get("nullable"):
            return {"anyOf": [converted, {"type": "null"}]}
        return converted

    schema = {
        "$ref": f"#/components/schemas/{schema_name}",
        "components": {"schemas": json_schema(contract["components"]["schemas"])},
    }
    Draft7Validator(schema, format_checker=FormatChecker()).validate(response.json())


class Cvat:
    def __init__(self, user=None):
        pass

    projects = [{"id": 42, "name": "Urban"}, {"id": 99, "name": "Private"}]
    tasks = [{"id": 9, "name": "Day", "project_id": 42}]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def list_projects(self):
        return self.projects

    def get_project(self, id_):
        import httpx

        for row in self.projects:
            if row["id"] == id_:
                return row
        response = httpx.Response(
            404, request=httpx.Request("GET", "http://cvat.test/api/projects/")
        )
        raise httpx.HTTPStatusError("missing", request=response.request, response=response)

    def list_tasks(self, *, project_id):
        assert project_id == 42
        return self.tasks


def api_for(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


def snapshot(user, *, dataset=42, tasks=(9,), frames=2, offset=100):
    return create_locked_snapshot(
        dataset_id=dataset,
        created_by=user,
        taxonomy_version="t",
        guideline_version="g",
        jobs=[
            JobExport(
                cvat_job_id=offset + i,
                cvat_task_id=task,
                source_updated_at=f"test-{offset}",
                annotations={"shapes": [], "tracks": []},
                frames=[
                    FrameExport(
                        frame_index=j,
                        file_name=f"{j}.jpg",
                        width=10,
                        height=10,
                        media_bytes=f"{offset}-{j}".encode(),
                        media_storage_key=f"test/{offset}/{j}",
                    )
                    for j in range(frames)
                ],
            )
            for i, task in enumerate(tasks)
        ],
    )


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setattr("runs.summary_views._client", Cvat)
    monkeypatch.setattr("snapshots.summary_views._client", Cvat)
    user = User.objects.create_user(username="summary-reader")
    RoleAssignment.objects.create(user=user, role=Role.QA_LEAD, dataset_id=42)
    cfg = ConfigVersion.objects.create(name="published", created_by=user, status="published")
    snap = snapshot(user)
    run = QCRun.objects.create(
        snapshot=snap,
        config_version=cfg,
        created_by=user,
        dataset_id=42,
        scope_hash=snap.revision_sha256,
        seed=123,
        status="completed",
    )
    return {"user": user, "cfg": cfg, "snap": snap, "run": run, "api": api_for(user)}


def run_url(world, suffix):
    return f"/api/runs/{world['run'].pk}/{suffix}/"


def add_reviews(world):
    frames = list(world["snap"].jobs.first().frames.order_by("frame_index"))
    a = FrameReview.objects.create(run=world["run"], snapshot_frame=frames[0], state="reviewed")
    b = FrameReview.objects.create(run=world["run"], snapshot_frame=frames[1], state="incomplete")
    first = Issue.objects.create(
        frame_review=a, family="E1", origin="reviewer", state="confirmed", anchor={}
    )
    Issue.objects.create(
        frame_review=b, family="E2", origin="reviewer", state="pending_review", anchor={}
    )
    return a, b, first


def test_metrics_are_counts_of_source_rows_not_candidate_or_quality_scores(world):
    add_reviews(world)
    response = world["api"].get(run_url(world, "metrics"))
    assert response.status_code == 200
    assert response.data == {
        "run_id": world["run"].pk,
        "status": "completed",
        "frames_total": 2,
        "frames_reviewed": 1,
        "issues_total": 2,
        "issues_by_family": {"E1": 1, "E2": 1},
        "issues_by_state": {"confirmed": 1, "pending_review": 1},
        "reviewed_ratio": 0.5,
    }


def test_empty_run_and_zero_denominator_are_explicit(world):
    empty = Snapshot.objects.create(
        dataset_id=42,
        created_by=world["user"],
        taxonomy_version="t",
        guideline_version="g",
        schema_version="test",
        status="pending",
    )
    QCRun.objects.filter(pk=world["run"].pk).update(snapshot=empty)
    response = world["api"].get(run_url(world, "metrics"))
    assert response.status_code == 200 and response.data["frames_total"] == 0
    assert response.data["reviewed_ratio"] is None and response.data["issues_by_family"] == {}
    for suffix, key in [
        ("engines", "engines"),
        ("review-volume", "points"),
        ("candidate-categories", "categories"),
    ]:
        response = world["api"].get(run_url(world, suffix))
        assert response.status_code == 200 and response.data[key] == []


def test_overlapping_jobs_count_logical_frames_once(world):
    snap = snapshot(world["user"], tasks=(9, 9), offset=250)
    QCRun.objects.filter(pk=world["run"].pk).update(snapshot=snap)
    response = world["api"].get(run_url(world, "metrics"))
    assert response.status_code == 200 and response.data["frames_total"] == 2


def candidate(world, *, family="E1", index=1):
    shard, _ = ShardCommit.objects.get_or_create(
        run=world["run"],
        engine="geometry",
        shard_index=0,
        defaults={
            "idempotency_key": "test",
            "snapshot_id": world["snap"].pk,
            "engine_version": "1",
            "output_sha256": "a" * 64,
        },
    )
    return CandidateRecord.objects.create(
        run=world["run"],
        shard=shard,
        dedup_key=f"{index:064x}",
        engine="geometry",
        engine_version="1",
        family=family,
        cvat_task_id=9,
        frame_number=0,
        anchor={},
        policy_version="v1",
        evidence={},
        evidence_sha256="a" * 64,
    )


def test_candidates_and_engines_use_ledger_units_not_shard_count(world):
    candidate(world)
    candidate(world, family="E2", index=2)
    EngineResult.objects.create(run=world["run"], engine="geometry", status="partial")
    for i, outcome in enumerate(["completed", "failed"]):
        LedgerUnit.objects.create(
            run=world["run"],
            engine="geometry",
            kind="frame",
            cvat_task_id=9,
            frame_number=i,
            outcome=outcome,
        )
    when = datetime(2026, 10, 14, tzinfo=UTC)
    WorkUnit.objects.create(
        run=world["run"],
        engine="geometry",
        shard_key="one-shard",
        idempotency_key="test",
        started_at=when,
        finished_at=when + timedelta(milliseconds=120),
        status="completed",
    )
    data = world["api"].get(run_url(world, "engines")).data
    assert data["engines"] == [
        {
            "engine": "geometry",
            "status": "partial",
            "units_total": 2,
            "units_failed": 1,
            "candidates": 2,
            "duration_ms": 120,
        }
    ]
    data = world["api"].get(run_url(world, "candidate-categories")).data
    assert data["total"] == 2 and data["categories"] == [
        {"family": "E1", "count": 1, "share": 0.5},
        {"family": "E2", "count": 1, "share": 0.5},
    ]


def test_unavailable_duration_is_null(world):
    EngineResult.objects.create(run=world["run"], engine="vlm", status="not_checked")
    assert world["api"].get(run_url(world, "engines")).data["engines"][0]["duration_ms"] is None


def test_review_volume_uses_completion_audit_and_decisions_with_dates(world):
    frame, _, issue = add_reviews(world)
    when = datetime(2026, 10, 14, 10, tzinfo=UTC)
    with patch("django.utils.timezone.now", return_value=when):
        audit = append_audit_event(
            actor=world["user"],
            action="frame.complete",
            object_type="frame",
            object_id=frame.pk,
            revision="test",
            before=None,
            after={},
            reason="test fixture",
        )
        ReviewDecision.objects.create(
            issue=issue,
            actor=world["user"],
            actor_role="qa_lead",
            action="confirm",
            revision="test",
            audit_event=audit,
        )
    data = (
        world["api"]
        .get(run_url(world, "review-volume") + "?date_from=2026-10-14&date_to=2026-10-14")
        .data
    )
    assert data["points"] == [{"period_start": "2026-10-14", "frames_reviewed": 1, "decisions": 1}]
    week = world["api"].get(run_url(world, "review-volume") + "?granularity=week").data
    assert week["points"][0]["period_start"] == "2026-10-12"
    assert (
        not world["api"].get(run_url(world, "review-volume") + "?date_to=2026-10-13").data["points"]
    )


@pytest.mark.parametrize(
    "query", ["granularity=month", "date_from=bad", "date_from=2026-10-15&date_to=2026-10-14"]
)
def test_invalid_review_volume_query_is_400(world, query):
    assert world["api"].get(run_url(world, "review-volume") + "?" + query).status_code == 400


def test_task_quality_uses_real_metadata_and_source_counts(world):
    add_reviews(world)
    response = world["api"].get(run_url(world, "tasks-quality"))
    assert response.status_code == 200 and response.data["results"] == [
        {
            "cvat_task_id": 9,
            "name": "Day",
            "frames": 2,
            "issues": 2,
            "issue_rate": 1.0,
            "reviewed_ratio": 0.5,
        }
    ]


def test_dataset_summary_filters_scope_and_uses_latest_run_only(world):
    add_reviews(world)
    snapshot(world["user"], dataset=99, offset=400)
    data = world["api"].get("/api/datasets/summary/").data
    assert data["results"] == [
        {
            "dataset_id": 42,
            "name": "Urban",
            "snapshot_count": 1,
            "latest_snapshot_id": world["snap"].pk,
            "latest_run_id": world["run"].pk,
            "open_issue_count": 2,
            "reviewed_ratio": 0.5,
        }
    ]
    empty_run = QCRun.objects.create(
        snapshot=world["snap"],
        config_version=world["cfg"],
        created_by=world["user"],
        dataset_id=42,
        scope_hash="next",
        seed=999,
    )
    data = world["api"].get("/api/datasets/summary/").data["results"][0]
    assert data["latest_run_id"] == empty_run.pk and data["reviewed_ratio"] == 0


def test_dataset_without_snapshot_or_run_has_null_ids_not_fake_values(world):
    user = User.objects.create_user(username="global")
    RoleAssignment.objects.create(user=user, role=Role.QC_ADMIN, dataset_id=None)
    rows = api_for(user).get("/api/datasets/summary/").data["results"]
    assert rows[1] == {
        "dataset_id": 99,
        "name": "Private",
        "snapshot_count": 0,
        "latest_snapshot_id": None,
        "latest_run_id": None,
        "open_issue_count": 0,
        "reviewed_ratio": None,
    }


def test_snapshot_runs_preserves_seed_config_and_newest_order(world):
    second = QCRun.objects.create(
        snapshot=world["snap"],
        config_version=world["cfg"],
        created_by=world["user"],
        dataset_id=42,
        scope_hash="next",
        seed=456,
    )
    response = world["api"].get(f"/api/snapshots/{world['snap'].pk}/runs/")
    assert response.status_code == 200
    assert [r["id"] for r in response.data["results"]] == [second.pk, world["run"].pk]
    assert response.data["results"][0]["seed"] == 456
    assert response.data["results"][0]["config_version_id"] == world["cfg"].pk


def test_revisions_include_locked_only_and_distinct_frame_count(world):
    overlapping = snapshot(world["user"], tasks=(9, 9), offset=500)
    Snapshot.objects.create(
        dataset_id=42,
        created_by=world["user"],
        taxonomy_version="t",
        guideline_version="g",
        schema_version="test",
        status="failed",
    )
    response = world["api"].get("/api/datasets/42/revisions/")
    assert response.status_code == 200
    assert [r["snapshot_id"] for r in response.data["results"]] == [
        overlapping.pk,
        world["snap"].pk,
    ]
    assert [r["frame_count"] for r in response.data["results"]] == [2, 2]
    assert world["api"].get("/api/datasets/99/revisions/").status_code == 403


@pytest.mark.parametrize(
    "suffix", ["metrics", "engines", "review-volume", "tasks-quality", "candidate-categories"]
)
def test_no_auth_missing_scope_and_nonexistent_run(world, suffix):
    url = run_url(world, suffix)
    assert APIClient().get(url).status_code in (401, 403)
    user = User.objects.create_user(username="no-grants", is_superuser=True)
    assert api_for(user).get(url).status_code == 403
    RoleAssignment.objects.create(user=user, role=Role.QA_LEAD, dataset_id=99)
    assert api_for(user).get(url).status_code == 403
    assert world["api"].get(f"/api/runs/999999/{suffix}/").status_code == 404


@pytest.mark.parametrize(
    "path", ["/api/datasets/summary/", "/api/datasets/42/revisions/", "/api/snapshots/1/runs/"]
)
def test_invalid_cursor_rejected(world, path):
    if "snapshots" in path:
        path = f"/api/snapshots/{world['snap'].pk}/runs/"
    assert world["api"].get(path + "?cursor=invalid").status_code == 400


def test_list_query_counts_are_bounded_with_many_rows(world, monkeypatch):
    class Many(Cvat):
        projects = [{"id": i, "name": f"Source Project {i}"} for i in range(1, 53)]

    user = User.objects.create_user(username="bounded-global")
    RoleAssignment.objects.create(user=user, role=Role.QC_ADMIN, dataset_id=None)
    api = api_for(user)
    with CaptureQueriesContext(connection) as small:
        assert api.get("/api/datasets/summary/").status_code == 200
    monkeypatch.setattr("snapshots.summary_views._client", Many)
    with CaptureQueriesContext(connection) as large:
        response = api.get("/api/datasets/summary/")
    assert len(large) <= len(small) + 1
    assert len(response.data["results"]) == 50 and response.data["next"]
    assert len(api.get(response.data["next"]).data["results"]) == 2


def test_cvat_failure_is_not_success_with_fake_names(world, monkeypatch):
    class Broken(Cvat):
        def list_projects(self):
            raise RuntimeError("private details must not leak")

    monkeypatch.setattr("snapshots.summary_views._client", Broken)
    response = world["api"].get("/api/datasets/summary/")
    assert response.status_code == 502 and "private" not in str(response.data)


def test_stage_is_read_from_cvat_and_missing_stage_is_not_fabricated(world, monkeypatch):
    class Jobs(Cvat):
        def list_jobs(self, *, task_id):
            return [
                {
                    "id": 1,
                    "task_id": task_id,
                    "assignee": None,
                    "updated_date": "2026-10-14T10:00:00Z",
                    "stage": "validation",
                }
            ]

    monkeypatch.setattr("snapshots.dataset_views._client", Jobs)
    response = world["api"].get("/api/datasets/42/tasks/")
    assert response.status_code == 200 and response.data[0]["jobs"][0]["stage"] == "validation"


@pytest.mark.parametrize("role", list(Role))
def test_all_contract_roles_can_read_scoped_summaries(world, role):
    user = User.objects.create_user(username=f"summary-{role}")
    RoleAssignment.objects.create(user=user, role=role, dataset_id=42)
    api = api_for(user)
    for suffix in ("metrics", "engines", "review-volume", "tasks-quality", "candidate-categories"):
        assert api.get(run_url(world, suffix)).status_code == 200
    assert api.get("/api/datasets/summary/").status_code == 200
    assert api.get("/api/datasets/42/revisions/").status_code == 200
    assert api.get(f"/api/snapshots/{world['snap'].pk}/runs/").status_code == 200


def test_many_tasks_paginate_without_query_or_metadata_n_plus_one(world, monkeypatch):
    with CaptureQueriesContext(connection) as small:
        assert world["api"].get(run_url(world, "tasks-quality")).status_code == 200
    tasks = tuple(range(1, 53))
    snap = snapshot(world["user"], tasks=tasks, frames=1, offset=600)
    QCRun.objects.filter(pk=world["run"].pk).update(snapshot=snap)
    calls = []

    class ManyTasks(Cvat):
        def list_tasks(self, *, project_id):
            calls.append(project_id)
            return [{"id": i, "name": f"CVAT source task {i}", "project_id": 42} for i in tasks]

    monkeypatch.setattr("runs.summary_views._client", ManyTasks)
    with CaptureQueriesContext(connection) as large:
        first = world["api"].get(run_url(world, "tasks-quality"))
    assert len(large) <= len(small) + 1
    assert first.status_code == 200 and len(first.data["results"]) == 50
    second = world["api"].get(first.data["next"])
    assert [r["cvat_task_id"] for r in second.data["results"]] == [51, 52]
    assert calls == [42, 42] and second.data["previous"]
    previous = world["api"].get(second.data["previous"])
    assert [r["cvat_task_id"] for r in previous.data["results"]] == list(range(1, 51))


def test_snapshot_runs_paginate_and_prefetch_engines(world):
    url = f"/api/snapshots/{world['snap'].pk}/runs/"
    with CaptureQueriesContext(connection) as small:
        assert world["api"].get(url).status_code == 200
    for i in range(52):
        run = QCRun.objects.create(
            snapshot=world["snap"],
            config_version=world["cfg"],
            created_by=world["user"],
            dataset_id=42,
            scope_hash=f"page-{i}",
            seed=i,
        )
        EngineResult.objects.create(run=run, engine="geometry", status="not_checked")
    with CaptureQueriesContext(connection) as large:
        first = world["api"].get(url)
    assert len(large) <= len(small) + 1 and len(first.data["results"]) == 50
    second = world["api"].get(first.data["next"])
    assert len(second.data["results"]) == 3
    assert set(r["id"] for r in first.data["results"]).isdisjoint(
        r["id"] for r in second.data["results"]
    )


def test_dataset_revisions_distinguishes_empty_missing_and_denied(world):
    user = User.objects.create_user(username="revision-admin")
    RoleAssignment.objects.create(user=user, role=Role.QC_ADMIN, dataset_id=None)
    api = api_for(user)
    assert api.get("/api/datasets/99/revisions/").data["results"] == []
    assert api.get("/api/datasets/999/revisions/").status_code == 404
    assert api.get("/api/snapshots/999999/runs/").status_code == 404


def test_wrong_project_task_metadata_is_rejected(world, monkeypatch):
    class Wrong(Cvat):
        def list_tasks(self, *, project_id):
            return [{"id": 9, "name": "Private", "project_id": 99}]

    monkeypatch.setattr("runs.summary_views._client", Wrong)
    response = world["api"].get(run_url(world, "tasks-quality"))
    assert response.status_code == 502 and "Private" not in str(response.data)


def test_invalid_stage_does_not_escape_as_success(world, monkeypatch):
    class Jobs(Cvat):
        def list_jobs(self, *, task_id):
            return [
                {
                    "id": 1,
                    "task_id": task_id,
                    "updated_date": "2026-10-14T10:00:00Z",
                    "stage": "invented",
                }
            ]

    monkeypatch.setattr("snapshots.dataset_views._client", Jobs)
    assert world["api"].get("/api/datasets/42/tasks/").status_code == 502


@pytest.mark.parametrize(
    "suffix,schema_name",
    [
        ("metrics", "RunMetrics"),
        ("engines", "RunEngineStats"),
        ("review-volume", "ReviewVolume"),
        ("tasks-quality", "PaginatedTaskQualityList"),
        ("candidate-categories", "CandidateCategories"),
    ],
)
def test_response_required_fields_match_mbe00_contract(world, suffix, schema_name):
    from pathlib import Path

    import yaml

    spec = yaml.safe_load(
        (Path(__file__).resolve().parents[4] / "docs/04-api/openapi.yaml").read_text(
            encoding="utf8"
        )
    )
    add_reviews(world)
    candidate(world)
    EngineResult.objects.create(run=world["run"], engine="geometry", status="checked")
    response = world["api"].get(run_url(world, suffix))
    assert response.status_code == 200
    schema = spec["components"]["schemas"][schema_name]
    assert set(schema["required"]) <= response.data.keys()
    assert response.data.keys() <= schema["properties"].keys()
    validate_response(spec, schema_name, response)


@pytest.mark.parametrize(
    "path,schema_name",
    [
        ("/api/datasets/summary/", "PaginatedDatasetSummaryList"),
        ("/api/datasets/42/revisions/", "PaginatedDatasetRevisionList"),
    ],
)
def test_dataset_response_fields_match_mbe00_contract(world, path, schema_name):
    from pathlib import Path

    import yaml

    spec = yaml.safe_load(
        (Path(__file__).resolve().parents[4] / "docs/04-api/openapi.yaml").read_text(
            encoding="utf8"
        )
    )
    response = world["api"].get(path)
    assert response.status_code == 200
    schema = spec["components"]["schemas"][schema_name]
    assert set(schema["required"]) <= response.data.keys()
    assert response.data.keys() <= schema["properties"].keys()
    item_name = schema["properties"]["results"]["items"]["$ref"].rsplit("/", 1)[1]
    item_schema = spec["components"]["schemas"][item_name]
    for item in response.data["results"]:
        assert set(item_schema["required"]) <= item.keys()
        assert item.keys() <= item_schema["properties"].keys()
    validate_response(spec, schema_name, response)


def test_snapshot_runs_response_types_and_nullability_match_contract(world):
    from pathlib import Path

    import yaml

    spec = yaml.safe_load(
        (Path(__file__).resolve().parents[4] / "docs/04-api/openapi.yaml").read_text(
            encoding="utf8"
        )
    )
    response = world["api"].get(f"/api/snapshots/{world['snap'].pk}/runs/")
    assert response.status_code == 200
    validate_response(spec, "PaginatedRunList", response)


@pytest.mark.parametrize("position", ["not-numeric", "-1", "9" * 100, "１２３"])
def test_well_encoded_cursor_with_invalid_position_is_400_not_500(world, position):
    import base64
    from urllib.parse import urlencode

    cursor = base64.b64encode(urlencode({"p": position}).encode()).decode()
    query = "?" + urlencode({"cursor": cursor})
    for url in (
        run_url(world, "tasks-quality"),
        f"/api/snapshots/{world['snap'].pk}/runs/",
        "/api/datasets/42/revisions/",
    ):
        response = world["api"].get(url + query)
        assert response.status_code == 400
