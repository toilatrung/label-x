"""Small focused suite; HTTP transport mocked, PostgreSQL real. Tailscale E2E is manual."""

import copy
import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from audit.models import AuditEvent
from engines.detector import _run_worker
from runs.gpu_worker import WorkerUnavailable, config_for_run, probe, request_worker, validate_url
from runs.models import GpuWorkerConfig, GpuWorkerSelection, ModelArtifact, RunGpuWorker
from tests.engines.test_detector import _input
from tests.orchestration.helpers import make_run

pytestmark = pytest.mark.django_db
HOST = "gpu.test-tailnet.ts.net"
TOKEN = "fixture-only-" + "x" * 32


@pytest.fixture(autouse=True)
def environment(settings):
    settings.GPU_WORKER_ALLOWED_HOSTS = [HOST, "gpu2.test-tailnet.ts.net"]
    settings.GPU_WORKER_CREDENTIALS = {"primary": TOKEN}


@pytest.fixture
def admin():
    user = User.objects.create(username="worker-admin")
    RoleAssignment.objects.create(user=user, role=Role.SUPER_ADMIN, dataset_id=None)
    client = APIClient()
    client.force_authenticate(user)
    return client


def data(revision=0, **updates):
    return {
        "revision": revision,
        "name": "GPU máy cá nhân",
        "url": "https://" + HOST,
        "credential_ref": "primary",
        "timeout_seconds": 120,
        "enabled": True,
        **updates,
    }


@pytest.fixture
def config(admin):
    reply = admin.put("/api/gpu-worker/config/", data(), format="json")
    assert reply.status_code == 200
    return GpuWorkerConfig.objects.get(pk=reply.data["config"]["revision"])


def ready(settings):
    manifest = json.loads(Path(settings.DETECTOR_MANIFEST_PATH).read_text())
    return {
        "status": "ready",
        "artifact_verified": True,
        "device": "cuda:0",
        "model": {
            "sha256": manifest["model"]["sha256"],
            "version": manifest["model"]["version"],
            "class_mapping_version": manifest["class_mapping"]["version"],
            "classes": manifest["class_mapping"]["classes"],
        },
    }


def test_config_roundtrip_revision_audit_and_no_secrets(admin):
    reply = admin.get("/api/gpu-worker/config/")
    assert reply.data["config"] is None
    first = admin.put("/api/gpu-worker/config/", data(), format="json")
    revision = first.data["config"]["revision"]
    second = admin.put("/api/gpu-worker/config/", data(revision, name="Máy mới"), format="json")
    assert second.status_code == 200
    assert GpuWorkerConfig.objects.count() == 2
    assert GpuWorkerConfig.objects.get(pk=revision).name == data()["name"]
    assert AuditEvent.objects.filter(action="gpu_worker.configure").count() == 2
    assert TOKEN not in json.dumps(second.data)
    assert TOKEN not in str(list(AuditEvent.objects.values("before", "after")))
    assert admin.put("/api/gpu-worker/config/", data(revision), format="json").status_code == 409
    assert GpuWorkerConfig.objects.count() == 2


@pytest.mark.parametrize("role,scope", [(Role.QA_LEAD, 1), (Role.REVIEWER, 1), (Role.QC_ADMIN, 1)])
def test_non_global_admin_forbidden(role, scope):
    user = User.objects.create(username="not-global", is_superuser=True)
    RoleAssignment.objects.create(user=user, role=role, dataset_id=scope)
    client = APIClient()
    client.force_authenticate(user)
    for method, path, body in [
        ("get", "config", None),
        ("put", "config", data()),
        ("post", "probe", {"revision": 1}),
    ]:
        assert (
            getattr(client, method)(
                "/api/gpu-worker/" + path + "/", body, format="json"
            ).status_code
            == 403
        )


def test_anonymous_denied_and_extra_secret_field_rejected(admin):
    assert APIClient().get("/api/gpu-worker/config/").status_code == 403
    assert (
        admin.put(
            "/api/gpu-worker/config/", data(token="must-not-store"), format="json"
        ).status_code
        == 400
    )
    assert not GpuWorkerConfig.objects.exists()


@pytest.mark.parametrize(
    "url",
    [
        "http://" + HOST,
        "https://evil.ts.net",
        "https://127.0.0.1",
        "https://" + HOST + ":8501",
        "https://" + HOST + "/other",
        "https://user:secret@" + HOST,
        "https://" + HOST + "?x=1",
        "https://" + HOST + "#x",
    ],
)
def test_ssrf_url_guard(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_unknown_credential_rejected(admin):
    assert (
        admin.put(
            "/api/gpu-worker/config/", data(credential_ref="unknown"), format="json"
        ).status_code
        == 400
    )


def test_probe_checks_model_and_does_not_require_server_checkpoint(
    admin, config, settings, monkeypatch
):
    settings.DETECTOR_CHECKPOINT_PATH = "/does-not-exist-on-labelx-server.pth"
    health = ready(settings)
    monkeypatch.setattr("runs.gpu_worker.request_worker", lambda *args: health)
    response = admin.post("/api/gpu-worker/probe/", {"revision": config.pk}, format="json")
    assert response.status_code == 200 and response.data["state"] == "ready"
    assert response.data["model"]["verified"] is True
    assert TOKEN not in json.dumps(response.data)
    health["model"]["sha256"] = "b" * 64
    assert probe(config)["state"] == "unavailable"
    assert (
        admin.post("/api/gpu-worker/probe/", {"revision": config.pk + 1}, format="json").status_code
        == 409
    )


@pytest.mark.parametrize("fault", ["offline", "cpu", "unverified", "not_loaded", "class_map"])
def test_not_ready_is_never_success(config, settings, monkeypatch, fault):
    health = ready(settings)
    if fault == "offline":

        def offline(*args):
            raise WorkerUnavailable("private diagnostic")

        monkeypatch.setattr("runs.gpu_worker.request_worker", offline)
    else:
        if fault == "cpu":
            health["device"] = "cpu"
        if fault == "unverified":
            health["artifact_verified"] = False
        if fault == "not_loaded":
            health["status"] = "loading"
        if fault == "class_map":
            health["model"]["classes"] = ["wrong"]
        monkeypatch.setattr("runs.gpu_worker.request_worker", lambda *args: health)
    result = probe(config)
    assert result["state"] == "unavailable" and result["model"] is None
    assert "private diagnostic" not in str(result)


def test_transport_has_no_proxy_redirect_and_bounded_timeout(config, monkeypatch):
    factory = MagicMock()
    client = factory.return_value.__enter__.return_value
    client.request.return_value = httpx.Response(
        503, text="private detail", request=httpx.Request("GET", "https://" + HOST)
    )
    monkeypatch.setattr("runs.gpu_worker.httpx.Client", factory)
    with pytest.raises(WorkerUnavailable) as error:
        request_worker(config, "/health")
    assert "private detail" not in str(error.value)
    assert factory.call_args.kwargs == {"timeout": 5, "trust_env": False, "follow_redirects": False}


def test_binding_unchanged_after_switch_and_remote_inference_needs_no_local_model(
    config,
    admin,
    settings,
    monkeypatch,
    tmp_path,
):
    run = make_run("fake")
    health = ready(settings)
    model = health["model"]
    artifact = ModelArtifact.objects.create(
        name="remote",
        version=model["version"],
        checksum=model["sha256"],
        class_mapping_version=model["class_mapping_version"],
        class_mapping={"classes": model["classes"]},
    )
    run.model_artifact = artifact
    run.save(update_fields=["model_artifact"])
    RunGpuWorker.objects.create(run=run, config=config)
    assert (
        admin.put(
            "/api/gpu-worker/config/",
            data(config.pk, url="https://gpu2.test-tailnet.ts.net"),
            format="json",
        ).status_code
        == 200
    )
    assert config_for_run(run.pk).pk == config.pk
    settings.DETECTOR_CHECKPOINT_PATH = "/server-has-no-model.pth"
    observed = []

    def upstream(revision, path, body=None):
        observed.append((revision.pk, path))
        if path == "/health":
            return health
        return {
            "schema_version": "labelx.detector.predictions.v1",
            "artifact_verified": True,
            "model": copy.deepcopy(model),
            "images": [],
        }

    monkeypatch.setattr("runs.gpu_worker.request_worker", upstream)
    inputs = tmp_path / "input"
    inputs.mkdir()
    (inputs / "frame.jpg").write_bytes(b"fixture")
    engine_input = _input()
    from dataclasses import replace

    _run_worker(inputs, replace(engine_input, run_id=run.pk))
    assert observed == [(config.pk, "/health"), (config.pk, "/infer")]


def test_prepare_blocks_offline_and_disabled_before_run(config, monkeypatch):
    from runs.gpu_worker import prepare

    monkeypatch.setattr("runs.gpu_worker.probe", lambda *args: {"state": "unavailable"})
    with pytest.raises(WorkerUnavailable):
        prepare(None)
    config.enabled = False
    assert probe(config)["state"] == "disabled"
    assert GpuWorkerSelection.objects.get(pk=1).config_id == config.pk


def test_create_run_preflights_then_pins_revision(config, settings, monkeypatch):
    from runs.models import ConfigVersion, QCRun
    from runs.services import BusinessRuleUnmetError, create_qc_run

    previous = make_run("fake")
    health = ready(settings)
    model = health["model"]
    ModelArtifact.objects.create(
        name="remote",
        version=model["version"],
        checksum=model["sha256"],
        class_mapping_version=model["class_mapping_version"],
        class_mapping={"classes": model["classes"]},
    )
    cfg = ConfigVersion.objects.create(
        name="remote detector",
        status="published",
        created_by=previous.created_by,
        engines={"detector": {"enabled": True}},
        models={"name": "remote", "version": model["version"]},
    )
    monkeypatch.setattr("runs.gpu_worker.request_worker", lambda *args: {"status": "loading"})
    before = QCRun.objects.count()
    with pytest.raises(BusinessRuleUnmetError):
        create_qc_run(
            snapshot_id=previous.snapshot_id,
            config_version_id=cfg.pk,
            seed=99,
            created_by=previous.created_by,
        )
    assert QCRun.objects.count() == before
    monkeypatch.setattr("runs.gpu_worker.request_worker", lambda *args: health)
    run, created = create_qc_run(
        snapshot_id=previous.snapshot_id,
        config_version_id=cfg.pk,
        seed=99,
        created_by=previous.created_by,
    )
    assert created and run.model_artifact is not None
    assert config_for_run(run.pk).pk == config.pk


def test_register_remote_artifact_does_not_read_host_checkpoint(config, settings, monkeypatch):
    import io

    from django.core.management import call_command

    settings.DETECTOR_CHECKPOINT_PATH = "/not-on-the-labelx-server.pth"
    health = ready(settings)
    monkeypatch.setattr("runs.gpu_worker.request_worker", lambda *args: health)
    call_command("check_detector", register=True, stdout=io.StringIO())
    call_command("check_detector", register=True, stdout=io.StringIO())
    assert ModelArtifact.objects.count() == 1
    assert ModelArtifact.objects.get().checksum == health["model"]["sha256"]


def test_corrupt_snapshot_media_never_reaches_worker(monkeypatch):
    from dataclasses import replace

    from django.core.files.base import ContentFile

    from engines.detector import run_detector_engine
    from engines.interface import EngineUnitRef, FrameKey

    run = make_run("fake")
    stores = MagicMock()
    stores.__getitem__.return_value.open.side_effect = lambda *args: ContentFile(b"corrupt")
    monkeypatch.setattr("engines.detector.storages", stores)
    upstream = MagicMock()
    monkeypatch.setattr("engines.detector._run_worker", upstream)
    inp = replace(
        _input(),
        run_id=run.pk,
        snapshot_id=run.snapshot_id,
        units=(EngineUnitRef("frame", FrameKey(9, 0)),),
    )
    with pytest.raises(ValueError, match="media"):
        run_detector_engine(inp)
    upstream.assert_not_called()
