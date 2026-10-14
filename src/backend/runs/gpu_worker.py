"""Tailscale HTTPS transport, bounded readiness probes and run-pinned worker revisions."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from django.conf import settings
from django.utils import timezone

from engines.detector import BDD100K_DETECTOR_CLASSES, MANIFEST_SCHEMA_VERSION
from engines.worker_adapter.client import request_json
from runs.models import GpuWorkerConfig, GpuWorkerSelection, ModelArtifact, RunGpuWorker

SHA256 = re.compile(r"[a-f0-9]{64}")


class WorkerUnavailable(RuntimeError):
    pass


def validate_url(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    # Exact Operations-owned allowlist, NOT an editable suffix/wildcard from the UI.
    if (
        parts.scheme != "https"
        or host not in settings.GPU_WORKER_ALLOWED_HOSTS
        or not host.endswith(".ts.net")
        or parts.port not in (None, 443)
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path not in ("", "/")
    ):
        raise ValueError("Chỉ chấp nhận HTTPS Tailscale host đã được quản trị server cho phép.")
    return "https://" + host


def credential(ref: str) -> str:
    if not isinstance(settings.GPU_WORKER_CREDENTIALS, dict):
        raise WorkerUnavailable("GPU_WORKER_CREDENTIALS phải là JSON object trên server.")
    value = settings.GPU_WORKER_CREDENTIALS.get(ref)
    if (
        not isinstance(value, str)
        or len(value) < 32
        or not value.isascii()
        or any(c.isspace() for c in value)
    ):
        raise WorkerUnavailable("Credential của GPU Worker chưa sẵn sàng trên server.")
    return value


def request_worker(
    config: GpuWorkerConfig, path: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    url = validate_url(config.url)
    token = credential(config.credential_ref)
    timeout = 5 if path == "/health" else config.timeout_seconds
    try:
        result = request_json(
            "GET" if body is None else "POST", url + path, token=token, timeout=timeout, body=body
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise WorkerUnavailable("GPU Worker từ chối xác thực.") from None
        raise WorkerUnavailable(
            "Không kết nối được GPU Worker hoặc response không hợp lệ."
        ) from None
    except (httpx.HTTPError, ValueError):
        raise WorkerUnavailable(
            "Không kết nối được GPU Worker hoặc response không hợp lệ."
        ) from None
    if not isinstance(result, dict):
        raise WorkerUnavailable("GPU Worker trả response không hợp lệ.")
    return result


def verify_remote(payload: dict[str, Any], artifact: ModelArtifact | None = None) -> dict[str, Any]:
    """Worker verifies its file; backend checks manifest binding without a host checkpoint."""
    try:
        manifest = json.loads(Path(settings.DETECTOR_MANIFEST_PATH).read_text(encoding="utf-8"))
        model = payload["model"]
        mapping = manifest["class_mapping"]
        expected = manifest["model"]
        if (
            manifest["schema_version"] != MANIFEST_SCHEMA_VERSION
            or payload.get("artifact_verified") is not True
            or not isinstance(model, dict)
            or not SHA256.fullmatch(str(expected["sha256"]))
            or tuple(mapping["classes"]) != BDD100K_DETECTOR_CLASSES
            or tuple(model.get("classes", [])) != BDD100K_DETECTOR_CLASSES
            or model.get("sha256") != expected["sha256"]
            or model.get("version") != expected["version"]
            or model.get("class_mapping_version") != mapping["version"]
        ):
            raise ValueError("model mismatch")
        if artifact is not None and (
            artifact.checksum != model["sha256"]
            or artifact.version != model["version"]
            or artifact.class_mapping_version != mapping["version"]
            or not isinstance(artifact.class_mapping, dict)
            or tuple(artifact.class_mapping.get("classes", [])) != BDD100K_DETECTOR_CLASSES
        ):
            raise ValueError("artifact mismatch")
    except (OSError, ValueError, KeyError, TypeError):
        raise WorkerUnavailable("Model/checksum/class map của GPU Worker không phù hợp.") from None
    return {
        "sha256": model["sha256"],
        "version": model["version"],
        "class_mapping_version": mapping["version"],
        "verified": True,
    }


def probe(config: GpuWorkerConfig, artifact: ModelArtifact | None = None) -> dict[str, Any]:
    started = time.monotonic()
    result: dict[str, Any] = {
        "revision": config.pk,
        "state": "disabled",
        "message": "Đã tắt GPU Worker.",
        "checked_at": timezone.now().isoformat(),
        "latency_ms": None,
        "device": None,
        "model": None,
    }
    if not config.enabled:
        return result
    try:
        payload = request_worker(config, "/health")
        if payload.get("status") != "ready":
            raise WorkerUnavailable("GPU Worker online nhưng model chưa sẵn sàng.")
        verified = verify_remote(payload, artifact)
        device = payload.get("device")
        if not isinstance(device, str) or not device.startswith("cuda"):
            raise WorkerUnavailable("GPU Worker chưa sử dụng thiết bị CUDA.")
        result.update(
            state="ready", message="GPU Worker sẵn sàng.", model=verified, device=device[:64]
        )
    except (WorkerUnavailable, ValueError):
        # Do not persist or expose arbitrary upstream diagnostics, URLs, headers or credentials.
        result.update(
            state="unavailable",
            message="GPU Worker chưa sẵn sàng; kiểm tra mạng, credential và model.",
        )
    result["latency_ms"] = max(0, round((time.monotonic() - started) * 1000))
    return result


def selected() -> GpuWorkerConfig | None:
    selection = GpuWorkerSelection.objects.select_related("config").filter(pk=1).first()
    return selection.config if selection else None


def prepare(artifact: ModelArtifact) -> GpuWorkerConfig | None:
    config = selected()
    if config is not None and probe(config, artifact)["state"] != "ready":
        raise WorkerUnavailable(
            "GPU Worker chưa sẵn sàng. Không tạo run detector; hãy kiểm tra kết nối."
        )
    return config


def config_for_run(run_id: int) -> GpuWorkerConfig | None:
    # No binding means legacy ENV mode; never attach an old run to the current selection.
    binding = RunGpuWorker.objects.select_related("config").filter(run_id=run_id).first()
    return binding.config if binding else None
