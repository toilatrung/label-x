"""Dataset selectors are scoped to LabelX grants and read CVAT only."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment

pytestmark = pytest.mark.django_db(transaction=True)


class FakeCvat:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def list_projects(self):
        return [{"id": 42, "name": "Urban"}, {"id": 99, "name": "Private"}]

    def get_project(self, id_):
        return {"id": id_, "name": "Urban" if id_ == 42 else "Private"}

    def list_tasks(self, *, project_id):
        assert project_id == 42
        return [{"id": 9, "name": "Day", "project_id": 42}]

    def list_jobs(self, *, task_id):
        assert task_id == 9
        return [
            {
                "id": 17,
                "task_id": 9,
                "assignee": {"id": 3},
                "frame_count": 12,
                "updated_date": "2026-10-09T07:05:45Z",
            }
        ]


def _client(role: Role, dataset_id: int | None) -> APIClient:
    user = get_user_model().objects.create_user(username=f"selector-{role}-{dataset_id}")
    RoleAssignment.objects.create(user=user, role=role, dataset_id=dataset_id)
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_scoped_user_sees_only_assigned_project_and_can_select_jobs(monkeypatch):
    monkeypatch.setattr("snapshots.dataset_views._client", FakeCvat)
    client = _client(Role.QA_LEAD, 42)

    listing = client.get("/api/datasets/")
    assert listing.status_code == 200
    assert listing.data["results"] == [
        {
            "id": 42,
            "cvat_project_id": 42,
            "name": "Urban",
            "taxonomy_version": None,
            "guideline_version": None,
        }
    ]

    tree = client.get("/api/datasets/42/tasks/")
    assert tree.status_code == 200
    assert tree.data == [
        {
            "cvat_task_id": 9,
            "name": "Day",
            "jobs": [
                {
                    "cvat_job_id": 17,
                    "assignee_cvat_user_id": 3,
                    "frame_count": 12,
                    "updated_date": "2026-10-09T07:05:45Z",
                }
            ],
        }
    ]

    denied = client.get("/api/datasets/99/tasks/")
    assert denied.status_code == 403
    assert denied.data["code"] == "OUT_OF_SCOPE"


def test_global_admin_can_list_projects_but_readonly_role_cannot_select_tasks(monkeypatch):
    monkeypatch.setattr("snapshots.dataset_views._client", FakeCvat)
    admin = _client(Role.QC_ADMIN, None)
    listing = admin.get("/api/datasets/")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.data["results"]] == [42, 99]

    annotator = _client(Role.ANNOTATOR, 42)
    assert annotator.get("/api/datasets/42/tasks/").status_code == 403


def test_cvat_task_from_other_project_is_rejected(monkeypatch):
    class WrongProject(FakeCvat):
        def list_tasks(self, *, project_id):
            return [{"id": 9, "name": "Private", "project_id": 99}]

    monkeypatch.setattr("snapshots.dataset_views._client", WrongProject)
    client = _client(Role.QA_LEAD, 42)
    response = client.get("/api/datasets/42/tasks/")
    assert response.status_code == 502


def test_global_dataset_list_paginates_and_rejects_invalid_cursor(monkeypatch):
    class ManyProjects(FakeCvat):
        def list_projects(self):
            return [{"id": id_, "name": f"Project {id_}"} for id_ in range(1, 53)]

    monkeypatch.setattr("snapshots.dataset_views._client", ManyProjects)
    client = _client(Role.SUPER_ADMIN, None)

    first = client.get("/api/datasets/")
    assert first.status_code == 200
    assert len(first.data["results"]) == 50
    assert first.data["next"].endswith("cursor=50")

    second = client.get("/api/datasets/?cursor=50")
    assert second.status_code == 200
    assert [item["id"] for item in second.data["results"]] == [51, 52]
    assert second.data["next"] is None

    invalid = client.get("/api/datasets/?cursor=not-a-number")
    assert invalid.status_code == 400


def test_cvat_nonexistent_dataset_tasks_returns_404_not_found(monkeypatch):
    import httpx

    class MissingProject(FakeCvat):
        def get_project(self, id_):
            request = httpx.Request("GET", f"http://cvat.example.test/api/projects/{id_}")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("Not Found", request=request, response=response)

    monkeypatch.setattr("snapshots.dataset_views._client", MissingProject)
    client = _client(Role.SUPER_ADMIN, None)
    response = client.get("/api/datasets/999/tasks/")
    assert response.status_code == 404
    assert response.data["code"] == "NOT_FOUND"


def test_scoped_user_skips_cvat_project_returning_404(monkeypatch):
    import httpx

    class OneProjectMissing(FakeCvat):
        def get_project(self, id_):
            if id_ == 99:
                request = httpx.Request("GET", f"http://cvat.example.test/api/projects/{id_}")
                response = httpx.Response(404, request=request)
                raise httpx.HTTPStatusError("Not Found", request=request, response=response)
            return super().get_project(id_)

    monkeypatch.setattr("snapshots.dataset_views._client", OneProjectMissing)
    user = get_user_model().objects.create_user(username="multi-project-user")
    RoleAssignment.objects.create(user=user, role=Role.QA_LEAD, dataset_id=42)
    RoleAssignment.objects.create(user=user, role=Role.QA_LEAD, dataset_id=99)
    client = APIClient()
    client.force_authenticate(user)

    response = client.get("/api/datasets/")
    assert response.status_code == 200
    assert response.data["results"] == [
        {
            "id": 42,
            "cvat_project_id": 42,
            "name": "Urban",
            "taxonomy_version": None,
            "guideline_version": None,
        }
    ]


def test_dataset_list_handles_empty_cursor_gracefully(monkeypatch):
    monkeypatch.setattr("snapshots.dataset_views._client", FakeCvat)
    client = _client(Role.SUPER_ADMIN, None)
    response = client.get("/api/datasets/?cursor=")
    assert response.status_code == 200
    assert len(response.data["results"]) == 2
