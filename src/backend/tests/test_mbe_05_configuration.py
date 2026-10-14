"""Tests cho MBE-05: Configuration (models, guideline versions, rules, workflow permissions).

Scope:
- GET /api/models/, PATCH /api/models/{id}/
- GET /api/guidelines/versions/
- GET /api/config-versions/{id}/rules/
- PATCH /api/auth/workflow-permissions/rules/{rule}/
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment, WorkflowRule, ensure_default_workflow_rules
from audit.models import AuditEvent
from guideline.models import GuidelineRule, GuidelineVersion
from runs.models import AIModel, ConfigVersion, ModelKind

pytestmark = pytest.mark.django_db


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def make_user():
    def _make(username: str, role: Role | None = None) -> User:
        user = User.objects.create_user(username=username, password="password123")
        if role is not None:
            dataset_id = None if role in (Role.SUPER_ADMIN, Role.QC_ADMIN) else 1
            RoleAssignment.objects.create(user=user, role=role.value, dataset_id=dataset_id)
        return user

    return _make


@pytest.fixture
def super_admin(make_user) -> User:
    return make_user("super_admin_user", Role.SUPER_ADMIN)


@pytest.fixture
def qc_admin(make_user) -> User:
    return make_user("qc_admin_user", Role.QC_ADMIN)


@pytest.fixture
def data_model_owner(make_user) -> User:
    return make_user("dmo_user", Role.DATA_MODEL_OWNER)


@pytest.fixture
def qa_lead(make_user) -> User:
    return make_user("qa_lead_user", Role.QA_LEAD)


@pytest.fixture
def annotator(make_user) -> User:
    return make_user("annotator_user", Role.ANNOTATOR)


# ==============================================================================
# Part 1: /api/models/ and /api/models/{id}/
# ==============================================================================


def test_models_list_happy_path_and_filtering(
    client: APIClient, super_admin: User, qa_lead: User, annotator: User
) -> None:
    AIModel.objects.create(
        name="faster-rcnn-model",
        kind=ModelKind.DETECTOR,
        version="v1.0.0",
        enabled=True,
        revision=1,
    )
    AIModel.objects.create(
        name="qwen-vl-model",
        kind=ModelKind.VLM,
        version="v0.2.0",
        enabled=False,
        revision=1,
    )

    # QA Lead has read access
    client.force_authenticate(user=qa_lead)
    resp = client.get("/api/models/")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert len(data["results"]) == 2
    assert "next" in data
    assert "previous" in data

    # Filter by kind
    resp_filter = client.get("/api/models/?kind=detector")
    assert resp_filter.status_code == status.HTTP_200_OK
    assert len(resp_filter.json()["results"]) == 1
    assert resp_filter.json()["results"][0]["name"] == "faster-rcnn-model"

    # Invalid kind returns 400
    resp_bad = client.get("/api/models/?kind=unknown_kind")
    assert resp_bad.status_code == status.HTTP_400_BAD_REQUEST

    # Annotator cannot list models (403)
    client.force_authenticate(user=annotator)
    resp_ann = client.get("/api/models/")
    assert resp_ann.status_code == status.HTTP_403_FORBIDDEN

    # Anonymous cannot list models (403)
    client.force_authenticate(user=None)
    resp_anon = client.get("/api/models/")
    assert resp_anon.status_code == status.HTTP_403_FORBIDDEN


def test_models_patch_happy_path(client: APIClient, data_model_owner: User) -> None:
    model = AIModel.objects.create(
        name="faster-rcnn-patch",
        kind=ModelKind.DETECTOR,
        version="1.0.0",
        enabled=True,
        revision=1,
    )

    client.force_authenticate(user=data_model_owner)
    patch_payload = {
        "expected_revision": 1,
        "enabled": False,
        "version": "1.0.1",
    }
    resp = client.patch(f"/api/models/{model.id}/", patch_payload, format="json")
    assert resp.status_code == status.HTTP_200_OK
    res_data = resp.json()
    assert res_data["enabled"] is False
    assert res_data["version"] == "1.0.1"
    assert res_data["revision"] == 2

    model.refresh_from_db()
    assert model.enabled is False
    assert model.version == "1.0.1"
    assert model.revision == 2

    # Verify audit event
    audit = AuditEvent.objects.filter(object_type="model", object_id=str(model.id)).first()
    assert audit is not None
    assert audit.action == "model.update"
    assert audit.revision == "2"
    assert audit.after["enabled"] is False


def test_models_patch_revision_mismatch_409(client: APIClient, qc_admin: User) -> None:
    model = AIModel.objects.create(
        name="detector-rev-test",
        kind=ModelKind.DETECTOR,
        version="1.0.0",
        enabled=True,
        revision=3,
    )
    client.force_authenticate(user=qc_admin)
    resp = client.patch(
        f"/api/models/{model.id}/",
        {"expected_revision": 1, "enabled": False},
        format="json",
    )
    assert resp.status_code == status.HTTP_409_CONFLICT
    assert resp.json()["code"] == "INVALID_TRANSITION"


def test_models_patch_attached_to_published_config_422(
    client: APIClient, super_admin: User
) -> None:
    model = AIModel.objects.create(
        name="detector-published",
        kind=ModelKind.DETECTOR,
        version="1.0.0",
        enabled=True,
        revision=1,
    )
    # Published ConfigVersion referencing this model
    ConfigVersion.objects.create(
        name="published-config-1",
        status=ConfigVersion.Status.PUBLISHED,
        models={"detector": {"model_id": model.id, "name": model.name, "version": model.version}},
    )

    client.force_authenticate(user=super_admin)
    resp = client.patch(
        f"/api/models/{model.id}/",
        {"expected_revision": 1, "enabled": False},
        format="json",
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert resp.json()["code"] == "BUSINESS_RULE_UNMET"


def test_models_patch_permissions_403(client: APIClient, qa_lead: User, annotator: User) -> None:
    model = AIModel.objects.create(
        name="detector-perms",
        kind=ModelKind.DETECTOR,
        version="1.0.0",
        enabled=True,
        revision=1,
    )

    # QA Lead has read-only access (403 for PATCH)
    client.force_authenticate(user=qa_lead)
    resp = client.patch(
        f"/api/models/{model.id}/",
        {"expected_revision": 1, "enabled": False},
        format="json",
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # Annotator (403 for PATCH)
    client.force_authenticate(user=annotator)
    resp_ann = client.patch(
        f"/api/models/{model.id}/",
        {"expected_revision": 1, "enabled": False},
        format="json",
    )
    assert resp_ann.status_code == status.HTTP_403_FORBIDDEN


def test_models_patch_not_found_404(client: APIClient, super_admin: User) -> None:
    client.force_authenticate(user=super_admin)
    resp = client.patch(
        "/api/models/999999/",
        {"expected_revision": 1, "enabled": False},
        format="json",
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


# ==============================================================================
# Part 2: /api/guidelines/versions/
# ==============================================================================


def test_guidelines_versions_list_happy_path(client: APIClient, annotator: User) -> None:
    v1 = GuidelineVersion.objects.create(
        version_tag="v1",
        name="Guideline v1",
        file_checksum=hashlib.sha256(b"v1").hexdigest(),
    )
    v2 = GuidelineVersion.objects.create(
        version_tag="v2",
        name="Guideline v2",
        file_checksum=hashlib.sha256(b"v2").hexdigest(),
    )
    GuidelineRule.objects.create(version=v1, rule_id="R1", section="§1", content="c1")
    GuidelineRule.objects.create(version=v2, rule_id="R1", section="§1", content="c1")
    GuidelineRule.objects.create(version=v2, rule_id="R2", section="§2", content="c2")

    # Annotator has read access to guideline versions
    client.force_authenticate(user=annotator)
    resp = client.get("/api/guidelines/versions/")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert "results" in data
    results = data["results"]
    assert len(results) == 2

    # Latest version (v2) has is_current = True
    v2_entry = next(r for r in results if r["version"] == "v2")
    assert v2_entry["is_current"] is True
    assert v2_entry["rule_count"] == 2
    assert v2_entry["effective_from"] is not None

    v1_entry = next(r for r in results if r["version"] == "v1")
    assert v1_entry["is_current"] is False
    assert v1_entry["rule_count"] == 1


def test_guidelines_versions_list_unauthenticated_403(client: APIClient) -> None:
    client.force_authenticate(user=None)
    resp = client.get("/api/guidelines/versions/")
    assert resp.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# Part 3: /api/config-versions/{id}/rules/
# ==============================================================================


def test_config_versions_rules_happy_path(client: APIClient, qa_lead: User) -> None:
    config = ConfigVersion.objects.create(
        name="qc-config-1",
        status=ConfigVersion.Status.DRAFT,
        engines={"schema": {"enabled": True, "strict": True}, "geometry": {"enabled": False}},
        thresholds={
            "release_thresholds": {"min_iou": 0.8},
            "classification_routing": {"score_threshold": 0.5},
        },
        payload={
            "rules": [
                {
                    "rule_id": "custom-rule-1",
                    "name": "Custom 1",
                    "enabled": True,
                    "parameters": {"p": 1},
                },
            ],
            "sampling_policy": {"rate": 0.1},
        },
    )

    client.force_authenticate(user=qa_lead)
    resp = client.get(f"/api/config-versions/{config.id}/rules/")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["config_version_id"] == config.id
    assert data["status"] == "draft"
    assert len(data["rules"]) == 1
    assert data["rules"][0]["rule_id"] == "custom-rule-1"
    assert data["release_thresholds"] == {"min_iou": 0.8}
    assert data["sampling_policy"] == {"rate": 0.1}


def test_config_versions_rules_fallback_to_engines(
    client: APIClient, data_model_owner: User
) -> None:
    config = ConfigVersion.objects.create(
        name="qc-config-engines-fallback",
        status=ConfigVersion.Status.PUBLISHED,
        engines={"duplicate": {"enabled": True, "threshold": 0.95}},
        thresholds={"release": {"gate_pass_rate": 0.99}},
        payload={},
    )
    client.force_authenticate(user=data_model_owner)
    resp = client.get(f"/api/config-versions/{config.id}/rules/")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert len(data["rules"]) == 1
    assert data["rules"][0]["rule_id"] == "engine-duplicate"
    assert data["rules"][0]["enabled"] is True
    assert data["release_thresholds"] == {"gate_pass_rate": 0.99}


def test_config_versions_rules_not_found_404(client: APIClient, qa_lead: User) -> None:
    client.force_authenticate(user=qa_lead)
    resp = client.get("/api/config-versions/999999/rules/")
    assert resp.status_code == status.HTTP_404_NOT_FOUND


def test_config_versions_rules_permission_403(client: APIClient, annotator: User) -> None:
    config = ConfigVersion.objects.create(
        name="qc-config-ann",
        status=ConfigVersion.Status.DRAFT,
        engines={"schema": {"enabled": True}},
    )
    client.force_authenticate(user=annotator)
    resp = client.get(f"/api/config-versions/{config.id}/rules/")
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_config_versions_create_and_rules_retrieval(client: APIClient, qc_admin: User) -> None:
    client.force_authenticate(user=qc_admin)
    create_payload = {
        "name": "cfg-with-rules",
        "engines": {"schema": {"enabled": True}},
        "thresholds": {"classification_routing": {"score_threshold": 0.7, "margin_threshold": 0.2}},
        "rules": [
            {"rule_id": "rule-xyz", "name": "Rule XYZ", "enabled": True, "parameters": {"k": "v"}}
        ],
        "release_thresholds": {"pass_rate": 0.95},
        "sampling_policy": {"strategy": "stratified", "sample_size": 50},
    }
    idempotency_key = f"key-{uuid.uuid4()}"
    resp_create = client.post(
        "/api/config-versions/",
        create_payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=idempotency_key,
    )
    assert resp_create.status_code == status.HTTP_201_CREATED
    config_id = resp_create.json()["id"]

    # Now fetch rules via the new endpoint
    resp_rules = client.get(f"/api/config-versions/{config_id}/rules/")
    assert resp_rules.status_code == status.HTTP_200_OK
    data = resp_rules.json()
    assert data["config_version_id"] == config_id
    assert len(data["rules"]) == 1
    assert data["rules"][0]["rule_id"] == "rule-xyz"
    assert data["release_thresholds"] == {"pass_rate": 0.95}
    assert data["sampling_policy"] == {"strategy": "stratified", "sample_size": 50}


# ==============================================================================
# Part 4: /api/auth/workflow-permissions/rules/{rule}/
# ==============================================================================


def test_workflow_permissions_rules_patch_happy_path(
    client: APIClient, qc_admin: User, qa_lead: User
) -> None:
    ensure_default_workflow_rules()
    rule = WorkflowRule.objects.get(rule="anti_self_review")
    assert rule.enforced is False
    assert rule.revision == 1

    client.force_authenticate(user=qc_admin)
    resp = client.patch(
        f"/api/auth/workflow-permissions/rules/{rule.rule}/",
        {"enforced": True, "expected_revision": 1, "reason": "Enable anti_self_review"},
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["rule"] == "anti_self_review"
    assert data["enforced"] is True
    assert data["revision"] == 2

    rule.refresh_from_db()
    assert rule.enforced is True
    assert rule.revision == 2

    # Audit event recorded
    audit = AuditEvent.objects.filter(object_type="workflow_rule", object_id=rule.rule).first()
    assert audit is not None
    assert audit.action == "workflow_rule.update"
    assert audit.revision == "2"
    assert audit.reason == "Enable anti_self_review"

    # GET /api/auth/workflow-permissions/ reflects updated rule
    client.force_authenticate(user=qa_lead)
    resp_get = client.get("/api/auth/workflow-permissions/")
    assert resp_get.status_code == status.HTTP_200_OK
    rule_data = next(r for r in resp_get.json()["rules"] if r["rule"] == "anti_self_review")
    assert rule_data["enforced"] is True
    assert rule_data["revision"] == 2


def test_workflow_permissions_rules_patch_revision_mismatch_409(
    client: APIClient, super_admin: User
) -> None:
    ensure_default_workflow_rules()
    client.force_authenticate(user=super_admin)
    resp = client.patch(
        "/api/auth/workflow-permissions/rules/anti_self_review/",
        {"enforced": True, "expected_revision": 999},
        format="json",
    )
    assert resp.status_code == status.HTTP_409_CONFLICT
    assert resp.json()["code"] == "INVALID_TRANSITION"


def test_workflow_permissions_rules_patch_locked_rule_422(
    client: APIClient, super_admin: User
) -> None:
    ensure_default_workflow_rules()
    # audit_logging is locked
    locked_rule = WorkflowRule.objects.get(rule="audit_logging")
    assert locked_rule.locked is True

    client.force_authenticate(user=super_admin)
    # Attempting to turn it off returns 422
    resp_fail = client.patch(
        "/api/auth/workflow-permissions/rules/audit_logging/",
        {"enforced": False, "expected_revision": locked_rule.revision},
        format="json",
    )
    assert resp_fail.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert resp_fail.json()["code"] == "BUSINESS_RULE_UNMET"

    # Keeping it on or re-enabling returns 200
    resp_ok = client.patch(
        "/api/auth/workflow-permissions/rules/audit_logging/",
        {"enforced": True, "expected_revision": locked_rule.revision},
        format="json",
    )
    assert resp_ok.status_code == status.HTTP_200_OK
    assert resp_ok.json()["enforced"] is True


def test_workflow_permissions_rules_patch_permissions_403(
    client: APIClient, qa_lead: User, annotator: User
) -> None:
    ensure_default_workflow_rules()

    # QA Lead has read-only access (403 for PATCH)
    client.force_authenticate(user=qa_lead)
    resp_qa = client.patch(
        "/api/auth/workflow-permissions/rules/anti_self_review/",
        {"enforced": True, "expected_revision": 1},
        format="json",
    )
    assert resp_qa.status_code == status.HTTP_403_FORBIDDEN

    # Annotator (403 for PATCH)
    client.force_authenticate(user=annotator)
    resp_ann = client.patch(
        "/api/auth/workflow-permissions/rules/anti_self_review/",
        {"enforced": True, "expected_revision": 1},
        format="json",
    )
    assert resp_ann.status_code == status.HTTP_403_FORBIDDEN


def test_workflow_permissions_rules_patch_not_found_404(client: APIClient, qc_admin: User) -> None:
    ensure_default_workflow_rules()
    client.force_authenticate(user=qc_admin)
    resp = client.patch(
        "/api/auth/workflow-permissions/rules/non_existent_rule/",
        {"enforced": True, "expected_revision": 1},
        format="json",
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND
