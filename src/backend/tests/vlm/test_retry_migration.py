"""Existing saved connections adopt three retries without rewriting pinned revisions."""

from importlib import import_module
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import connection

from runs.models import ConfigVersion, VlmConfiguration, VlmConnection
from tests.vlm.test_contract import VALID

pytestmark = pytest.mark.django_db
upgrade = import_module("runs.migrations.0013_vlm_three_retries").upgrade_current_connection


def test_upgrade_creates_a_revision_and_preserves_published_config():
    previous = VlmConnection.objects.create(
        config=VALID, encrypted_api_key="encrypted", confidence_threshold=0.4
    )
    selection = VlmConfiguration.objects.create(pk=1, connection=previous)
    pinned = ConfigVersion.objects.create(
        status="published", models={"vlm": {**VALID, "connection_id": previous.pk}}
    )
    upgrade(apps, SimpleNamespace(connection=connection))
    selection.refresh_from_db()
    previous.refresh_from_db()
    pinned.refresh_from_db()
    current = selection.connection
    assert current.pk != previous.pk
    assert current.config == {**VALID, "max_attempts": 4}
    assert current.encrypted_api_key == previous.encrypted_api_key
    assert current.confidence_threshold == previous.confidence_threshold
    assert previous.config == VALID
    assert pinned.models["vlm"] == {**VALID, "connection_id": previous.pk}
    upgrade(apps, SimpleNamespace(connection=connection))
    assert VlmConnection.objects.count() == 2


@pytest.mark.parametrize("attempts", [1, 2, 4])
def test_upgrade_preserves_explicit_attempt_limits(attempts):
    previous = VlmConnection.objects.create(
        config={**VALID, "max_attempts": attempts}, encrypted_api_key="encrypted"
    )
    selection = VlmConfiguration.objects.create(pk=1, connection=previous)
    upgrade(apps, SimpleNamespace(connection=connection))
    selection.refresh_from_db()
    assert selection.connection_id == previous.pk
    assert VlmConnection.objects.count() == 1


def test_upgrade_without_saved_connection_is_noop():
    upgrade(apps, SimpleNamespace(connection=connection))
    assert not VlmConnection.objects.exists()
