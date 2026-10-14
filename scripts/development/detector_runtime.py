"""Compose lifecycle for host Django/Celery and an isolated GPU worker. No secrets in argv."""

import argparse
import os
import re
import secrets
import subprocess
from pathlib import Path

import environ

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["configure", "up", "down", "logs"])
    parser.add_argument("--checkpoint", type=Path)
    args = parser.parse_args()
    if args.command == "configure":
        if not args.checkpoint or not args.checkpoint.is_file():
            parser.error(
                "configure requires --checkpoint pointing to an existing host checkpoint"
            )
        target = ROOT / "src/backend/.env"
        if not target.is_file():
            parser.error("Create backend .env first (make env)")
        text = target.read_text(encoding="utf-8")
        values = environ.Env()
        environ.Env.read_env(target)
        token = values("DETECTOR_SERVICE_TOKEN", default="") or secrets.token_hex(32)
        updates = {
            "DETECTOR_CHECKPOINT_PATH": args.checkpoint.resolve().as_posix(),
            "DETECTOR_SERVICE_TOKEN": token,
            "DETECTOR_WORKER_URL": "http://127.0.0.1:8501",
            "DETECTOR_MANIFEST_PATH": (
                ROOT / "src/detector_worker/model-manifest.json"
            ).as_posix(),
        }
        for key, value in updates.items():
            pattern = rf"(?m)^{key}=.*$"
            text = (
                re.sub(pattern, lambda _, key=key, value=value: f"{key}={value}", text)
                if re.search(pattern, text)
                else (text.rstrip() + f"\n{key}={value}\n")
            )
        target.write_text(text, encoding="utf-8")
        print(
            "Updated only detector host paths, loopback URL and token in ignored backend .env"
        )
        return
    env = environ.Env()
    environ.Env.read_env(ROOT / "src/backend/.env")
    checkpoint = Path(
        env(
            "DETECTOR_CHECKPOINT_PATH",
            default=str(ROOT / ".cache/models/faster_rcnn_r50_fpn_3x_det_bdd100k.pth"),
        )
    ).resolve()
    token = env("DETECTOR_SERVICE_TOKEN", default="")
    if args.command == "up":
        if not checkpoint.is_file():
            parser.error(
                "Missing host checkpoint; set DETECTOR_CHECKPOINT_PATH in backend .env"
            )
        if checkpoint.name != "faster_rcnn_r50_fpn_3x_det_bdd100k.pth":
            parser.error("Checkpoint must use the frozen manifest filename")
        if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
            parser.error(
                "Set a random DETECTOR_SERVICE_TOKEN (>=32 ASCII characters) in backend .env"
            )
    environment = dict(os.environ)
    environment.update(
        DETECTOR_MODEL_DIR=str(checkpoint.parent),
        DETECTOR_SERVICE_TOKEN=token or "not-used-for-stopping-the-container",
        DETECTOR_DEVICE=env("DETECTOR_DEVICE", default="cuda:0"),
    )
    command = [
        "docker",
        "compose",
        "-f",
        str(ROOT / "infrastructure/docker-compose.detector.yml"),
    ]
    if environment["DETECTOR_DEVICE"].startswith("cuda"):
        command += ["-f", str(ROOT / "infrastructure/docker-compose.detector-gpu.yml")]
    command += {
        "up": ["up", "-d", "--build", "--wait", "--wait-timeout", "240"],
        "down": ["down"],
        "logs": ["logs", "--tail", "100"],
    }[args.command]
    subprocess.run(command, env=environment, check=True)


if __name__ == "__main__":
    main()
