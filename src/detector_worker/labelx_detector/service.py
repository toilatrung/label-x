"""Authenticated, single-request GPU service; checkpoint verified before warm load.

The public CLI prediction schema stays unchanged. This internal frame contract preserves
the original ROI softmax distribution (ten foreground classes + background) through NMS.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from PIL import Image

from .artifact import ArtifactManifest, verify_checkpoint
from .inference import MMDetectionBackend

MAX_BYTES = 50 * 1024 * 1024
MAX_REQUEST = 70 * 1024 * 1024


class WarmDetector:
    def __init__(self, checkpoint: Path, manifest_path: Path, config: Path, device: str):
        self.manifest = ArtifactManifest.load(manifest_path)
        verify_checkpoint(checkpoint, self.manifest)
        self.backend = MMDetectionBackend(config, checkpoint, device, self.manifest.classes)

    def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        frame = payload.get("frame")
        if not isinstance(frame, dict) or payload.get("model_sha256") != self.manifest.sha256:
            raise ValueError("invalid frame/model binding")
        encoded = payload.get("image_base64")
        if not isinstance(encoded, str):
            raise ValueError("image required")
        raw = base64.b64decode(encoded, validate=True)
        if not 0 < len(raw) <= MAX_BYTES or hashlib.sha256(raw).hexdigest() != frame.get(
            "media_sha256"
        ):
            raise ValueError("image integrity mismatch")
        with Image.open(io.BytesIO(raw)) as image:
            if (
                image.size != (frame.get("width"), frame.get("height"))
                or image.width * image.height > 50_000_000
            ):
                raise ValueError("image dimensions mismatch")
            image.verify()
        with tempfile.TemporaryDirectory(prefix="labelx-detector-") as directory:
            path = Path(directory) / "frame.png"
            with Image.open(io.BytesIO(raw)) as image:
                image.convert("RGB").save(path, "PNG")
            detections = self._scored_inference(path)
        return {
            "schema_version": "labelx.detector.frame.v1",
            "frame": frame,
            "model_sha256": self.manifest.sha256,
            "class_mapping_version": self.manifest.mapping_version,
            "classes": list(self.manifest.classes),
            "detections": detections,
        }

    def _scored_inference(self, path: Path) -> list[dict[str, Any]]:
        from mmdet.core import multiclass_nms

        head = self.backend._model.roi_head.bbox_head
        original = head.get_bboxes
        records: list[dict[str, Any]] = []
        classes = self.manifest.classes

        def capture(
            rois: Any,
            cls_score: Any,
            bbox_pred: Any,
            img_shape: Any,
            scale_factor: Any,
            rescale: bool = False,
            cfg: Any = None,
        ) -> Any:
            boxes, scores = original(
                rois, cls_score, bbox_pred, img_shape, scale_factor, rescale=rescale, cfg=None
            )
            if cfg is None:
                raise ValueError("NMS configuration required")
            kept, labels, indices = multiclass_nms(
                boxes, scores, cfg.score_thr, cfg.nms, cfg.max_per_img, return_inds=True
            )
            for detection, label, index in zip(kept, labels, indices):
                class_id = int(label)
                probabilities = scores[int(index) // len(classes)].detach().cpu().tolist()
                coords = detection[:4].detach().cpu().tolist()
                records.append(
                    {
                        "bbox_xyxy": coords,
                        "class_id": class_id,
                        "class_name": classes[class_id],
                        "confidence": float(detection[4]),
                        "class_scores": probabilities,
                    }
                )
            return kept, labels

        head.get_bboxes = capture
        try:
            self.backend.infer([path])
            self.backend.synchronize()
        finally:
            head.get_bboxes = original
        return sorted(
            records, key=lambda d: (tuple(d["bbox_xyxy"]), d["class_id"], -d["confidence"])
        )


def main() -> None:
    token = os.environ.get("DETECTOR_SERVICE_TOKEN", "")
    if len(token) < 32:
        raise ValueError("DETECTOR_SERVICE_TOKEN must contain at least 32 characters")
    if not token.isascii():
        raise ValueError("DETECTOR_SERVICE_TOKEN must contain ASCII characters")
    worker = WarmDetector(
        Path(
            os.environ.get("DETECTOR_CHECKPOINT", "/models/faster_rcnn_r50_fpn_3x_det_bdd100k.pth")
        ),
        Path("model-manifest.json"),
        Path("configs/faster_rcnn_r50_fpn_3x_det_bdd100k.py"),
        os.environ.get("DETECTOR_DEVICE", "cuda:0"),
    )

    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(120)

        def log_message(self, format: str, *args: Any) -> None:
            return  # no request body, headers, paths or credentials in logs

        def reply(self, status: int, value: dict[str, Any]) -> None:
            raw = json.dumps(value, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self) -> bool:
            return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token)

        def do_GET(self) -> None:
            if not self.authorized():
                self.reply(401, {"error": "unauthorized"})
            elif self.path == "/health":
                self.reply(200, {"status": "ready", "model_sha256": worker.manifest.sha256})
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
                    raise ValueError("invalid request")
                result = worker.predict(payload)
            except (ValueError, OSError, KeyError):
                self.reply(422, {"error": "invalid_frame"})
                return
            except Exception:
                self.reply(503, {"error": "inference_unavailable"})
                return
            self.reply(200, result)

    server = HTTPServer(("0.0.0.0", 8501), Handler)  # noqa: S104 (private container; bind host port to loopback)
    server.timeout = 120
    print("Detector ready; artifact verified; single GPU request at a time", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
