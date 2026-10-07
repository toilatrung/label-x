import json
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from cvat_adapter.client import CvatReadClient
from cvat_adapter.hashing import canonicalize_job_annotations


class Command(BaseCommand):
    help = "Read one CVAT job and print its stable annotation SHA-256"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("job_id", type=int)

    def handle(self, *args: Any, **options: Any) -> None:
        job_id = int(options["job_id"])
        with CvatReadClient(settings.CVAT_BASE_URL, settings.CVAT_SERVICE_TOKEN) as client:
            annotations = client.get_job_annotations(job_id)
        digest = canonicalize_job_annotations(job_id, annotations)
        self.stdout.write(
            json.dumps(
                {
                    "job_id": digest.job_id,
                    "sha256": digest.sha256,
                    "hash": f"sha256:{digest.sha256}",
                    "rectangles": digest.rectangle_count,
                    "track_rectangles": digest.track_rectangle_count,
                    "ignored_shapes": digest.ignored_shape_count,
                    "ignored_tracks": digest.ignored_track_count,
                },
                sort_keys=True,
            )
        )
