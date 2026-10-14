"""Light stdlib tests; no Docker, GPU, network or application database required."""

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "worker", Path(__file__).parents[1] / "worker.py"
)
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.checkpoint = self.directory / "model.pth"
        self.checkpoint.write_bytes(b"fixture checkpoint, not a real model")
        self.frozen = {
            "model": {
                "checkpoint_filename": "model.pth",
                "version": "v1",
                "sha256": hashlib.sha256(self.checkpoint.read_bytes()).hexdigest(),
            },
            "class_mapping": {
                "version": "classes-v1",
                "classes": [str(i) for i in range(10)],
            },
        }
        self.state_patch = patch.object(worker, "STATE", self.directory / "state")
        self.manifest_patch = patch.object(worker, "manifest", return_value=self.frozen)
        self.state_patch.start()
        self.manifest_patch.start()
        self.addCleanup(self.state_patch.stop)
        self.addCleanup(self.manifest_patch.stop)
        self.stdout = io.StringIO()
        self.output = contextlib.redirect_stdout(self.stdout)
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def configure(self, **kwargs):
        values = {
            "checkpoint": str(self.checkpoint),
            "device": "cuda:0",
            "port": 8501,
            "token_file": None,
        }
        values.update(kwargs)
        worker.configure(argparse.Namespace(**values))
        return worker.load()

    def health(self):
        return {
            "status": "ready",
            "artifact_verified": True,
            "device": "cuda:0",
            "model": {
                "sha256": self.frozen["model"]["sha256"],
                "version": "v1",
                "class_mapping_version": "classes-v1",
                "classes": self.frozen["class_mapping"]["classes"],
            },
        }

    def test_configure_private_reuses_token_without_printing(self):
        config, token = self.configure()
        self.assertEqual(config["port"], 8501)
        self.assertEqual(len(token), 64)
        self.assertEqual(self.configure()[1], token)
        self.assertNotIn(token, self.stdout.getvalue())
        if os.name != "nt":
            self.assertEqual(
                (worker.STATE / "worker.env").stat().st_mode & 0o777, 0o600
            )

    def test_explicit_token_file(self):
        source = self.directory / "secret.txt"
        source.write_text("a" * 40 + "\n", "utf-8")
        self.assertEqual(self.configure(token_file=str(source))[1], "a" * 40)

    def test_bad_checkpoint_never_creates_state(self):
        self.checkpoint.write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            self.configure()
        self.assertFalse(worker.STATE.exists())

    def test_wrong_filename_rejected(self):
        other = self.directory / "wrong.pth"
        other.write_bytes(self.checkpoint.read_bytes())
        with self.assertRaises(ValueError):
            self.configure(checkpoint=str(other))

    def test_invalid_parameters_never_create_state(self):
        for values in ({"device": "cuda:0;bad"}, {"port": 80}, {"port": 65536}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.configure(**values)
        self.assertFalse(worker.STATE.exists())

    def test_bad_tokens_rejected(self):
        for token in ("short", "a" * 32 + "\n", "é" * 32):
            with self.subTest(token=token), self.assertRaises(ValueError):
                worker.validate_token(token)

    def test_start_uses_isolated_project_loopback_and_no_token_argv(self):
        config, token = self.configure(port=8502)
        with patch.object(worker, "run") as run:
            worker.compose("start")
        command, env = run.call_args.args
        self.assertIn("labelx-gpu-worker", command)
        self.assertIn("--no-build", command)
        self.assertIn("never", command)
        self.assertTrue(any("detector-gpu.yml" in part for part in command))
        self.assertNotIn(token, " ".join(command))
        self.assertEqual(env["DETECTOR_SERVICE_TOKEN"], token)
        self.assertEqual(env["DETECTOR_HOST_PORT"], str(config["port"]))
        self.assertEqual(env["DETECTOR_IMAGE"], "labelx-detector-worker:gpu")

    def test_start_checks_corruption_before_docker(self):
        self.configure()
        self.checkpoint.write_bytes(b"changed")
        with patch.object(worker, "run") as run, self.assertRaises(ValueError):
            worker.compose("start")
        run.assert_not_called()

    def test_stop_works_without_checkpoint_no_volume_deletion(self):
        self.configure()
        self.checkpoint.unlink()
        with patch.object(worker, "run") as run:
            worker.compose("stop")
        command = run.call_args.args[0]
        self.assertEqual(command[-1], "down")
        self.assertNotIn("--volumes", command)

    def test_cpu_profile_has_no_gpu_override(self):
        self.configure(device="cpu")
        with patch.object(worker, "run") as run:
            worker.compose("start")
        self.assertFalse(
            any("detector-gpu.yml" in part for part in run.call_args.args[0])
        )

    def test_health_must_match_artifact_classes_device(self):
        config, _ = self.configure()
        worker.validate_health(self.health(), config)
        for field, value in (
            ("status", "loading"),
            ("device", "cpu"),
            ("artifact_verified", False),
            ("model", {}),
        ):
            response = self.health()
            response[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                worker.validate_health(response, config)
        for field in ("sha256", "version", "classes", "class_mapping_version"):
            response = self.health()
            response["model"][field] = None
            with self.subTest(field=field), self.assertRaises(ValueError):
                worker.validate_health(response, config)

    def test_probe_localhost_auth_bounded_and_no_proxy(self):
        _, token = self.configure()
        with patch.object(worker.urllib.request, "build_opener") as build:
            client = build.return_value
            response = client.open.return_value.__enter__.return_value
            response.read.return_value = json.dumps(self.health()).encode()
            worker.check()
        self.assertEqual(build.call_args.args[0].proxies, {})
        redirect = build.call_args.args[1]
        self.assertIsNone(
            redirect.redirect_request(None, None, 302, "", {}, "https://bad")
        )
        request = client.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8501/health")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + token)
        self.assertEqual(client.open.call_args.kwargs["timeout"], 5)
        self.assertNotIn(token, self.stdout.getvalue())

    def test_tailscale_only_prints_command(self):
        self.configure(port=8502)
        with patch.object(worker.subprocess, "run") as run:
            self.assertEqual(worker.main(["tailscale-command"]), 0)
        run.assert_not_called()
        self.assertIn(
            "tailscale serve --bg http://127.0.0.1:8502", self.stdout.getvalue()
        )

    def test_cli_failure_never_prints_underlying_secret(self):
        stderr = io.StringIO()
        with (
            patch.object(worker, "check", side_effect=ValueError("SECRET")),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(worker.main(["check"]), 1)
        self.assertNotIn("SECRET", stderr.getvalue())

    def test_non_object_profile_and_health_rejected(self):
        config, _ = self.configure()
        with self.assertRaises(TypeError):
            worker.validate_health([], config)
        (worker.STATE / "config.json").write_text("[]", "utf-8")
        with self.assertRaises(TypeError):
            worker.load()


if __name__ == "__main__":
    unittest.main()
