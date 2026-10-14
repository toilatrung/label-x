"""Saved VLM connections feed real worker requests without exposing credentials."""

import dataclasses
import json

import httpx
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from audit.models import AuditEvent
from runs.models import VlmConfiguration, VlmConnection
from vlm.client import DashScopeClient
from vlm.config import parse_vlm_config
from vlm.connection import connection_api_key, current_config
from vlm.errors import VlmProviderError

pytestmark = pytest.mark.django_db
URL = "/api/configuration/vlm/"
SECRET = "test-private-vlm-key"


def actor(role=Role.QC_ADMIN):
    user = User.objects.create_user(f"settings-{role}")
    RoleAssignment.objects.create(user=user, role=role, dataset_id=1)
    client = APIClient()
    client.force_authenticate(user)
    return client


def save(client, revision=0, **overrides):
    return client.patch(
        URL,
        {
            "expected_revision": revision,
            "base_url": "https://api.shopaikey.com/v1",
            "model": "qwen3-vl-plus",
            "api_key": SECRET,
            **overrides,
        },
        format="json",
    )


def test_save_encrypts_and_does_not_echo_secret():
    client = actor()
    assert client.get(URL).data["api_key_configured"] is False
    response = save(client)
    assert response.status_code == 200, response.data
    assert response.data["api_key_configured"] is True
    assert SECRET not in response.content.decode()
    assert SECRET not in client.get(URL).content.decode()
    connection = VlmConnection.objects.get()
    assert SECRET not in connection.encrypted_api_key
    assert SECRET not in json.dumps(list(AuditEvent.objects.values()), default=str)
    config = parse_vlm_config(current_config())
    assert connection_api_key(config) == SECRET
    from vlm.contract import CandidateContext, CropInput, VlmRequest

    request = VlmRequest(
        config=config,
        crop=CropInput(b"crop", "image/png"),
        taxonomy=(),
        context=CandidateContext("1", "revision", None),
    )
    assert DashScopeClient._api_key(request) == SECRET
    with pytest.raises(VlmProviderError):
        connection_api_key(
            dataclasses.replace(
                config, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
        )


def test_new_qc_config_inherits_and_pins_connection_with_idempotent_replay():
    client = actor()
    first = save(client).data["revision"]
    body = {"name": "VLM", "engines": {"vlm": {"enabled": True}}}
    created = client.post(
        "/api/config-versions/", body, format="json", HTTP_IDEMPOTENCY_KEY="vlm-new"
    )
    assert created.status_code == 201, created.data
    assert created.data["models"]["vlm"]["connection_id"] == first
    assert SECRET not in created.content.decode()
    published = client.post(f"/api/config-versions/{created.data['id']}/publish/")
    assert published.status_code == 200, published.data
    second = save(client, first, api_key="replacement-key").data["revision"]
    replay = client.post(
        "/api/config-versions/", body, format="json", HTTP_IDEMPOTENCY_KEY="vlm-new"
    )
    assert replay.data["models"]["vlm"]["connection_id"] == first
    assert current_config()["connection_id"] == second
    assert connection_api_key(parse_vlm_config(replay.data["models"]["vlm"])) == SECRET


def test_key_preserved_and_url_change_requires_new_key():
    client = actor()
    revision = save(client).data["revision"]
    body = {
        "expected_revision": revision,
        "model": "qwen3-vl-plus",
        "base_url": "https://api.shopaikey.com/v1",
    }
    preserved = client.patch(URL, body, format="json")
    assert preserved.status_code == 200
    assert connection_api_key(parse_vlm_config(current_config())) == SECRET
    body.update(
        expected_revision=preserved.data["revision"],
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )
    assert client.patch(URL, body, format="json").status_code == 400
    body["api_key"] = "dashscope-key"
    assert client.patch(URL, body, format="json").status_code == 200
    assert current_config()["api_key_env"] == "DASHSCOPE_API_KEY"


def test_conflict_and_invalid_host_do_not_change_connection():
    client = actor()
    revision = save(client).data["revision"]
    assert save(client).status_code == 409
    for url in [
        "http://127.0.0.1/v1",
        "https://example.com/v1",
        "https://api.shopaikey.com/v1?key=x",
        "https://[broken/v1",
    ]:
        assert save(client, revision, base_url=url).status_code == 400
    assert VlmConnection.objects.count() == 1
    assert VlmConfiguration.objects.get(pk=1).connection_id == revision


def test_read_only_role_cannot_update():
    client = actor(Role.QA_LEAD)
    assert client.get(URL).status_code == 200
    assert save(client).status_code == 403
    assert not VlmConnection.objects.exists()


def test_anonymous_and_csrf_writes_are_rejected():
    assert APIClient().get(URL).status_code == 403
    client = APIClient(enforce_csrf_checks=True)
    user = User.objects.create_user("csrf-user")
    RoleAssignment.objects.create(user=user, role=Role.QC_ADMIN)
    client.force_login(user)
    assert save(client).status_code == 403


def test_encrypted_key_used_for_provider_http_request():
    from vlm.contract import CandidateContext, CropInput, TaxonomyLabel, VlmRequest

    save(actor())
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    request = VlmRequest(
        config=parse_vlm_config(current_config()),
        crop=CropInput(b"crop", "image/png"),
        taxonomy=(TaxonomyLabel("1", "car"),),
        context=CandidateContext("1", "revision", "car"),
    )
    DashScopeClient(transport=httpx.MockTransport(handler)).complete(request)
    assert requests[0].headers["Authorization"] == f"Bearer {SECRET}"
    assert requests[0].url == "https://api.shopaikey.com/v1/chat/completions"


def test_publish_requires_vlm_connection_and_disabling_vlm_does_not_inherit():
    client = actor()
    response = client.post(
        "/api/config-versions/",
        {
            "name": "missing",
            "engines": {"vlm": {"enabled": True}},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="missing-vlm",
    )
    assert response.status_code == 201
    assert client.post(f"/api/config-versions/{response.data['id']}/publish/").status_code == 422
    save(client)
    response = client.post(
        "/api/config-versions/",
        {
            "name": "disabled",
            "engines": {"schema": {"enabled": True}, "vlm": {"enabled": False}},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="disabled-vlm",
    )
    assert response.status_code == 201
    assert "vlm" not in response.data["models"]


def test_credential_decryption_supports_django_key_rotation(settings):
    save(actor())
    config = parse_vlm_config(current_config())
    original = settings.SECRET_KEY
    settings.SECRET_KEY = "new-deployment-secret-for-test"
    settings.SECRET_KEY_FALLBACKS = [original]
    assert connection_api_key(config) == SECRET
    settings.SECRET_KEY_FALLBACKS = []
    with pytest.raises(VlmProviderError):
        connection_api_key(config)


@pytest.mark.parametrize("value", [-0.1, 1.1, True, False, "NaN", "Infinity"])
def test_invalid_confidence_threshold_is_rejected(value):
    response = save(actor(), confidence_threshold=value)
    assert response.status_code == 400
    assert not VlmConnection.objects.exists()


def test_threshold_is_frozen_in_qc_config_and_affects_routing():
    from orchestration.routing_policy import RoutingInput, RoutingPolicy, route

    client = actor()
    first = save(client, confidence_threshold=0.60)
    assert first.status_code == 200
    assert client.get(URL).data["confidence_threshold"] == 0.60
    body = {"name": "threshold", "engines": {"vlm": {"enabled": True}}}
    created = client.post(
        "/api/config-versions/", body, format="json", HTTP_IDEMPOTENCY_KEY="threshold"
    )
    assert created.status_code == 201, created.data
    threshold = created.data["thresholds"]["classification_routing"]
    assert threshold["score_threshold"] == 0.60
    policy = RoutingPolicy.from_config(threshold)
    candidate = RoutingInput(
        score=0.70,
        source_available=True,
        source_trusted=True,
        predicted_class_id=1,
        annotated_class_id=1,
        crop_valid=True,
    )
    assert not route(policy, candidate).call_qwen
    assert route(RoutingPolicy(score_threshold=0.85), candidate).call_qwen
    changed = save(client, first.data["revision"], confidence_threshold=0.90)
    assert changed.status_code == 200
    replay = client.post(
        "/api/config-versions/", body, format="json", HTTP_IDEMPOTENCY_KEY="threshold"
    )
    assert replay.data["thresholds"] == created.data["thresholds"]
    # Explicit run thresholds retain precedence; a supplied margin stays untouched.
    explicit = {
        **body,
        "thresholds": {
            "classification_routing": {
                "score_threshold": 0.30,
                "margin_threshold": 0.10,
            }
        },
    }
    response = client.post(
        "/api/config-versions/", explicit, format="json", HTTP_IDEMPOTENCY_KEY="explicit-threshold"
    )
    assert response.data["thresholds"] == explicit["thresholds"]


def test_omitting_threshold_on_save_preserves_previous_value():
    client = actor()
    revision = save(client, confidence_threshold=0.40).data["revision"]
    assert save(client, revision).data["confidence_threshold"] == 0.40
