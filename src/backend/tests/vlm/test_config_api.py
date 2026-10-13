"""M04A-01: ConfigVersion kiểm schema models.vlm và thresholds.classification_routing."""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth.models import User

from runs.config_versions import create_config_version, publish_config_version
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
