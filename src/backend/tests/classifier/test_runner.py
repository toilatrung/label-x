"""M04B-03: runner tiến trình riêng — lệnh từ settings, không shell, timeout, đầu ra bị kiểm."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from classifier.errors import ClassifierReason, ClassifierRunError
from classifier.runner import (
    CropItem,
    SubprocessClassifierRunner,
    artifact_manifest_path,
    parse_batch_output,
)

SHA = "b" * 64
PRED = {
    "top3": [
        {"class_id": 2, "class_name": "car", "score": 0.7},
        {"class_id": 3, "class_name": "truck", "score": 0.2},
        {"class_id": 4, "class_name": "bus", "score": 0.1},
    ],
    "score": 0.7,
    "margin": 0.5,
    "calibrated": False,
}


def output(**over: Any) -> str:
    data: dict[str, Any] = {
        "checkpoint": {
            "version": "v1",
            "sha256": SHA,
            "status": "smoke_only",
            "class_map_version": "bdd100k-det-10-v1",
        },
        "results": [{"id": "1", "ok": True, "prediction": PRED}],
    }
    data.update(over)
    return json.dumps(data)


@pytest.fixture
def artifact_root(tmp_path: Path, settings: Any) -> Path:
    settings.CLASSIFIER_ARTIFACT_ROOT = str(tmp_path / "artifacts")
    directory = tmp_path / "artifacts" / "classifier" / "v1"
    directory.mkdir(parents=True)
    (directory / "classifier-manifest.json").write_text("{}")
    return tmp_path / "artifacts"


def fake_worker(tmp_path: Path, body: str) -> list[str]:
    script = tmp_path / "worker.py"
    script.write_text(body)
    return [sys.executable, str(script)]


def test_parse_ok_and_per_item_failure() -> None:
    result = parse_batch_output(
        output(
            results=[
                {"id": "1", "ok": True, "prediction": PRED},
                {"id": "2", "ok": False, "reason": "box_too_small"},
            ]
        ),
        expected_sha256=SHA,
    )
    assert result.items["1"].ok and result.items["1"].prediction["score"] == 0.7
    assert not result.items["2"].ok and result.items["2"].reason == "box_too_small"


@pytest.mark.parametrize(
    ("stdout", "reason"),
    [
        ("not json", ClassifierReason.INFERENCE_ERROR),
        ("{}", ClassifierReason.INFERENCE_ERROR),
        (
            output(checkpoint={"version": "v", "sha256": "c" * 64}),
            ClassifierReason.CHECKSUM_MISMATCH,
        ),
    ],
)
def test_parse_rejects_bad_output(stdout: str, reason: ClassifierReason) -> None:
    with pytest.raises(ClassifierRunError) as excinfo:
        parse_batch_output(stdout, expected_sha256=SHA)
    assert excinfo.value.reason == reason


def run(runner_key: str = "classifier/v1") -> Any:
    return SubprocessClassifierRunner().run(
        artifact_key=runner_key, expected_sha256=SHA, crops=[CropItem("1", b"png")]
    )


def test_runs_command_from_settings_without_shell(artifact_root, settings, tmp_path, monkeypatch):
    settings.CLASSIFIER_WORKER_COMMAND = fake_worker(
        tmp_path, f"import sys\nassert sys.argv[1] == 'predict-batch'\nprint({output()!r})\n"
    )
    seen: dict[str, Any] = {}
    real = subprocess.Popen

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.update(kwargs, argv=args[0])
        return real(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", spy)
    result = run()
    assert result.items["1"].ok
    assert seen["shell"] is False and isinstance(seen["argv"], list)
    assert seen["start_new_session"] is True


def test_worker_does_not_inherit_backend_secrets(artifact_root, settings, tmp_path, monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "super-secret")
    monkeypatch.setenv("DATABASE_URL", "postgres://u:pw@h/db")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-live")
    settings.CLASSIFIER_WORKER_COMMAND = fake_worker(
        tmp_path,
        "import os, sys\n"
        "secrets = ('DJANGO_SECRET_KEY', 'DATABASE_URL', 'DASHSCOPE_API_KEY')\n"
        "bad = [k for k in secrets if k in os.environ]\n"
        "assert not bad, bad\n"
        "assert 'PATH' in os.environ\n"
        f"print({output()!r})\n",
    )
    assert run().items["1"].ok


def test_timeout_kills_the_whole_process_group(artifact_root, settings, tmp_path):
    pid_file = tmp_path / "grandchild.pid"
    settings.CLASSIFIER_WORKER_COMMAND = fake_worker(
        tmp_path,
        "import subprocess, sys, time\n"
        f"child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
        "time.sleep(60)\n",
    )
    settings.CLASSIFIER_TIMEOUT_SECONDS = 1.5
    started = time.monotonic()
    with pytest.raises(ClassifierRunError) as excinfo:
        run()
    assert excinfo.value.reason == ClassifierReason.TIMEOUT
    # a surviving grandchild keeps the pipe open and would block this call for ~60 s
    assert time.monotonic() - started < 15
    pid = int(pid_file.read_text())
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(pid, 9)
        pytest.fail("grandchild survived the timeout")


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        (3, ClassifierReason.CHECKSUM_MISMATCH),
        (4, ClassifierReason.CHECKPOINT_UNAVAILABLE),
        (2, ClassifierReason.INFERENCE_ERROR),
        (1, ClassifierReason.INFERENCE_ERROR),
    ],
)
def test_exit_codes_map_to_stable_reasons(artifact_root, settings, tmp_path, code, reason, caplog):
    settings.CLASSIFIER_WORKER_COMMAND = fake_worker(
        tmp_path, f"import sys\nsys.stderr.write('Traceback /secret/path')\nsys.exit({code})\n"
    )
    with pytest.raises(ClassifierRunError) as excinfo:
        run()
    assert excinfo.value.reason == reason
    assert "/secret/path" not in str(excinfo.value)


def test_timeout_is_a_stable_reason(artifact_root, settings, tmp_path):
    settings.CLASSIFIER_WORKER_COMMAND = fake_worker(tmp_path, "import time\ntime.sleep(5)\n")
    settings.CLASSIFIER_TIMEOUT_SECONDS = 0.5
    with pytest.raises(ClassifierRunError) as excinfo:
        run()
    assert excinfo.value.reason == ClassifierReason.TIMEOUT


def test_not_configured_and_unstartable_command(artifact_root, settings):
    settings.CLASSIFIER_WORKER_COMMAND = []
    with pytest.raises(ClassifierRunError) as excinfo:
        run()
    assert excinfo.value.reason == ClassifierReason.NOT_CONFIGURED
    settings.CLASSIFIER_WORKER_COMMAND = ["/nonexistent/worker-binary"]
    with pytest.raises(ClassifierRunError) as excinfo:
        run()
    assert excinfo.value.reason == ClassifierReason.NOT_CONFIGURED


@pytest.mark.parametrize("key", ["", "../../etc", "classifier/missing", "/etc"])
def test_artifact_key_cannot_escape_or_be_missing(artifact_root, settings, tmp_path, key):
    settings.CLASSIFIER_WORKER_COMMAND = fake_worker(tmp_path, f"print({output()!r})\n")
    assert artifact_manifest_path(key) is None
    with pytest.raises(ClassifierRunError) as excinfo:
        run(key)
    assert excinfo.value.reason == ClassifierReason.CHECKPOINT_UNAVAILABLE


def test_no_artifact_root_means_unavailable(settings):
    settings.CLASSIFIER_ARTIFACT_ROOT = ""
    assert artifact_manifest_path("classifier/v1") is None


def test_crop_bytes_do_not_leak_into_repr() -> None:
    assert b"secret-bytes" not in repr(CropItem("1", b"secret-bytes")).encode()


def test_crops_are_passed_as_relative_names_under_image_root(artifact_root, settings, tmp_path):
    settings.CLASSIFIER_WORKER_COMMAND = fake_worker(
        tmp_path,
        "import json, os, sys\n"
        "args = sys.argv\n"
        "root = args[args.index('--image-root') + 1]\n"
        "items = json.load(open(args[args.index('--input') + 1]))\n"
        "assert all(not os.path.isabs(i['image']) for i in items), items\n"
        "assert all(os.path.isfile(os.path.join(root, i['image'])) for i in items)\n"
        f"print({output()!r})\n",
    )
    assert run().items["1"].ok


def prediction_row(**over: Any) -> str:
    return output(results=[{"id": "1", "ok": True, "prediction": {**PRED, **over}}])


@pytest.mark.parametrize(
    "bad",
    [
        {
            "top3": [
                {"class_id": 2, "class_name": "car", "score": 0.1},
                {"class_id": 3, "class_name": "truck", "score": 0.8},
            ],
            "score": 0.1,
            "margin": 0.0,
        },
        {
            "top3": [
                {"class_id": 2, "class_name": "car", "score": 0.7},
                {"class_id": 3, "class_name": "truck", "score": 0.1},
                {"class_id": 4, "class_name": "bus", "score": 0.2},
            ],
            "margin": 0.6,
        },  # only the 2nd/3rd entries are out of order
        {"score": 0.1},  # score != top-1
        {"margin": 0.9},  # margin != s1 - s2
        {"margin": -0.7},
        {"score": 1.5, "top3": [{"class_id": 2, "class_name": "car", "score": 1.5}], "margin": 1.5},
        {
            "top3": [
                {"class_id": 2, "class_name": "car", "score": 0.7},
                {"class_id": 2, "class_name": "car", "score": 0.2},
            ]
        },
        {"top3": [{"class_id": True, "class_name": "car", "score": 0.7}]},
    ],
)
def test_inconsistent_predictions_become_inference_error_not_stored(bad: dict[str, Any]) -> None:
    result = parse_batch_output(prediction_row(**bad), expected_sha256=SHA)
    assert result.items["1"].ok is False
    assert result.items["1"].reason == ClassifierReason.INFERENCE_ERROR.value


def test_class_names_come_from_the_class_map_not_the_worker() -> None:
    fake = {
        **PRED,
        "top3": [
            {"class_id": 0, "class_name": "FAKE-NAME", "score": 0.7},
            {"class_id": 3, "class_name": "x" * 500, "score": 0.2},
        ],
        "margin": 0.5,
    }
    result = parse_batch_output(
        output(results=[{"id": "1", "ok": True, "prediction": fake}]), expected_sha256=SHA
    )
    names = [e["class_name"] for e in result.items["1"].prediction["top3"]]
    assert names == ["pedestrian", "truck"]


@pytest.mark.parametrize(
    ("worker_reason", "expected"),
    [
        ("box_too_small", "box_too_small"),
        ("invalid_crop", "invalid_crop"),
        ("duplicate_id", "invalid_crop"),
        ("sk-LEAK /etc/passwd", "inference_error"),
        ("x" * 500, "inference_error"),
        (None, "inference_error"),
    ],
)
def test_item_reasons_are_mapped_to_the_enum(worker_reason: Any, expected: str) -> None:
    result = parse_batch_output(
        output(results=[{"id": "1", "ok": False, "reason": worker_reason}]), expected_sha256=SHA
    )
    assert result.items["1"].reason == expected


@pytest.mark.parametrize(
    "checkpoint",
    [
        {
            "version": "v" * 100,
            "sha256": SHA,
            "status": "smoke_only",
            "class_map_version": "bdd100k-det-10-v1",
        },
        {
            "version": "v 1;rm",
            "sha256": SHA,
            "status": "smoke_only",
            "class_map_version": "bdd100k-det-10-v1",
        },
        {
            "version": "v1",
            "sha256": SHA,
            "status": "validated",
            "class_map_version": "bdd100k-det-10-v1",
        },
        {"version": "v1", "sha256": SHA, "status": "trained", "class_map_version": "other"},
        {
            "version": 5,
            "sha256": SHA,
            "status": "trained",
            "class_map_version": "bdd100k-det-10-v1",
        },
    ],
)
def test_checkpoint_fields_are_validated(checkpoint: dict[str, Any]) -> None:
    with pytest.raises(ClassifierRunError):
        parse_batch_output(output(checkpoint=checkpoint), expected_sha256=SHA)
