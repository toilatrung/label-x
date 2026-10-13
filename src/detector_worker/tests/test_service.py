import base64
import hashlib
import io
from types import SimpleNamespace

import pytest
from PIL import Image

from labelx_detector.service import WarmDetector


def request():
    stream = io.BytesIO()
    Image.new("RGB", (20, 10)).save(stream, "PNG")
    raw = stream.getvalue()
    return {
        "model_sha256": "a" * 64,
        "image_base64": base64.b64encode(raw).decode(),
        "frame": {"width": 20, "height": 10, "media_sha256": hashlib.sha256(raw).hexdigest()},
    }


def worker():
    instance = object.__new__(WarmDetector)
    instance.manifest = SimpleNamespace(sha256="a" * 64, mapping_version="v1", classes=["car"])
    instance._scored_inference = lambda path: [{"class_scores": [0.9, 0.1]}]
    return instance


def test_warm_service_frame_provenance_and_full_scores():
    payload = request()
    result = worker().predict(payload)
    assert result["frame"] == payload["frame"]
    assert result["schema_version"] == "labelx.detector.frame.v1"
    assert result["detections"][0]["class_scores"] == [0.9, 0.1]


@pytest.mark.parametrize("bad", ["model", "hash", "dimensions", "base64"])
def test_warm_service_rejects_invalid_inputs(bad):
    payload = request()
    if bad == "model":
        payload["model_sha256"] = "b" * 64
    elif bad == "hash":
        payload["frame"]["media_sha256"] = "b" * 64
    elif bad == "dimensions":
        payload["frame"]["width"] = 21
    else:
        payload["image_base64"] = "not base64"
    with pytest.raises(ValueError):
        worker().predict(payload)
