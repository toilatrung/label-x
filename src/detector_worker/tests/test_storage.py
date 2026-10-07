import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from labelx_detector.artifact import ArtifactManifest, ChecksumMismatchError
from labelx_detector.storage import S3Credentials, fetch_checkpoint, publish_checkpoint

CLASSES = [
    "pedestrian",
    "rider",
    "car",
    "truck",
    "bus",
    "train",
    "motorcycle",
    "bicycle",
    "traffic light",
    "traffic sign",
]


class ArtifactHandler(BaseHTTPRequestHandler):
    content = b""
    digest = ""

    def do_PUT(self):
        type(self).content = self.rfile.read(int(self.headers["Content-Length"]))
        type(self).digest = self.headers.get("x-amz-meta-sha256", "")
        self.send_response(200)
        self.end_headers()

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(type(self).content)))
        self.send_header("x-amz-meta-sha256", type(self).digest)
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(type(self).content)))
        self.end_headers()
        self.wfile.write(type(self).content)

    def log_message(self, format, *args):
        pass


@pytest.fixture
def artifact_server():
    ArtifactHandler.content = b""
    ArtifactHandler.digest = ""
    server = ThreadingHTTPServer(("127.0.0.1", 0), ArtifactHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


def manifest_for(tmp_path, content):
    digest = hashlib.sha256(content).hexdigest()
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "model": {
                    "name": "test-model",
                    "version": "v1",
                    "checkpoint_filename": "model.pth",
                    "sha256": digest,
                    "size_bytes": len(content),
                },
                "class_mapping": {"version": "bdd-v1", "classes": CLASSES},
            }
        ),
        encoding="utf-8",
    )
    return ArtifactManifest.load(path)


def test_publish_then_fetch_is_checksum_verified(tmp_path, artifact_server):
    content = b"frozen detector artifact"
    checkpoint = tmp_path / "model.pth"
    checkpoint.write_bytes(content)
    manifest = manifest_for(tmp_path, content)
    credentials = S3Credentials("test", "test-secret")

    uri = publish_checkpoint(
        checkpoint,
        manifest,
        artifact_server,
        "models",
        "detector/model.pth",
        "us-east-1",
        credentials,
    )
    destination = tmp_path / "download" / "model.pth"
    digest = fetch_checkpoint(
        destination,
        manifest,
        artifact_server,
        "models",
        "detector/model.pth",
        "us-east-1",
        credentials,
    )

    assert uri == "s3://models/detector/model.pth"
    assert digest == manifest.sha256
    assert destination.read_bytes() == content


def test_fetch_does_not_publish_corrupt_download(tmp_path, artifact_server):
    manifest = manifest_for(tmp_path, b"expected")
    ArtifactHandler.content = b"corrupt"
    destination = tmp_path / "model.pth"

    with pytest.raises(ChecksumMismatchError):
        fetch_checkpoint(
            destination,
            manifest,
            artifact_server,
            "models",
            "detector/model.pth",
            "us-east-1",
            S3Credentials("test", "test-secret"),
        )

    assert not destination.exists()
