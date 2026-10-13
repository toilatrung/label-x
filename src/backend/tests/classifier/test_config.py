"""M04B-03: config classifier — tạo (400) và publish (422) theo ModelArtifact/class map."""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth.models import User

from classifier.config import CLASS_MAP_VERSION, CLASSES
from runs.config_versions import create_config_version, publish_config_version
from runs.models import ModelArtifact
from runs.serializers import ConfigVersionCreateSerializer
from runs.services import BusinessRuleUnmetError

ENGINES = {"schema": {"enabled": True}, "classifier": {"enabled": True}}
SHA = "a" * 64


def make_artifact(**over: Any) -> ModelArtifact:
    fields: dict[str, Any] = {
        "name": "convnext-tiny-labelx",
        "version": "smoke-1",
        "checksum": SHA,
        "class_mapping_version": CLASS_MAP_VERSION,
        "class_mapping": {"version": CLASS_MAP_VERSION, "classes": list(CLASSES)},
        "artifact_key": "classifier/smoke-1",
    }
    fields.update(over)
    return ModelArtifact.objects.create(**fields)


def _data(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"name": "n", "engines": ENGINES}
    base.update(over)
    return base


def test_serializer_accepts_classifier_engine_and_model_ref() -> None:
    ser = ConfigVersionCreateSerializer(data=_data(models={"classifier": {"model_artifact_id": 3}}))
    assert ser.is_valid(), ser.errors


@pytest.mark.parametrize(
    "models",
    [
        {"classifier": []},
        {"classifier": {}},
        {"classifier": {"model_artifact_id": "3"}},
        {"classifier": {"model_artifact_id": True}},
        {"classifier": {"model_artifact_id": 0}},
        {"classifier": {"model_artifact_id": 1, "path": "/etc/passwd"}},
        {"classifier": {"model_artifact_id": 1, "command": "rm -rf /"}},
    ],
)
def test_serializer_rejects_bad_classifier_models(models: dict[str, Any]) -> None:
    ser = ConfigVersionCreateSerializer(data=_data(models=models))
    assert not ser.is_valid() and "models" in ser.errors
    assert "/etc/passwd" not in str(ser.errors) and "rm -rf" not in str(ser.errors)


@pytest.fixture
def user(db: None) -> User:
    return User.objects.create_user("clf-admin")


def _draft(user: User, *, engines: dict[str, Any] = ENGINES, models: dict[str, Any] | None = None):
    return create_config_version(
        name="c",
        engines=engines,
        thresholds={},
        models=models or {},
        created_by=user,
        idempotency_key=f"k-{id(models)}-{len(engines)}-{ModelArtifact.objects.count()}",
    )


@pytest.mark.django_db
def test_publish_blocks_enabled_classifier_without_models(user: User) -> None:
    config = _draft(user)
    with pytest.raises(BusinessRuleUnmetError, match="thiếu models.classifier"):
        publish_config_version(config_id=config.pk, actor=user)
    config.refresh_from_db()
    assert config.status == "draft"


@pytest.mark.django_db
def test_publish_blocks_missing_artifact(user: User) -> None:
    config = _draft(user, models={"classifier": {"model_artifact_id": 999999}})
    with pytest.raises(BusinessRuleUnmetError, match="không trỏ tới ModelArtifact"):
        publish_config_version(config_id=config.pk, actor=user)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"checksum": "xyz"}, "checksum sha256"),
        ({"checksum": ""}, "checksum sha256"),
        ({"artifact_key": ""}, "artifact_key"),
        ({"class_mapping_version": "other-v1"}, "class map"),
        ({"class_mapping": {}}, "class map"),
        (
            {"class_mapping": {"version": CLASS_MAP_VERSION, "classes": list(CLASSES[:9])}},
            "class map",
        ),
        (
            {"class_mapping": {"version": CLASS_MAP_VERSION, "classes": [*CLASSES[:9], "unknown"]}},
            "class map",
        ),
    ],
)
def test_publish_blocks_artifact_without_manifest_or_class_map(
    user: User, override: dict[str, Any], message: str
) -> None:
    artifact = make_artifact(**override)
    config = _draft(user, models={"classifier": {"model_artifact_id": artifact.pk}})
    with pytest.raises(BusinessRuleUnmetError, match=message):
        publish_config_version(config_id=config.pk, actor=user)
    config.refresh_from_db()
    assert config.status == "draft"


@pytest.mark.django_db
def test_publish_allows_valid_classifier_and_disabled_classifier(user: User) -> None:
    artifact = make_artifact()
    ok = _draft(user, models={"classifier": {"model_artifact_id": artifact.pk}})
    assert publish_config_version(config_id=ok.pk, actor=user).status == "published"
    off = _draft(user, engines={"schema": {"enabled": True}, "classifier": {"enabled": False}})
    assert publish_config_version(config_id=off.pk, actor=user).status == "published"
