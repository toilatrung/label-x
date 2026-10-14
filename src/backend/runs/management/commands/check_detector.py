"""Preflight host files, worker readiness and optional explicit artifact registration."""

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import IntegrityError, transaction

from engines.detector import verify_artifact, worker_request
from runs.models import ModelArtifact


class Command(BaseCommand):
    help = (
        "Verify detector; --register explicitly registers the verified artifact (never a config)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--register", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            manifest = json.loads(Path(settings.DETECTOR_MANIFEST_PATH).read_text(encoding="utf-8"))
            model, mapping = manifest["model"], manifest["class_mapping"]
            health = worker_request("GET", "/health")
            if health.get("status") != "ready":
                raise ValueError("worker not ready")
            expected = {
                "model_artifact__checksum": model["sha256"],
                "model_artifact__version": model["version"],
                "model_artifact__class_mapping_version": mapping["version"],
                "model_artifact__class_mapping": {"classes": mapping["classes"]},
            }
            verify_artifact(health.get("model"), expected)
            if options["register"]:
                with transaction.atomic():
                    artifact, _ = ModelArtifact.objects.get_or_create(
                        name=model["name"],
                        version=model["version"],
                        defaults={
                            "checksum": model["sha256"],
                            "class_mapping_version": mapping["version"],
                            "class_mapping": {"classes": mapping["classes"]},
                            "artifact_key": model.get("artifact_uri", ""),
                        },
                    )
                    if (
                        artifact.checksum != model["sha256"]
                        or artifact.class_mapping_version != mapping["version"]
                        or artifact.class_mapping.get("classes") != mapping["classes"]
                    ):
                        raise ValueError(
                            "existing ModelArtifact does not match; refusing overwrite"
                        )
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, IntegrityError) as exc:
            raise CommandError(
                "Detector preflight failed; check host paths, token, worker and artifact"
            ) from exc
        self.stdout.write(
            self.style.SUCCESS("Detector ready; checkpoint and worker provenance verified")
        )
        self.stdout.write(
            "ConfigVersion.models must reference this registered model (no automatic edits):"
        )
        self.stdout.write(json.dumps({"name": model["name"], "version": model["version"]}))
