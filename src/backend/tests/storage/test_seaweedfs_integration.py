"""Opt-in integration check against the committed SeaweedFS dev stack.

Run after ``make infra-up`` with:
``LABELX_RUN_S3_INTEGRATION=1 uv run pytest tests/storage/test_seaweedfs_integration.py -q``.
"""

from __future__ import annotations

import os

import pytest

from storage import ObjectStorage

pytestmark = pytest.mark.skipif(
    os.getenv("LABELX_RUN_S3_INTEGRATION") != "1",
    reason="set LABELX_RUN_S3_INTEGRATION=1 and start the dev stack",
)


def test_put_head_get_and_presign_against_seaweedfs() -> None:
    storage = ObjectStorage.from_django_settings("evidence")
    payload = b"LabelX T-014 SeaweedFS integration payload"

    first = storage.put(payload, extension="txt", content_type="text/plain")
    second = storage.put(payload, extension="txt", content_type="text/plain")

    assert first.key == second.key
    assert storage.head(first.key) is not None
    assert storage.get(first.key) == payload
    assert storage.presigned_get_url(first.key, is_allowed=lambda _key: True).startswith("http")
