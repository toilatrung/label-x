"""BLOCKER-033 host-to-container transport, explicit registration and real GPU opt-in."""

import io
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, Mock

import httpx
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from engines.detector import _run_worker, worker_request
from tests.engines.test_detector import _input, _settings
from tests.engines.test_detector import artifact_files as artifact_files


@pytest.fixture
def http_worker(settings, monkeypatch):
    settings.DETECTOR_WORKER_URL = "http://127.0.0.1:8501"
    settings.DETECTOR_SERVICE_TOKEN = "test-only-token-" + "x" * 32
    factory = MagicMock()
    monkeypatch.setattr("engines.detector.httpx.Client", factory)
    return factory, factory.return_value.__enter__.return_value


def test_transport_sends_auth_but_no_proxy_or_redirects(http_worker):
    factory, client = http_worker
    client.request.return_value.json.return_value = {"status": "ready"}
    assert worker_request("GET", "/health") == {"status": "ready"}
    assert factory.call_args.kwargs["trust_env"] is False
    assert factory.call_args.kwargs["follow_redirects"] is False
    assert client.request.call_args.args == ("GET", "http://127.0.0.1:8501/health")
    assert client.request.call_args.kwargs["headers"]["Authorization"].startswith("Bearer ")


@pytest.mark.parametrize(
    "url",
    [
        "http://gpu.example:8501",
        "file:///tmp/model",
        "http://user:password@localhost:8501",
        "http://localhost:8501?token=bad",
        "http://localhost:8501/other",
        "http://localhost/#bad",
    ],
)
def test_unsafe_worker_urls_rejected_without_request(settings, http_worker, url):
    settings.DETECTOR_WORKER_URL = url
    with pytest.raises(ValueError):
        worker_request("GET", "/health")
    http_worker[0].assert_not_called()


@pytest.mark.parametrize("token", ["", "short", "é" * 32, "x" * 32 + "\n"])
def test_invalid_token_rejected(settings, http_worker, token):
    settings.DETECTOR_SERVICE_TOKEN = token
    # Whitespace at the end is stripped by _required_setting; reject embedded whitespace instead.
    if token.endswith("\n"):
        settings.DETECTOR_SERVICE_TOKEN = "x" * 16 + "\n" + "x" * 16
    with pytest.raises(ValueError):
        worker_request("GET", "/health")
    http_worker[0].assert_not_called()


@pytest.mark.parametrize("code", [301, 401, 422, 503])
def test_upstream_errors_are_redacted(http_worker, code):
    _, client = http_worker
    client.request.return_value = httpx.Response(
        code,
        request=httpx.Request("POST", "http://127.0.0.1:8501/infer"),
        text="sensitive upstream error must not escape",
    )
    with pytest.raises(RuntimeError, match="unavailable") as error:
        worker_request("POST", "/infer", {})
    assert "sensitive" not in str(error.value)


def test_timeout_is_redacted(http_worker):
    http_worker[1].request.side_effect = httpx.ReadTimeout("secret")
    with pytest.raises(RuntimeError, match="unavailable") as error:
        worker_request("GET", "/health")
    assert "secret" not in str(error.value)


def test_host_bytes_not_host_paths_sent_after_artifact_verification(
    artifact_files,
    tmp_path,
    monkeypatch,
):
    inputs = tmp_path / "input"
    inputs.mkdir()
    (inputs / "9-4.jpg").write_bytes(b"image")
    monkeypatch.setattr("engines.detector.artifact_for_run", lambda _: artifact_files.row)
    request = Mock(
        return_value={
            "schema_version": "labelx.detector.predictions.v1",
            "model": artifact_files.worker,
            "images": [],
        }
    )
    monkeypatch.setattr("engines.detector.worker_request", request)
    with _settings(artifact_files):
        _run_worker(inputs, _input())
    body = request.call_args.args[2]
    assert body["model_sha256"] == artifact_files.sha
    assert body["images"][0]["path"] == "9-4.jpg"
    assert body["images"][0]["image_base64"] == "aW1hZ2U="
    assert str(tmp_path) not in json.dumps(body)
    artifact_files.checkpoint.write_bytes(b"tampered")
    request.reset_mock()
    with _settings(artifact_files), pytest.raises(ValueError, match="checksum"):
        _run_worker(inputs, _input())
    request.assert_not_called()


@pytest.mark.django_db
def test_preflight_read_only_and_explicit_registration_are_idempotent(artifact_files, monkeypatch):
    from runs.models import ModelArtifact

    artifact_files.data["model"]["name"] = "fixture detector"
    artifact_files.manifest.write_text(json.dumps(artifact_files.data))
    monkeypatch.setattr(
        "runs.management.commands.check_detector.worker_request",
        lambda *args: {
            "status": "ready",
            "model": artifact_files.worker,
        },
    )
    with _settings(artifact_files):
        call_command("check_detector", stdout=io.StringIO())
        assert not ModelArtifact.objects.exists()
        call_command("check_detector", register=True, stdout=io.StringIO())
        call_command("check_detector", register=True, stdout=io.StringIO())
        assert ModelArtifact.objects.count() == 1
        ModelArtifact.objects.update(class_mapping_version="wrong")
        with pytest.raises(CommandError):
            call_command("check_detector", register=True, stdout=io.StringIO())
        assert ModelArtifact.objects.get().class_mapping_version == "wrong"


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(not os.environ.get("LABELX_DETECTOR_RUNTIME_SAMPLE"), reason="real GPU opt-in")
def test_real_bdd100k_run_reaches_checked_with_real_http_and_postgres(settings, tmp_path):
    from django.contrib.auth.models import User
    from django.core.files.base import ContentFile
    from django.core.files.storage import storages
    from PIL import Image

    from orchestration.dispatch import run_work_unit
    from orchestration.models import CandidateRecord, LedgerUnit
    from runs.models import ConfigVersion
    from runs.services import create_qc_run
    from snapshots.normalization import FrameExport, JobExport
    from snapshots.services import create_locked_snapshot

    # Only storage uses a disposable directory. GPU, HTTP, DB, dispatch and provenance are real.
    settings.STORAGES = {
        **settings.STORAGES,
        "snapshots": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path / "media")},
        },
    }
    raw = Path(os.environ["LABELX_DETECTOR_RUNTIME_SAMPLE"]).read_bytes()
    width, height = Image.open(io.BytesIO(raw)).size
    storage = storages["snapshots"]
    key = storage.save("isolated/frame.jpg", ContentFile(raw))
    call_command("check_detector", register=True, stdout=io.StringIO())
    manifest = json.loads(Path(settings.DETECTOR_MANIFEST_PATH).read_text())
    user = User.objects.create(username="blocker033-gpu")
    job = JobExport(
        cvat_job_id=18,
        cvat_task_id=21,
        source_updated_at="isolated-runtime-test",
        annotations={"shapes": [], "tracks": []},
        frames=(
            FrameExport(
                frame_index=0,
                source_frame_id=0,
                file_name="bdd100k-val.jpg",
                width=width,
                height=height,
                media_bytes=raw,
                media_storage_key=key,
            ),
        ),
        assignee_cvat_user_id=None,
    )
    snapshot = create_locked_snapshot(
        dataset_id=3, created_by=user, jobs=[job], taxonomy_version="test", guideline_version="test"
    )
    config = ConfigVersion.objects.create(
        name="BLOCKER-033 runtime",
        status="published",
        created_by=user,
        engines={"detector": {"enabled": True, "params": {"batch_size": 1}}},
        models={"name": manifest["model"]["name"], "version": manifest["model"]["version"]},
    )
    run, _ = create_qc_run(
        snapshot_id=snapshot.pk, config_version_id=config.pk, seed=42, created_by=user
    )
    unit = run.work_units.get(engine="detector")
    assert run_work_unit.run(unit.pk) == "completed"
    run.refresh_from_db()
    result = run.engine_results.get(engine="detector")
    assert run.status == "completed"
    assert result.status == "checked" and result.reason is None
    assert result.eligible_units == result.completed_units == 1
    assert result.failed_units == result.not_checked_units == 0
    assert LedgerUnit.objects.filter(run=run, outcome="completed").count() == 1
    candidates = CandidateRecord.objects.filter(run=run)
    assert candidates.exists()
    assert all(c.evidence["artifact_verified"] for c in candidates)
    assert all(c.evidence["checkpoint_sha256"] == manifest["model"]["sha256"] for c in candidates)
    before = candidates.count()
    assert run_work_unit.run(unit.pk) == "completed"
    assert candidates.count() == before  # Redelivery does not duplicate inference/evidence.
    print(f"REAL GPU PASS: detector=checked, completed=1, failed=0, candidates={before}")
