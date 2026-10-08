from __future__ import annotations

import io
import logging
from collections.abc import Mapping
from contextlib import nullcontext
from typing import Any
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from storage import (
    ObjectStorage,
    ObjectStoragePermissionError,
    content_key,
    upload_then_commit,
)


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_calls = 0
        self.presign_calls = 0
        self.fail_upload = False

    def head_object(self, **kwargs: object) -> Mapping[str, Any]:
        location = (str(kwargs["Bucket"]), str(kwargs["Key"]))
        try:
            body = self.objects[location]
        except KeyError:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "missing"}}, "HeadObject"
            ) from None
        return {"ContentLength": len(body), "ETag": "fake-etag"}

    def put_object(self, **kwargs: object) -> Mapping[str, Any]:
        self.put_calls += 1
        if self.fail_upload:
            raise RuntimeError("upload failed")
        location = (str(kwargs["Bucket"]), str(kwargs["Key"]))
        self.objects[location] = bytes(kwargs["Body"])
        return {"ETag": "fake-etag"}

    def get_object(self, **kwargs: object) -> Mapping[str, Any]:
        location = (str(kwargs["Bucket"]), str(kwargs["Key"]))
        return {"Body": io.BytesIO(self.objects[location])}

    def generate_presigned_url(
        self, client_method: str, *, Params: Mapping[str, object], ExpiresIn: int
    ) -> str:
        self.presign_calls += 1
        return f"https://storage.invalid/{Params['Bucket']}/{Params['Key']}?ttl={ExpiresIn}"


def test_content_key_uses_documented_sha256_layout() -> None:
    key, digest = content_key(b"test", ".JPG")
    assert digest == "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
    assert key == f"sha256/9f/{digest}.jpg"


def test_put_same_content_twice_is_a_noop_and_get_round_trips() -> None:
    backend = FakeS3()
    storage = ObjectStorage(backend, "labelx-evidence")

    first = storage.put(b"same content", extension="json", content_type="application/json")
    second = storage.put(b"same content", extension="json", content_type="application/json")

    assert first.key == second.key
    assert first.created is True
    assert second.created is False
    assert backend.put_calls == 1
    assert len(backend.objects) == 1
    assert storage.get(first.key) == b"same content"


def test_upload_failure_does_not_call_metadata_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = FakeS3()
    backend.fail_upload = True
    storage = ObjectStorage(backend, "labelx-evidence")
    committed: list[str] = []
    atomic = Mock(return_value=nullcontext())
    monkeypatch.setattr("storage.client.transaction.atomic", atomic)

    with pytest.raises(RuntimeError, match="upload failed"):
        upload_then_commit(storage, b"payload", lambda blob: committed.append(blob.key))

    assert committed == []
    atomic.assert_not_called()


def test_metadata_callback_runs_after_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = FakeS3()
    storage = ObjectStorage(backend, "labelx-evidence")
    atomic = Mock(return_value=nullcontext())
    monkeypatch.setattr("storage.client.transaction.atomic", atomic)

    def commit(blob: object) -> str:
        assert backend.put_calls == 1
        assert len(backend.objects) == 1
        return "metadata-id"

    blob, result = upload_then_commit(storage, b"payload", commit)
    assert blob.created is True
    assert result == "metadata-id"
    atomic.assert_called_once_with()


def test_presigned_url_checks_permission_before_signing(settings: Any) -> None:
    settings.OBJECT_STORAGE_PRESIGNED_TTL_SECONDS = 120
    backend = FakeS3()
    storage = ObjectStorage(backend, "labelx-evidence")

    with pytest.raises(ObjectStoragePermissionError):
        storage.presigned_get_url("private/key", is_allowed=lambda _key: False)
    assert backend.presign_calls == 0

    url = storage.presigned_get_url("allowed/key", is_allowed=lambda _key: True)
    assert url.endswith("?ttl=120")
    assert backend.presign_calls == 1

    with pytest.raises(ValueError, match="between 1 and 3600"):
        storage.presigned_get_url("allowed/key", is_allowed=lambda _key: True, expires_in=0)
    assert backend.presign_calls == 1


def test_credentials_never_appear_in_logs(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    access_key = "sensitive-access-key"
    secret_key = "sensitive-secret-key"
    backend = FakeS3()
    settings.STORAGES = {
        "evidence": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": "labelx-evidence",
                "endpoint_url": "https://storage.invalid",
                "access_key": access_key,
                "secret_key": secret_key,
                "region_name": "us-east-1",
            },
        }
    }
    monkeypatch.setattr("storage.client.boto3.client", lambda *_args, **_kwargs: backend)

    with caplog.at_level(logging.DEBUG, logger="storage.client"):
        storage = ObjectStorage.from_django_settings("evidence")
        storage.put(b"payload")
        storage.put(b"payload")

    assert access_key not in caplog.text
    assert secret_key not in caplog.text
    assert "labelx-evidence" in caplog.text
