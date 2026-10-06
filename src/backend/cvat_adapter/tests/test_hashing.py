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


def test_aggregate_hash_is_independent_of_job_order() -> None:
    first = canonicalize_job_annotations(17, _annotations())
    second = canonicalize_job_annotations(5, {"shapes": []})

    assert aggregate_job_hash([first, second]) == aggregate_job_hash([second, first])
