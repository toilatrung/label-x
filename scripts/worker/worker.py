#!/usr/bin/env python3
"""Standalone GPU host lifecycle. Python 3.10+ stdlib; no backend dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".cache" / "gpu-worker"
PROJECT = "labelx-gpu-worker"
IMAGE = "labelx-detector-worker:gpu"


def manifest() -> dict:
    return json.loads(
        (ROOT / "src/detector_worker/model-manifest.json").read_text("utf-8")
    )


def validate_token(token: str) -> str:
    if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("Token must contain >=32 non-whitespace ASCII characters.")
    return token


def verify_checkpoint(checkpoint: Path) -> Path:
    checkpoint = checkpoint.expanduser().resolve(strict=True)
    model = manifest()["model"]
    if not checkpoint.is_file() or checkpoint.name != model["checkpoint_filename"]:
        raise ValueError("Checkpoint filename must match model-manifest.json.")
    digest = hashlib.sha256()
    with checkpoint.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != model["sha256"]:
        raise ValueError("Checkpoint SHA-256 does not match the frozen manifest.")
    return checkpoint


def private_write(path: Path, value: str) -> None:
    """Atomic replacement, restrictive POSIX mode; Windows inherits directory ACL."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load() -> tuple[dict, str]:
    config = json.loads((STATE / "config.json").read_text("utf-8"))
    if not isinstance(config, dict):
        raise TypeError("Invalid local worker profile; run configure again.")
    if (
        type(config.get("port")) is not int
        or not 1024 <= config["port"] <= 65535
        or not re.fullmatch(r"cuda:\d+|cpu", config.get("device", ""))
        or not isinstance(config.get("checkpoint"), str)
    ):
        raise ValueError("Invalid local worker profile; run configure again.")
    token = validate_token(
        (STATE / "worker.env")
        .read_text("utf-8")
        .removeprefix("DETECTOR_SERVICE_TOKEN=")
        .strip()
    )
    return config, token


def configure(args: argparse.Namespace) -> None:
    checkpoint = verify_checkpoint(Path(args.checkpoint))
    if not re.fullmatch(r"cuda:\d+|cpu", args.device) or not 1024 <= args.port <= 65535:
        raise ValueError("Use device cuda:N or cpu and a port between 1024 and 65535.")
    secret_path = STATE / "worker.env"
    if args.token_file:
        token = validate_token(Path(args.token_file).read_text("utf-8-sig").strip())
    elif secret_path.exists():
        token = validate_token(
            secret_path.read_text("utf-8")
            .removeprefix("DETECTOR_SERVICE_TOKEN=")
            .strip()
        )
    else:
        token = secrets.token_hex(32)
    private_write(secret_path, f"DETECTOR_SERVICE_TOKEN={token}\n")
    private_write(
        STATE / "config.json",
        json.dumps(
            {
                "checkpoint": str(checkpoint),
                "device": args.device,
                "port": args.port,
            },
            indent=2,
        )
        + "\n",
    )
    print("Checkpoint verified. Profile: .cache/gpu-worker/config.json")
    print("Secret: .cache/gpu-worker/worker.env (ignored by Git; never share/commit).")


def run(command: list[str], env: dict | None = None) -> None:
    # No shell, no token in argv, no automatic Docker/Tailscale installation.
    result = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if result.returncode:
        raise ValueError(
            f"Command failed (exit {result.returncode}); inspect the output above."
        )


def compose(action: str) -> None:
    config, token = load()
    checkpoint = Path(config["checkpoint"])
    if action == "start":
        checkpoint = verify_checkpoint(checkpoint)
    env = os.environ.copy()
    env.update(
        {
            "DETECTOR_SERVICE_TOKEN": token,
            "DETECTOR_MODEL_DIR": str(checkpoint.parent),
            "DETECTOR_DEVICE": config["device"],
            "DETECTOR_HOST_PORT": str(config["port"]),
            "DETECTOR_IMAGE": IMAGE,
            # Ignore unrelated backend .env and inherited Compose service profiles.
            "COMPOSE_PROFILES": "",
        }
    )
    command = [
        "docker",
        "compose",
        "--env-file",
        str(STATE / "worker.env"),
        "--project-name",
        PROJECT,
        "-f",
        str(ROOT / "infrastructure/docker-compose.detector.yml"),
    ]
    if config["device"].startswith("cuda:"):
        command.extend(
            ["-f", str(ROOT / "infrastructure/docker-compose.detector-gpu.yml")]
        )
    command.extend(
        {
            "start": [
                "up",
                "--detach",
                "--no-build",
                "--pull",
                "never",
                "--wait",
                "--wait-timeout",
                "240",
            ],
            "stop": ["down"],  # Own project only; no volume deletion.
            "status": ["ps", "--all"],
            "logs": ["logs", "--tail", "100"],
        }[action]
    )
    run(command, env)


def validate_health(payload: dict, config: dict) -> None:
    expected = manifest()
    if not isinstance(payload, dict):
        raise TypeError("Invalid worker health response.")
    model = payload.get("model")
    if (
        payload.get("status") != "ready"
        or payload.get("artifact_verified") is not True
        or payload.get("device") != config["device"]
        or not isinstance(model, dict)
        or model.get("sha256") != expected["model"]["sha256"]
        or model.get("version") != expected["model"]["version"]
        or model.get("class_mapping_version") != expected["class_mapping"]["version"]
        or model.get("classes") != expected["class_mapping"]["classes"]
    ):
        raise ValueError(
            "Worker health is not ready or does not match the frozen model/device."
        )


def check() -> None:
    config, token = load()
    request = urllib.request.Request(
        f"http://127.0.0.1:{config['port']}/health",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Do not send localhost credentials through system proxies or redirects.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    client = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with client.open(request, timeout=5) as response:
        payload = json.loads(response.read(65537))
    validate_health(payload, config)
    print(
        f"READY: verified model, device={config['device']}, loopback port={config['port']}"
    )
    if config["device"] == "cpu":
        print("CPU debug only: Label-X remote preflight requires CUDA.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    setup = commands.add_parser(
        "configure", help="Verify existing checkpoint; save ignored local profile."
    )
    setup.add_argument("--checkpoint", required=True)
    setup.add_argument("--device", default="cuda:0")
    setup.add_argument("--port", type=int, default=8501)
    setup.add_argument(
        "--token-file",
        help="Optional plaintext token file (not a command-line secret).",
    )
    commands.add_parser(
        "build", help="Explicit GPU image build; may download large dependencies."
    )
    for action in ("start", "stop", "status", "logs", "check", "tailscale-command"):
        commands.add_parser(action)
    args = parser.parse_args(argv)
    try:
        if args.action == "configure":
            configure(args)
        elif args.action == "build":
            run(
                [
                    "docker",
                    "build",
                    "-f",
                    str(ROOT / "infrastructure/detector-worker/Dockerfile"),
                    "-t",
                    IMAGE,
                    str(ROOT),
                ]
            )
        elif args.action == "check":
            check()
        elif args.action == "tailscale-command":
            config, _ = load()
            print(
                "Review existing Serve config/grants first; run manually (never Funnel):"
            )
            print(f"tailscale serve --bg http://127.0.0.1:{config['port']}")
            print("tailscale serve status")
        else:
            compose(args.action)
    except (OSError, ValueError, TypeError) as error:
        # Avoid leaking token/config/HTTP response contents through error strings.
        print(
            f"Worker command failed ({type(error).__name__}). Check profile, checkpoint, "
            "Docker/GPU and local worker logs; secrets are not printed.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
