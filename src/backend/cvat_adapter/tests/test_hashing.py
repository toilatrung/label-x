import json
from pathlib import Path
from typing import Any, cast

from cvat_adapter.hashing import aggregate_job_hash, canonicalize_job_annotations

FIXTURE = Path(__file__).parent / "fixtures" / "job-17-annotations.json"


def _annotations() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_same_annotations_have_same_hash_despite_order_and_server_version() -> None:
    original = _annotations()
    reordered = _annotations()
    reordered["version"] = 99
    reordered["shapes"].reverse()

    first = canonicalize_job_annotations(17, original)
    second = canonicalize_job_annotations(17, reordered)

    assert first.sha256 == second.sha256
    assert first.canonical_json == second.canonical_json
    assert first.rectangle_count == 2
    assert first.ignored_shape_count == 1
    assert "20.123456" in first.canonical_json


def test_changed_rectangle_changes_hash() -> None:
    original = canonicalize_job_annotations(17, _annotations())
    changed_payload = _annotations()
    changed_payload["shapes"][0]["points"][0] = 21
    changed = canonicalize_job_annotations(17, changed_payload)

    assert original.sha256 != changed.sha256


def test_track_keyframe_and_outside_are_hashed() -> None:
    payload: dict[str, Any] = {
        "shapes": [],
        "tracks": [
            {
                "id": 7,
                "frame": 0,
                "label_id": 4,
                "attributes": [],
                "shapes": [
                    {
                        "type": "rectangle",
                        "frame": 0,
                        "points": [1, 2, 11, 12],
                        "outside": False,
                    },
                    {
                        "type": "rectangle",
                        "frame": 3,
                        "points": [2, 3, 12, 13],
                        "outside": True,
                    },
                ],
            }
        ],
    }
    original = canonicalize_job_annotations(17, payload)
    payload["tracks"][0]["shapes"][1]["outside"] = False
    changed = canonicalize_job_annotations(17, payload)

    assert original.sha256 != changed.sha256
    assert original.track_rectangle_count == 2
    assert original.ignored_track_count == 0


def test_negative_zero_is_normalized() -> None:
    positive = _annotations()
    negative = _annotations()
    positive["shapes"][0]["points"][0] = 0.0
    negative["shapes"][0]["points"][0] = -0.0

    assert (
        canonicalize_job_annotations(17, positive).sha256
        == canonicalize_job_annotations(17, negative).sha256
    )
    assert "-0.0" not in canonicalize_job_annotations(17, negative).canonical_json


def test_aggregate_hash_is_independent_of_job_order() -> None:
    first = canonicalize_job_annotations(17, _annotations())
    second = canonicalize_job_annotations(5, {"shapes": []})

    assert aggregate_job_hash([first, second]) == aggregate_job_hash([second, first])
