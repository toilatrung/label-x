"""Import an immutable guideline YAML with optional structured taxonomy."""

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from guideline.importing import load_guideline


class Command(BaseCommand):
    help = "Nạp guideline và taxonomy từ tệp YAML (idempotent theo SHA-256)"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("file", type=str)
        parser.add_argument("--actor", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        file_path = Path(options["file"])
        if not file_path.is_file():
            raise CommandError(f"File not found: {file_path}")
        version, skipped = load_guideline(file_path.read_bytes(), str(options["actor"]).strip())
        self.stdout.write(
            self.style.SUCCESS(
                "Guideline already loaded. Skipping."
                if skipped
                else f"Loaded guideline '{version.name}' ({version.version_tag}): "
                f"{version.rules.count()} rules, {version.mappings.count()} mappings."
            )
        )
