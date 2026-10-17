from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

from snapshots.normalization import FrameExport, JobExport, normalize_job, normalize_snapshot

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "normalized-snapshot-v1.json"


def annotations() -> dict[str, Any]:
    return {
        "version": 23,
        "shapes": [
            {
                "id": 91,
                "type": "rectangle",
                "frame": 2,
                "label_id": 4,
                "points": [20.12345649, 40.0, 220.5, 180.9999999],
                "attributes": [{"spec_id": 8, "value": "moving"}],
            },
            {
                "id": 3,
                "type": "polygon",
                "frame": 0,
                "label_id": 4,
                "points": [0, 0, 1, 1, 2, 2],
            },
            {
                "id": 12,
                "type": "rectangle",
                "frame": 0,
                "label_id": 4,
                "points": [10, 20, 110, 120],
                "occluded": True,
                "z_order": 1,
            },
            {
                "id": 13,
                "type": "rectangle",
                "frame": 0,
                "label_id": 4,
                "points": [11, 21, 111, 121],
                "attributes": [{"spec_id": 8, "value": "moving"}],
            },
        ],
        "tracks": [],
    }


def job_export(payload: dict[str, Any] | None = None) -> JobExport:
    return JobExport(
        cvat_job_id=17,
        cvat_task_id=9,
        source_updated_at="2026-10-09T07:05:45Z",
        assignee_cvat_user_id=501,
        annotations=payload or annotations(),
        frames=(
            FrameExport(
                frame_index=2,
                source_frame_id=1002,
                file_name="000002.jpg",
                width=1280,
                height=720,
                media_bytes=b"frame-2",
                media_storage_key="snapshots/source/000002.jpg",
            ),
            FrameExport(
                frame_index=0,
                source_frame_id=1000,
                file_name="000000.jpg",
                width=1280,
                height=720,
                media_bytes=b"frame-0",
                media_storage_key="snapshots/source/000000.jpg",
            ),
        ),
    )


def test_normalized_snapshot_matches_shared_v1_fixture() -> None:
    normalized_job = normalize_job(job_export())
    payload, digest = normalize_snapshot(
        dataset_id=42,
        jobs=[normalized_job],
        taxonomy_version="bdd100k-10-v1",
        guideline_version="bdd100k-guideline-v1",
    )

    assert payload == json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert digest == "c612367cd6b4ac81d0fb8b27fca80d79291fa6d0fc827849b67a8802de1ab278"


def test_two_unchanged_exports_have_identical_job_and_snapshot_sha256() -> None:
    reordered = copy.deepcopy(annotations())
    reordered["version"] = 999
    cast(list[object], reordered["shapes"]).reverse()

    first = normalize_job(job_export())
    second = normalize_job(job_export(reordered))
    first_snapshot = normalize_snapshot(
        dataset_id=42,
        jobs=[first],
        taxonomy_version="bdd100k-10-v1",
        guideline_version="bdd100k-guideline-v1",
    )
    second_snapshot = normalize_snapshot(
        dataset_id=42,
        jobs=[second],
        taxonomy_version="bdd100k-10-v1",
        guideline_version="bdd100k-guideline-v1",
    )

    assert first.sha256 == second.sha256
    assert first_snapshot[1] == second_snapshot[1]
    assert len(first.sha256) == len(first_snapshot[1]) == 64


def test_non_bbox_shapes_are_skipped_and_counted_by_type_including_tracks() -> None:
    payload = annotations()
    cast(list[object], payload["shapes"]).extend(
        [
            {"id": 4, "type": "points", "frame": 0, "label_id": 4},
            {"malformed": True},
        ]
    )
    payload["tracks"] = [
        {
            "id": 8,
            "label_id": 4,
            "shapes": [
                {"type": "ellipse", "frame": 0, "points": [1, 2, 3, 4]},
                {"type": "rectangle", "frame": 0, "points": [1, 2, 3, 4]},
            ],
        }
    ]

    result = normalize_job(job_export(payload))

    assert result.rectangle_count == 4
    assert result.skipped_shape_counts == {
        "ellipse": 1,
        "points": 1,
        "polygon": 1,
        "unknown": 1,
    }


def test_media_change_changes_job_and_snapshot_hash() -> None:
    original = normalize_job(job_export())
    changed_export = job_export()
    changed_frames = list(changed_export.frames)
    changed_frames[0] = FrameExport(
        frame_index=2,
        source_frame_id=1002,
        file_name="000002.jpg",
        width=1280,
        height=720,
        media_bytes=b"changed-frame-2",
        media_storage_key="snapshots/source/000002.jpg",
    )
    changed = normalize_job(
        JobExport(
            cvat_job_id=changed_export.cvat_job_id,
            cvat_task_id=changed_export.cvat_task_id,
            source_updated_at=changed_export.source_updated_at,
            assignee_cvat_user_id=changed_export.assignee_cvat_user_id,
            annotations=changed_export.annotations,
            frames=changed_frames,
        )
    )

    assert original.sha256 != changed.sha256
