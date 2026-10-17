import base64
import hashlib
import io
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import Mock

import pytest
from PIL import Image

from labelx_detector.service import MAX_REQUEST, WarmDetector, make_handler, validate_token


@pytest.mark.parametrize("token", ["", "short", "é" * 40, "x" * 32 + "\n"])
def test_bad_token_rejected(token):
    with pytest.raises(ValueError):
        validate_token(token)


@pytest.fixture
def server():
    worker = Mock()
    worker.device = "cuda:0"
    worker.model.return_value = {"sha256": "a" * 64}
    worker.predict.return_value = {"images": []}
    token = "fixture-only-" + "x" * 32
    http = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(worker, token))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:" + str(http.server_port), worker, token
    http.shutdown()
    http.server_close()
    thread.join(timeout=5)


def request(server, path, body=None, authenticated=True, size=None):
    url, _, token = server
    headers = {"Authorization": "Bearer " + token} if authenticated else {}
    if size is not None:
        headers["Content-Length"] = str(size)
    req = urllib.request.Request(url + path, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def test_health_auth_and_routes(server):
    assert request(server, "/health", authenticated=False)[0] == 401
    assert request(server, "/health")[1]["status"] == "ready"
    assert request(server, "/missing")[0] == 404
    assert request(server, "/infer", b"{}", authenticated=False)[0] == 401
    server[1].predict.assert_not_called()


def test_batch_endpoint_and_redacted_errors(server):
    assert request(server, "/infer", b"{}")[0] == 200
    assert request(server, "/infer", b"[]")[0] == 422
    assert request(server, "/infer", b"{bad")[0] == 422
    assert request(server, "/infer", b"{}", size=MAX_REQUEST + 1)[0] == 413
    server[1].predict.side_effect = RuntimeError("do not leak paths/credentials")
    assert request(server, "/infer", b"{}")[1] == {"error": "inference_unavailable"}


def test_health_responds_while_gpu_busy_and_second_inference_is_rejected(server):
    entered, release = threading.Event(), threading.Event()

    def busy(_):
        entered.set()
        release.wait(timeout=5)
        return {"images": []}

    server[1].predict.side_effect = busy
    first = threading.Thread(target=lambda: request(server, "/infer", b"{}"), daemon=True)
    first.start()
    try:
        assert entered.wait(timeout=2)
        assert request(server, "/health")[0] == 200
        assert request(server, "/infer", b"{}") == (503, {"error": "worker_busy"})
        assert server[1].predict.call_count == 1
    finally:
        release.set()
        first.join(timeout=5)


def payload():
    output = io.BytesIO()
    Image.new("RGB", (10, 10)).save(output, "PNG")
    raw = output.getvalue()
    return {
        "model_sha256": "a" * 64,
        "images": [
            {
                "path": "frame.png",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "image_base64": base64.b64encode(raw).decode(),
            }
        ],
    }


@pytest.mark.parametrize(
    "mutation",
    [
        {"path": "../frame.png"},
        {"path": "C:\\frame.png"},
        {"path": "a/b.png"},
        {"image_base64": "invalid"},
        {"sha256": "b" * 64},
        {"path": "a.txt"},
    ],
)
def test_input_integrity_and_path_traversal(mutation):
    worker = WarmDetector.__new__(WarmDetector)
    worker.manifest = Mock(sha256="a" * 64)
    data = payload()
    data["images"][0].update(mutation)
    with pytest.raises(ValueError):
        worker.predict(data)


def test_wrong_model_and_duplicate_names_rejected():
    worker = WarmDetector.__new__(WarmDetector)
    worker.manifest = Mock(sha256="a" * 64)
    data = payload()
    with pytest.raises(ValueError):
        worker.predict({**data, "model_sha256": "b" * 64})
    data["images"] *= 2
    with pytest.raises(ValueError):
        worker.predict(data)
