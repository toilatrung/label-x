"""Frozen model artifact metadata and integrity verification."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ManifestError(ValueError):
    """Raised when model metadata is incomplete or inconsistent."""


class ChecksumMismatchError(RuntimeError):
    """Raised before model loading when a checkpoint is not the frozen artifact."""


def unlink_if_exists(path: Path) -> None:
    """Remove a file without relying on Path.unlink(missing_ok), added in Python 3.8."""

    try:
        path.unlink()
    except FileNotFoundError:
        pass


@dataclass(frozen=True)
class ArtifactManifest:
    """Validated subset of the model manifest required at inference time."""

    path: Path
    raw: dict[str, Any]
    name: str
    version: str
    checkpoint_filename: str
    sha256: str
    mapping_version: str
    classes: tuple[str, ...]

    @classmethod
    def load(cls, path: Path) -> ArtifactManifest:
        manifest_path = path.resolve()
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            model = raw["model"]
            mapping = raw["class_mapping"]
            classes = tuple(mapping["classes"])
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ManifestError(f"Invalid artifact manifest {manifest_path}: {exc}") from exc

        sha256 = str(model.get("sha256") or "").lower()
        if not SHA256_PATTERN.fullmatch(sha256):
            raise ManifestError(
                "The checkpoint is not frozen: model.sha256 must contain 64 lowercase "
                "hexadecimal characters. Run `labelx-detector freeze` with the recovered "
                "checkpoint before inference."
            )
        if len(classes) != 10 or len(set(classes)) != 10:
            raise ManifestError("class_mapping.classes must contain 10 unique BDD100K classes")
        if not all(isinstance(item, str) and item.strip() for item in classes):
            raise ManifestError("Every BDD100K class name must be a non-empty string")

        return cls(
            path=manifest_path,
            raw=raw,
            name=str(model["name"]),
            version=str(model["version"]),
            checkpoint_filename=str(model["checkpoint_filename"]),
            sha256=sha256,
            mapping_version=str(mapping["version"]),
            classes=classes,
        )


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 of a file without loading it all into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        chunk = stream.read(chunk_size)
        while chunk:
            digest.update(chunk)
            chunk = stream.read(chunk_size)
    return digest.hexdigest()


def verify_checkpoint(checkpoint: Path, manifest: ArtifactManifest) -> str:
    """Verify the frozen checkpoint before any deserialization occurs."""

    checkpoint_path = checkpoint.resolve()
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"Checkpoint does not exist: {checkpoint_path}")
    actual = sha256_file(checkpoint_path)
    if actual != manifest.sha256:
        raise ChecksumMismatchError(
            f"Checkpoint SHA-256 mismatch for {checkpoint_path}: "
            f"expected {manifest.sha256}, got {actual}. Model loading was refused."
        )
    return actual


def freeze_checkpoint(checkpoint: Path, manifest_path: Path) -> str:
    """Record a local checkpoint's SHA-256 and size using an atomic manifest update."""

    checkpoint_path = checkpoint.resolve()
    target = manifest_path.resolve()
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"Checkpoint does not exist: {checkpoint_path}")
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        model = raw["model"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ManifestError(f"Invalid artifact manifest {target}: {exc}") from exc

    digest = sha256_file(checkpoint_path)
    model["sha256"] = digest
    model["size_bytes"] = checkpoint_path.stat().st_size
    model["checkpoint_filename"] = checkpoint_path.name
    model["frozen_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    model["artifact_state"] = "frozen"

    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(raw, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
    except BaseException:
        unlink_if_exists(temporary)
        raise
    return digest
