"""Model registration stays separate from immutable analysis configurations."""

import uuid

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from runs.models import ConfigVersion, ModelArtifact

pytestmark = pytest.mark.django_db


def test_catalog_to_published_config_preserves_previous_version():
    user = User.objects.create_user(username="detector-config-admin")
    RoleAssignment.objects.create(user=user, role=Role.QC_ADMIN, dataset_id=None)
    client = APIClient()
    client.force_authenticate(user)
    artifact = ModelArtifact.objects.create(
        name="BDD Detector",
        version="bdd-v1",
        checksum="a" * 64,
        class_mapping_version="bdd-10",
        class_mapping={"classes": ["car"]},
        artifact_key="s3://private-artifact-path",
    )
    previous = ConfigVersion.objects.create(
        name="previous",
        status="published",
        models={},
        engines={"detector": {"enabled": True}},
    )
    catalog = client.get("/api/model-artifacts/")
    assert catalog.status_code == 200
    assert catalog.json() == [
        {
            "id": artifact.pk,
            "name": artifact.name,
            "version": artifact.version,
            "checksum": artifact.checksum,
            "class_mapping_version": "bdd-10",
            "class_mapping": {"classes": ["car"]},
        }
    ]
    choice = catalog.json()[0]
    created = client.post(
        "/api/config-versions/",
        {
            "name": "Detector settings",
            "engines": {"detector": {"enabled": True}},
            "models": {"name": choice["name"], "version": choice["version"]},
            "thresholds": {},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert created.status_code == 201
    published = client.post(f"/api/config-versions/{created.json()['id']}/publish/")
    assert published.status_code == 200
    assert published.json()["models"] == {"name": artifact.name, "version": artifact.version}
    previous.refresh_from_db()
    assert previous.models == {}


@pytest.mark.parametrize("role,expected", [(Role.QA_LEAD, 200), (Role.ANNOTATOR, 403)])
def test_catalog_permissions(role, expected):
    user = User.objects.create_user(username=f"catalog-{role}")
    RoleAssignment.objects.create(user=user, role=role, dataset_id=1)
    client = APIClient()
    client.force_authenticate(user)
    assert client.get("/api/model-artifacts/").status_code == expected


def test_catalog_requires_authentication():
    assert APIClient().get("/api/model-artifacts/").status_code == 403


@pytest.mark.parametrize(
    "role,dataset_id,expected",
    [
        (Role.QC_ADMIN, None, 200),
        (Role.SUPER_ADMIN, None, 200),
        (Role.QC_ADMIN, 1, 403),
        (Role.QA_LEAD, 1, 403),
        (Role.ANNOTATOR, 1, 403),
    ],
)
def test_registration_permissions_and_no_config_mutation(monkeypatch, role, dataset_id, expected):
    from audit.models import AuditEvent

    user = User.objects.create_user(username="register-admin")
    RoleAssignment.objects.create(user=user, role=role, dataset_id=dataset_id)
    client = APIClient()
    client.force_authenticate(user)
    previous = ConfigVersion.objects.create(name="unchanged", status="published", models={})
    invocations = []

    def register(*args, **kwargs):
        invocations.append((args, kwargs))
        ModelArtifact.objects.get_or_create(
            name="Verified Detector",
            version="v1",
            defaults={"checksum": "b" * 64, "class_mapping_version": "bdd-10"},
        )

    monkeypatch.setattr("runs.model_artifact_views.call_command", register)
    response = client.post("/api/model-artifacts/register/")
    assert response.status_code == expected
    if expected == 200:
        assert invocations[0][0] == ("check_detector",)
        assert invocations[0][1]["register"] is True
        assert response.json()[0]["name"] == "Verified Detector"
        assert AuditEvent.objects.filter(action="model_artifacts.register").exists()
        assert client.post("/api/model-artifacts/register/").status_code == 200
        assert ModelArtifact.objects.count() == 1
    else:
        assert not invocations
    previous.refresh_from_db()
    assert previous.models == {}
    assert ConfigVersion.objects.count() == 1


def test_registration_failure_is_safe_and_rejects_client_model_data(monkeypatch):
    from django.core.management.base import CommandError

    user = User.objects.create_user(username="register-failure")
    RoleAssignment.objects.create(user=user, role=Role.QC_ADMIN, dataset_id=None)
    client = APIClient()
    client.force_authenticate(user)

    def fail(*args, **kwargs):
        raise CommandError("private worker token or path")

    monkeypatch.setattr("runs.model_artifact_views.call_command", fail)
    response = client.post("/api/model-artifacts/register/")
    assert response.status_code == 503
    assert "private worker" not in response.content.decode()
    assert not ModelArtifact.objects.exists()
    assert not ConfigVersion.objects.exists()
    assert (
        client.post(
            "/api/model-artifacts/register/", {"checksum": "spoofed"}, format="json"
        ).status_code
        == 400
    )
    assert APIClient().post("/api/model-artifacts/register/").status_code == 403
