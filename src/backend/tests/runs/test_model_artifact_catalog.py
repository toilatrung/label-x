"""Detector editing selects registered artifacts and creates immutable QC versions."""

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
