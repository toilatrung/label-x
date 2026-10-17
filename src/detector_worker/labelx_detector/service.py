"""Private authenticated HTTP adapter; one warm model and one GPU request at a time."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from PIL import Image

from .artifact import ArtifactManifest, verify_checkpoint
from .inference import SUPPORTED_IMAGE_SUFFIXES, MMDetectionBackend, run_batch

MAX_REQUEST = 70 * 1024 * 1024


class WarmDetector:
    def __init__(self, checkpoint: Path, manifest_path: Path, config: Path, device: str):
        self.checkpoint = checkpoint
        self.manifest = ArtifactManifest.load(manifest_path)
        self.config = config
        self.device = device
        verify_checkpoint(checkpoint, self.manifest)
        self.backend = MMDetectionBackend(config, checkpoint, device, self.manifest.classes)

    def model(self) -> dict[str, Any]:
        return {
            "sha256": self.manifest.sha256,
            "version": self.manifest.version,
            "class_mapping_version": self.manifest.mapping_version,
            "classes": list(self.manifest.classes),
        }

    def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("model_sha256") != self.manifest.sha256:
            raise ValueError("model binding mismatch")
        images = payload.get("images")
        batch_size = payload.get("batch_size", 1)
        threshold = payload.get("score_threshold", 0.05)
        if (
            not isinstance(images, list)
            or not 1 <= len(images) <= 256
            or isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or not 1 <= batch_size <= 4
            or isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not 0 <= threshold <= 1
        ):
            raise ValueError("invalid batch")
        with tempfile.TemporaryDirectory(prefix="labelx-detector-") as directory:
            root = Path(directory)
            inputs = root / "input"
            inputs.mkdir()
            seen = set()
            for image in images:
                if not isinstance(image, dict):
                    raise ValueError("invalid image")
                name = image.get("path")
                if (
                    not isinstance(name, str)
                    or not name
                    or "/" in name
                    or "\\" in name
                    or ":" in name
                    or name in seen
                    or Path(name).suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES
                ):
                    raise ValueError("invalid image path")
                seen.add(name)
                encoded = image.get("image_base64")
                if not isinstance(encoded, str):
                    raise ValueError("image required")
                raw = base64.b64decode(encoded, validate=True)
                if not raw or hashlib.sha256(raw).hexdigest() != image.get("sha256"):
                    raise ValueError("image integrity mismatch")
                with Image.open(io.BytesIO(raw)) as opened:
                    if opened.width * opened.height > 50_000_000:
                        raise ValueError("image too large")
                    opened.verify()
                (inputs / name).write_bytes(raw)
            result = run_batch(
                input_directory=inputs,
                output=root / "predictions.json",
                checkpoint=self.checkpoint,
                manifest=self.manifest,
                config=self.config,
                device=self.device,
                batch_size=batch_size,
                score_threshold=float(threshold),
                backend=self.backend,
            )
            result["artifact_verified"] = True
            return result


def validate_token(token: str) -> None:
    if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("DETECTOR_SERVICE_TOKEN must contain >=32 non-whitespace ASCII characters")


def make_handler(worker: WarmDetector, token: str) -> type[BaseHTTPRequestHandler]:
    validate_token(token)
    inference_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(120)

        def log_message(self, format: str, *args: Any) -> None:
            return  # Never log request bodies or credentials.

        def reply(self, status: int, payload: dict[str, Any]) -> None:
            raw = json.dumps(payload, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self) -> bool:
            actual = self.headers.get("Authorization", "").encode("utf-8")
            return hmac.compare_digest(actual, ("Bearer " + token).encode("ascii"))

        def do_GET(self) -> None:
            if not self.authorized():
                self.reply(401, {"error": "unauthorized"})
            elif self.path == "/health":
                self.reply(
                    200,
                    {
                        "status": "ready",
                        "model": worker.model(),
                        "artifact_verified": True,
                        "device": worker.device,
                    },
                )
            else:
                self.reply(404, {"error": "not_found"})

        def do_POST(self) -> None:
            if not self.authorized():
                self.reply(401, {"error": "unauthorized"})
                return
            if self.path != "/infer":
                self.reply(404, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_REQUEST:
                    self.reply(413, {"error": "request_size"})
                    return
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("object required")
                if not inference_lock.acquire(blocking=False):
                    self.reply(503, {"error": "worker_busy"})
                    return
                try:
                    result = worker.predict(payload)
                finally:
                    inference_lock.release()
            except (ValueError, OSError, KeyError):
                self.reply(422, {"error": "invalid_batch"})
                return
            except Exception as exc:
                # Do not log payloads, image URLs or arbitrary exception text.
                print(f"Detector inference unavailable: {type(exc).__name__}", flush=True)
                self.reply(503, {"error": "inference_unavailable"})
                return
            self.reply(200, result)

    return Handler


def main() -> None:
    token = os.environ.get("DETECTOR_SERVICE_TOKEN", "")
    # Validate before loading a 165 MB model.
    validate_token(token)
    worker = WarmDetector(
        Path("/models/faster_rcnn_r50_fpn_3x_det_bdd100k.pth"),
        Path("model-manifest.json"),
        Path("configs/faster_rcnn_r50_fpn_3x_det_bdd100k.py"),
        os.environ.get("DETECTOR_DEVICE", "cuda:0"),
    )
    # Container port is published only on host loopback by Compose; no public/plaintext remote API.
    server = ThreadingHTTPServer(("0.0.0.0", 8501), make_handler(worker, token))  # noqa: S104
    print("Detector ready; verified artifact; serialized GPU requests", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
