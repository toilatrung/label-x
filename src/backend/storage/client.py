"""S3-compatible storage with content-addressed, idempotent writes.

Blobs are uploaded before callers commit relational metadata.  This ordering
prevents a committed database row from pointing at an object that was never
successfully written (NFR-06).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

_NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}


class S3Client(Protocol):
    """Small subset of the boto3 S3 client used by this module."""

    def head_object(self, **kwargs: object) -> Mapping[str, Any]: ...

    def get_object(self, **kwargs: object) -> Mapping[str, Any]: ...

    def put_object(self, **kwargs: object) -> Mapping[str, Any]: ...

    def generate_presigned_url(
        self, client_method: str, *, Params: Mapping[str, object], ExpiresIn: int
    ) -> str: ...


class ObjectStorageConfigurationError(ValueError):
    """The selected Django storage alias is not configured for S3."""


class ObjectStoragePermissionError(PermissionError):
    """The caller is not allowed to read the requested object."""


@dataclass(frozen=True, slots=True)
class Blob:
    """Stable reference returned after a content-addressed upload."""

    bucket: str
    key: str
    sha256: str
    size: int
    created: bool


@dataclass(frozen=True, slots=True)
class ObjectHead:
    """Safe object metadata returned by HEAD (credentials are never included)."""

    bucket: str
    key: str
    size: int
    etag: str | None
    content_type: str | None


def content_key(content: bytes, extension: str | None = None) -> tuple[str, str]:
    """Return ``(key, digest)`` using the canonical SHA-256 key layout.

    ``extension`` remains accepted for caller compatibility, but it does not
    participate in the key: identical bytes must always resolve to one object.
    """

    digest = hashlib.sha256(content).hexdigest()
    return f"sha256/{digest[:2]}/{digest}", digest


def _is_not_found(error: ClientError) -> bool:
    code = str(error.response.get("Error", {}).get("Code", ""))
    return code in _NOT_FOUND_CODES


class ObjectStorage:
    """Access one S3 bucket without exposing credentials to consumers or logs."""

    def __init__(self, client: S3Client, bucket: str) -> None:
        if not bucket.strip():
            raise ObjectStorageConfigurationError("object storage bucket is required")
        self._client = client
        self.bucket = bucket

    @classmethod
    def from_django_settings(cls, alias: str = "evidence") -> ObjectStorage:
        """Build a client from ``STORAGES[alias]`` without logging its secrets."""

        try:
            config = settings.STORAGES[alias]
        except (KeyError, TypeError) as error:
            raise ObjectStorageConfigurationError(
                f"Django storage alias {alias!r} is not configured"
            ) from error
        if not isinstance(config, Mapping):
            raise ObjectStorageConfigurationError(f"storage alias {alias!r} is invalid")
        options = config.get("OPTIONS")
        if not isinstance(options, Mapping):
            raise ObjectStorageConfigurationError(f"storage alias {alias!r} has invalid OPTIONS")

        bucket = options.get("bucket_name")
        if not isinstance(bucket, str) or not bucket.strip():
            raise ObjectStorageConfigurationError(f"storage alias {alias!r} has no bucket_name")

        client_options = {
            boto_name: options.get(setting_name)
            for setting_name, boto_name in (
                ("endpoint_url", "endpoint_url"),
                ("access_key", "aws_access_key_id"),
                ("secret_key", "aws_secret_access_key"),
                ("region_name", "region_name"),
            )
            if options.get(setting_name) is not None
        }
        return cls(cast(S3Client, boto3.client("s3", **client_options)), bucket)

    def head(self, key: str) -> ObjectHead | None:
        """Return metadata, or ``None`` when the key does not exist."""

        try:
            response = self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if _is_not_found(error):
                return None
            raise
        return ObjectHead(
            bucket=self.bucket,
            key=key,
            size=int(response.get("ContentLength", 0)),
            etag=cast(str | None, response.get("ETag")),
            content_type=cast(str | None, response.get("ContentType")),
        )

    def put(
        self,
        content: bytes,
        *,
        extension: str | None = None,
        content_type: str = "application/octet-stream",
    ) -> Blob:
        """Store bytes once; repeated content resolves to the existing object."""

        key, digest = content_key(content, extension)
        existing = self.head(key)
        if existing is not None:
            logger.debug("object storage hit bucket=%s key=%s", self.bucket, key)
            return Blob(self.bucket, key, digest, existing.size, created=False)

        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
            Metadata={"sha256": digest},
        )
        logger.info("object stored bucket=%s key=%s size=%d", self.bucket, key, len(content))
        return Blob(self.bucket, key, digest, len(content), created=True)

    def get(self, key: str) -> bytes:
        """Read a complete object body."""

        response = self._client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"]
        return cast(bytes, body.read())

    def presigned_get_url(
        self,
        key: str,
        *,
        is_allowed: Callable[[str], bool],
        expires_in: int | None = None,
    ) -> str:
        """Sign a short-lived GET URL only after application authorization."""

        if not is_allowed(key):
            raise ObjectStoragePermissionError(f"not allowed to read object {key!r}")
        ttl = (
            expires_in
            if expires_in is not None
            else int(getattr(settings, "OBJECT_STORAGE_PRESIGNED_TTL_SECONDS", 300))
        )
        if not 1 <= ttl <= 3600:
            raise ValueError("presigned URL expiry must be between 1 and 3600 seconds")
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=ttl
        )


def upload_then_commit[T](
    storage: ObjectStorage,
    content: bytes,
    commit_metadata: Callable[[Blob], T],
    *,
    extension: str | None = None,
    content_type: str = "application/octet-stream",
) -> tuple[Blob, T]:
    """Upload a blob, then commit metadata inside one database transaction.

    An upload failure occurs before the transaction and therefore cannot commit
    metadata.  A metadata failure can leave an orphan blob, which is safe for a
    retry and is intentionally delegated to the future GC task (BLOCKER-014).
    """

    blob = storage.put(content, extension=extension, content_type=content_type)
    with transaction.atomic():
        result = commit_metadata(blob)
    return blob, result
