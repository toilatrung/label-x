"""Command line entry points: build-dataset, train, verify, predict."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

from .artifact import ChecksumMismatchError, ClassifierArtifact, ManifestError
from .crops import letterbox_crop
from .dataset import DatasetError, SplitConfig, build_dataset, parse_label_map
from .infer import Classifier, predict_batch
from .train import TrainingDataError, train_classifier

EXIT_CHECKSUM_MISMATCH = 3  # the backend maps these codes to stable reason codes
EXIT_BAD_MANIFEST = 4


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="labelx-classifier")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-dataset", help="crop a normalized snapshot into a dataset")
    build.add_argument("--snapshot", type=Path, required=True)
    build.add_argument("--label-map", type=Path, required=True, help='JSON {"<label_id>": "name"}')
    build.add_argument("--image-root", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--group-by", choices=("task", "job", "frame"), default="task")
    build.add_argument("--val-fraction", type=float, default=0.2)
    build.add_argument("--held-out-fraction", type=float, default=0.0)
    build.add_argument("--revision-sha256", default=None)
    build.add_argument("--data-origin", choices=("fixture", "real"), default="fixture")

    fit = sub.add_parser("train", help="fine-tune on the train split and freeze a checkpoint")
    fit.add_argument("--dataset", type=Path, required=True)
    fit.add_argument("--out", type=Path, required=True)
    fit.add_argument("--version", required=True)
    fit.add_argument("--smoke-only", action="store_true", help="force status smoke_only")
    fit.add_argument("--epochs", type=int, default=5)
    fit.add_argument("--batch-size", type=int, default=32)
    fit.add_argument("--lr", type=float, default=1e-4)
    fit.add_argument("--seed", type=int, default=0)
    fit.add_argument("--device", default=None)
    fit.add_argument("--no-pretrained", action="store_true")
    fit.add_argument("--git-commit", default=None)

    verify = sub.add_parser("verify", help="check the checkpoint against its manifest")
    verify.add_argument("--manifest", type=Path, required=True)

    predict = sub.add_parser("predict", help="classify full-frame boxes or ready 224 crops")
    predict.add_argument("--manifest", type=Path, required=True)
    predict.add_argument("--image", type=Path, required=True)
    predict.add_argument("--box", type=float, nargs=4, metavar=("X1", "Y1", "X2", "Y2"))
    predict.add_argument("--device", default="cpu")

    batch = sub.add_parser("predict-batch", help="classify a JSON list of {id, image, box?}")
    batch.add_argument("--manifest", type=Path, required=True)
    batch.add_argument("--input", type=Path, required=True, help="JSON list of items")
    batch.add_argument("--device", default="cpu")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build-dataset":
            snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
            label_map = parse_label_map(json.loads(args.label_map.read_text(encoding="utf-8")))
            manifest = build_dataset(
                snapshot,
                image_root=args.image_root,
                out_dir=args.out,
                label_map=label_map,
                split=SplitConfig(val=args.val_fraction, held_out=args.held_out_fraction),
                group_by=args.group_by,
                snapshot_revision_sha256=args.revision_sha256,
                data_origin=args.data_origin,
            )
            print(
                json.dumps({"manifest_sha256": manifest["manifest_sha256"], **manifest["counts"]})
            )
        elif args.command == "train":
            artifact = train_classifier(
                args.dataset,
                args.out,
                version=args.version,
                smoke_only=args.smoke_only,
                epochs=args.epochs,
                batch_size=args.batch_size,
                lr=args.lr,
                seed=args.seed,
                device=args.device,
                pretrained=not args.no_pretrained,
                git_commit=args.git_commit,
            )
            print(
                json.dumps(
                    {
                        "manifest": str(artifact.path),
                        "sha256": artifact.sha256,
                        "status": artifact.status,
                        "status_reasons": artifact.raw["training"]["status_reasons"],
                    }
                )
            )
        elif args.command == "verify":
            artifact = ClassifierArtifact.load(args.manifest)
            artifact.load_model()  # checksum, then a strict state_dict load
            print(
                json.dumps(
                    {
                        "verified": True,
                        "version": artifact.version,
                        "sha256": artifact.sha256,
                        "status": artifact.status,
                    }
                )
            )
        elif args.command == "predict-batch":
            items = json.loads(args.input.read_text(encoding="utf-8"))
            if not isinstance(items, list):
                raise ValueError("--input must be a JSON list")
            classifier = Classifier.load(args.manifest, device=args.device)
            print(json.dumps(predict_batch(classifier, items)))
        else:
            classifier = Classifier.load(args.manifest, device=args.device)
            with Image.open(args.image) as image:
                crop = (
                    image.convert("RGB")
                    if args.box is None
                    else letterbox_crop(image, tuple(args.box))[0]
                )
            print(json.dumps(classifier.predict([crop])[0].as_dict()))
    except ChecksumMismatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CHECKSUM_MISMATCH
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_BAD_MANIFEST
    except (
        DatasetError,
        TrainingDataError,
        OSError,
        ValueError,
        RuntimeError,
        KeyError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
