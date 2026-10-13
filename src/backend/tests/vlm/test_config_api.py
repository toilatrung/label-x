"""M04A-01: ConfigVersion kiểm schema models.vlm và thresholds.classification_routing."""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from runs.config_versions import create_config_version, publish_config_version
from runs.models import ConfigVersion
from runs.routing_config import validate_routing_thresholds
from runs.serializers import ConfigVersionCreateSerializer
from runs.services import BusinessRuleUnmetError
from tests.vlm.test_contract import VALID

ENGINES = {"schema": {"enabled": True}}


def _data(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"name": "n", "engines": ENGINES}
    base.update(over)
    return base


def test_serializer_accepts_valid_vlm_and_routing() -> None:
    ser = ConfigVersionCreateSerializer(
        data=_data(
            models={"vlm": VALID},
            thresholds={
                "classification_routing": {"score_threshold": 0.85, "margin_threshold": 0.15}
            },
        )
    )
    assert ser.is_valid(), ser.errors


@pytest.mark.parametrize(
    "models",
    [{"vlm": {**VALID, "model": "other"}}, {"vlm": {**VALID, "api_key": "sk-x"}}, {"vlm": []}],
)
def test_serializer_rejects_bad_vlm(models: dict[str, Any]) -> None:
    ser = ConfigVersionCreateSerializer(data=_data(models=models))
    assert not ser.is_valid() and "models" in ser.errors
    assert "sk-x" not in str(ser.errors)


@pytest.mark.parametrize(
    "routing",
    [
        {"score_threshold": 1.5},
        {"margin_threshold": -0.1},
        {"score_threshold": "0.8"},
        {"score_threshold": True},
        {"score_threshold": float("nan")},
        {"extra": 1},
    ],
)
def test_routing_invalid(routing: dict[str, Any]) -> None:
    assert validate_routing_thresholds({"classification_routing": routing})
    ser = ConfigVersionCreateSerializer(data=_data(thresholds={"classification_routing": routing}))
    assert not ser.is_valid() and "thresholds" in ser.errors


def test_routing_absent_or_partial_is_ok() -> None:
    assert validate_routing_thresholds({}) == []
    assert validate_routing_thresholds({"classification_routing": {}}) == []
    assert validate_routing_thresholds({"classification_routing": {"score_threshold": 0}}) == []
    assert validate_routing_thresholds({"classification_routing": "x"})


@pytest.mark.django_db
def test_publish_blocks_invalid_ai_config_and_allows_valid() -> None:
    user = User.objects.create_user("cfg-admin")
    bad = create_config_version(
        name="bad",
        engines=ENGINES,
        thresholds={"classification_routing": {"score_threshold": 9}},
        models={},
        created_by=user,
        idempotency_key="k-bad",
    )
    with pytest.raises(BusinessRuleUnmetError):
        publish_config_version(config_id=bad.pk, actor=user)
    bad.refresh_from_db()
    assert bad.status == "draft"
    ok = create_config_version(
        name="ok",
        engines=ENGINES,
        thresholds={"classification_routing": {"score_threshold": 0.85}},
        models={"vlm": VALID},
        created_by=user,
        idempotency_key="k-ok",
    )
    assert publish_config_version(config_id=ok.pk, actor=user).status == "published"


def _actor(role: Role) -> APIClient:
    user = User.objects.create_user(username=f"vlm-cfg-{role}")
    RoleAssignment.objects.create(user=user, role=role, dataset_id=1)
    client = APIClient()
    client.force_authenticate(user)
    return client


def _post(client: APIClient, key: str, **over: Any) -> Any:
    body = {"name": "n", "engines": ENGINES, **over}
    return client.post("/api/config-versions/", body, format="json", HTTP_IDEMPOTENCY_KEY=key)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "vlm",
    [
        {**VALID, "model": ["qwen3-vl-plus"]},
        {**VALID, "model": {"a": 1}},
        {**VALID, "prompt_version": ["vlm-prompt-v0"]},
        {**VALID, "base_url": "https://dashscope.aliyuncs.com:99999/v1"},
        {**VALID, "base_url": "https://dashscope.aliyuncs.com/v1?api_key=sk-x"},
        {**VALID, "base_url": "https://dashscope.aliyuncs.com/v1\r\nX: 1"},
        {**VALID, "api_key_env": "DJANGO_SECRET_KEY"},
        {**VALID, "api_key_env": ["x"]},
        {**VALID, "budget": {"max_calls": 10**12}},
        {**VALID, "timeout_seconds": 0.0001},
    ],
)
def test_http_create_rejects_bad_vlm_with_400_never_500(vlm: dict[str, Any]) -> None:
    resp = _post(_actor(Role.QC_ADMIN), f"k-{id(vlm)}", models={"vlm": vlm})
    assert resp.status_code == 400, resp.content[:200]
    assert not ConfigVersion.objects.exists()
    assert "sk-x" not in resp.content.decode()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("area", "payload"),
    [
        ("models", {"other": {"api_key": "sk-leak-1"}}),
        ("models", {"api_key": "sk-leak-2"}),
        ("thresholds", {"api_key": "sk-leak-3"}),
        ("thresholds", {"nested": [{"Authorization": "Bearer sk-leak-4"}]}),
        ("models", {"vlm": {**VALID, "api_key": "sk-leak-5"}}),
        ("thresholds", {"client-secret": "sk-leak-6"}),
        ("thresholds", {"password": "x"}),
        ("thresholds", {"token": "x"}),
        ("thresholds", {"Cookie": "x"}),
        ("thresholds", {"access_token": "x"}),
    ],
)
def test_http_create_rejects_secret_like_keys_in_every_area(
    area: str, payload: dict[str, Any]
) -> None:
    resp = _post(_actor(Role.QC_ADMIN), f"s-{area}-{id(payload)}", **{area: payload})
    assert resp.status_code == 400
    assert "sk-leak" not in resp.content.decode() and not ConfigVersion.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_http_secret_key_in_engine_params_is_rejected() -> None:
    engines = {**ENGINES, "schema": {"enabled": True, "params": {"api_key": "sk-leak-7"}}}
    resp = _post(_actor(Role.QC_ADMIN), "e-1", engines=engines)
    assert resp.status_code == 400 and "sk-leak-7" not in resp.content.decode()


@pytest.mark.django_db(transaction=True)
def test_http_valid_config_with_benign_keys_is_created_and_publish_checks_again() -> None:
    client = _actor(Role.QC_ADMIN)
    ok = _post(
        client,
        "ok-1",
        thresholds={"max_tokens": 5, "tokenizer": "x"},
        models={"vlm": {**VALID, "api_key_env": "DASHSCOPE_API_KEY"}},
    )
    assert ok.status_code == 201, ok.content[:300]
    # Dòng bẩn đi đường vòng (ORM) vẫn bị chặn ở publish bằng 422.
    bad = ConfigVersion.objects.create(
        name="dirty",
        engines=ENGINES,
        models={"vlm": VALID, "other": {"api_key": "sk-leak-8"}},  # chỉ khoá secret là lỗi
        created_by=User.objects.first(),
        idempotency_key="dirty-1",
    )
    dirty_vlm = ConfigVersion.objects.create(
        name="dirty-vlm",
        engines=ENGINES,
        models={"vlm": {**VALID, "model": ["x"]}},
        created_by=User.objects.first(),
        idempotency_key="dirty-2",
    )
    assert client.post(f"/api/config-versions/{dirty_vlm.pk}/publish/").status_code == 422
    resp = client.post(f"/api/config-versions/{bad.pk}/publish/")
    assert resp.status_code == 422
    assert resp.json()["code"] == "BUSINESS_RULE_UNMET"
    assert "sk-leak-8" not in resp.content.decode()
    bad.refresh_from_db()
    assert bad.status == "draft"
    assert client.post(f"/api/config-versions/{ok.data['id']}/publish/").status_code == 200
