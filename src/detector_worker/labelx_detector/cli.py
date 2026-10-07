"""Command-line entry point for artifact lifecycle and inference."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .artifact import ArtifactManifest, freeze_checkpoint, verify_checkpoint
from .inference import run_batch
from .storage import S3Credentials, fetch_checkpoint, publish_checkpoint


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="labelx-detector")
    subcommands = parser.add_subparsers(dest="command", required=True)

    freeze = subcommands.add_parser("freeze", help="record checkpoint SHA-256 in the manifest")
    freeze.add_argument("--checkpoint", required=True, type=Path)
    freeze.add_argument("--manifest", required=True, type=Path)

    verify = subcommands.add_parser("verify", help="verify checkpoint against frozen SHA-256")
    verify.add_argument("--checkpoint", required=True, type=Path)
    verify.add_argument("--manifest", required=True, type=Path)

    for command, help_text in (
        ("publish", "publish a verified checkpoint to S3-compatible storage"),
        ("fetch", "fetch and verify a checkpoint from S3-compatible storage"),
    ):
        artifact = subcommands.add_parser(command, help=help_text)
        artifact.add_argument("--checkpoint", required=True, type=Path)
        artifact.add_argument("--manifest", required=True, type=Path)
        artifact.add_argument("--endpoint", required=True)
        artifact.add_argument("--bucket", required=True)
        artifact.add_argument("--key", required=True)
        artifact.add_argument("--region", default="us-east-1")

    infer = subcommands.add_parser("infer", help="run deterministic folder-to-JSON inference")
    infer.add_argument("--input-dir", required=True, type=Path)
    infer.add_argument("--output", required=True, type=Path)
    infer.add_argument("--checkpoint", required=True, type=Path)
    infer.add_argument("--manifest", required=True, type=Path)
    infer.add_argument("--config", required=True, type=Path)
    infer.add_argument("--device", default="cuda:0")
    infer.add_argument("--batch-size", type=int, default=1)
    infer.add_argument("--score-threshold", type=float, default=0.05)
    infer.add_argument("--recursive", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "freeze":
        digest = freeze_checkpoint(args.checkpoint, args.manifest)
        print(json.dumps({"status": "frozen", "sha256": digest}))
        return 0

    manifest = ArtifactManifest.load(args.manifest)
    if args.command == "verify":
        digest = verify_checkpoint(args.checkpoint, manifest)
        print(json.dumps({"status": "verified", "sha256": digest}))
        return 0

    if args.command in {"publish", "fetch"}:
        credentials = S3Credentials.from_environment()
        if args.command == "publish":
            uri = publish_checkpoint(
                args.checkpoint,
                manifest,
                args.endpoint,
                args.bucket,
                args.key,
                args.region,
                credentials,
            )
            print(json.dumps({"status": "published", "uri": uri, "sha256": manifest.sha256}))
        else:
            digest = fetch_checkpoint(
                args.checkpoint,
                manifest,
                args.endpoint,
                args.bucket,
                args.key,
                args.region,
                credentials,
            )
            print(json.dumps({"status": "fetched", "sha256": digest}))
        return 0

    payload = run_batch(
        input_directory=args.input_dir,
        output=args.output,
        checkpoint=args.checkpoint,
        manifest=manifest,
        config=args.config,
        device=args.device,
        batch_size=args.batch_size,
        score_threshold=args.score_threshold,
        recursive=args.recursive,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "images": payload["run"]["image_count"],
                "seconds_per_image": payload["run"]["seconds_per_image"],
                "output": str(args.output.resolve()),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
