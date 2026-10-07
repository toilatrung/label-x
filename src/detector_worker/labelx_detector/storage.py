"""Publish and retrieve frozen checkpoints from an S3-compatible artifact store."""

from __future__ import annotations

import hashlib
import hmac
import http.client
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Mapping
from urllib.parse import quote, urlsplit

from .artifact import (
    ArtifactManifest,
    ChecksumMismatchError,
    unlink_if_exists,
    verify_checkpoint,
)


class ArtifactStoreError(RuntimeError):
    """Raised when the artifact store refuses or corrupts an operation."""


@dataclass(frozen=True)
class S3Credentials:
    access_key: str
    secret_key: str
    session_token: str | None = None

    @classmethod
    def from_environment(cls) -> S3Credentials:
        access_key = os.environ.get("AWS_ACCESS_KEY_ID")
        secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        if not access_key or not secret_key:
            raise ArtifactStoreError("AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required")
        return cls(access_key, secret_key, os.environ.get("AWS_SESSION_TOKEN"))


def _signing_key(secret_key: str, date: str, region: str) -> bytes:
    date_key = hmac.new(("AWS4" + secret_key).encode(), date.encode(), hashlib.sha256).digest()
    region_key = hmac.new(date_key, region.encode(), hashlib.sha256).digest()
    service_key = hmac.new(region_key, b"s3", hashlib.sha256).digest()
    return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()


def _signed_headers(
    method: str,
    endpoint: str,
    bucket: str,
    key: str,
    payload_sha256: str,
    region: str,
    credentials: S3Credentials,
    extra_headers: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> tuple[str, dict[str, str]]:
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ArtifactStoreError(f"Invalid S3 endpoint: {endpoint}")
    timestamp = now or datetime.now(timezone.utc)
    amz_date = timestamp.strftime("%Y%m%dT%H%M%SZ")
    date = timestamp.strftime("%Y%m%d")
    endpoint_path = parsed.path.rstrip("/")
    object_path = f"{endpoint_path}/{quote(bucket, safe='')}/{quote(key, safe='/~-_.')}"
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"

    headers = {
        "host": host,
        "x-amz-content-sha256": payload_sha256,
        "x-amz-date": amz_date,
    }
    if credentials.session_token:
        headers["x-amz-security-token"] = credentials.session_token
    if extra_headers:
        headers.update({name.lower(): value.strip() for name, value in extra_headers.items()})
    signed_names = ";".join(sorted(headers))
    canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in sorted(headers))
    canonical_request = "\n".join(
        [method, object_path, "", canonical_headers, signed_names, payload_sha256]
    )
    scope = f"{date}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )
    signature = hmac.new(
        _signing_key(credentials.secret_key, date, region),
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()
    headers["authorization"] = (
        "AWS4-HMAC-SHA256 "
        f"Credential={credentials.access_key}/{scope},"
        f"SignedHeaders={signed_names},Signature={signature}"
    )
    return object_path, headers


def _connection(endpoint: str) -> http.client.HTTPConnection:
    parsed = urlsplit(endpoint)
    connection_type = (
        http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    )
    return connection_type(parsed.hostname, parsed.port, timeout=300)


def _request(
    method: str,
    endpoint: str,
    bucket: str,
    key: str,
    payload_sha256: str,
    region: str,
    credentials: S3Credentials,
    body: BinaryIO | None = None,
    extra_headers: Mapping[str, str] | None = None,
) -> http.client.HTTPResponse:
    path, headers = _signed_headers(
        method,
        endpoint,
        bucket,
        key,
        payload_sha256,
        region,
        credentials,
        extra_headers,
    )
    connection = _connection(endpoint)
    connection.request(method, path, body=body, headers=headers)
    return connection.getresponse()


def publish_checkpoint(
    checkpoint: Path,
    manifest: ArtifactManifest,
    endpoint: str,
    bucket: str,
    key: str,
    region: str,
    credentials: S3Credentials,
) -> str:
    """Upload a verified checkpoint and confirm immutable metadata with HEAD."""

    digest = verify_checkpoint(checkpoint, manifest)
    size = checkpoint.stat().st_size
    headers = {
        "content-length": str(size),
        "content-type": "application/octet-stream",
        "x-amz-meta-sha256": digest,
    }
    with checkpoint.open("rb") as stream:
        response = _request(
            "PUT",
            endpoint,
            bucket,
            key,
            digest,
            region,
            credentials,
            stream,
            headers,
        )
        body = response.read()
    if response.status not in {200, 201}:
        raise ArtifactStoreError(
            f"Artifact upload failed with HTTP {response.status}: {body[:500]!r}"
        )
    verify_remote_checkpoint(endpoint, bucket, key, manifest, region, credentials)
    return f"s3://{bucket}/{key}"


def verify_remote_checkpoint(
    endpoint: str,
    bucket: str,
    key: str,
    manifest: ArtifactManifest,
    region: str,
    credentials: S3Credentials,
) -> None:
    """Require the remote size and publisher-provided checksum to match the manifest."""

    empty_digest = hashlib.sha256(b"").hexdigest()
    response = _request("HEAD", endpoint, bucket, key, empty_digest, region, credentials)
    response.read()
    if response.status != 200:
        raise ArtifactStoreError(f"Artifact HEAD failed with HTTP {response.status}")
    expected_size = int(manifest.raw["model"]["size_bytes"])
    actual_size = int(response.getheader("Content-Length", "-1"))
    actual_digest = response.getheader("x-amz-meta-sha256", "")
    if actual_size != expected_size or actual_digest != manifest.sha256:
        raise ChecksumMismatchError(
            "Remote checkpoint metadata mismatch: "
            f"expected size={expected_size}, sha256={manifest.sha256}; "
            f"got size={actual_size}, sha256={actual_digest or '<missing>'}"
        )


def fetch_checkpoint(
    destination: Path,
    manifest: ArtifactManifest,
    endpoint: str,
    bucket: str,
    key: str,
    region: str,
    credentials: S3Credentials,
) -> str:
    """Download to a temporary file, verify SHA-256, then atomically publish locally."""

    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    empty_digest = hashlib.sha256(b"").hexdigest()
    response = _request("GET", endpoint, bucket, key, empty_digest, region, credentials)
    if response.status != 200:
        body = response.read()
        raise ArtifactStoreError(
            f"Artifact download failed with HTTP {response.status}: {body[:500]!r}"
        )

    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".part", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        digest = verify_checkpoint(temporary, manifest)
        temporary.replace(destination)
        return digest
    except BaseException:
        unlink_if_exists(temporary)
        raise
