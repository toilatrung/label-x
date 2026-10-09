"""Contract and end-to-end tests for T-028's pure E3 engine."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft4Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT4

from engines.duplicate_overlap import (
    DUPLICATE_OVERLAP_DESCRIPTOR,
    DUPLICATE_OVERLAP_ENGINE_NAME,
    DUPLICATE_OVERLAP_ENGINE_VERSION,
    DUPLICATE_OVERLAP_RULE_ID,
    DUPLICATE_OVERLAP_SRS_REQUIREMENT,
    Annotation,
    MatchingPair,
    generate_duplicate_overlap_candidates,
    run_duplicate_overlap_engine,
)
from engines.interface import EngineConfig, EngineInput, EngineUnitRef, FrameKey

ROOT = Path(__file__).resolve().parents[3]
SPEC = yaml.safe_load((ROOT / "docs/04-api/openapi.yaml").read_text(encoding="utf-8"))
GUIDELINE = yaml.safe_load(
    (ROOT / "src/backend/fixtures/bdd100k_guideline_v1.yaml").read_text(encoding="utf-8")
)


def _annotation(
    annotation_id: str,
    *,
    label: str = "car",
    x1: float = 0,
    y1: float = 0,
    x2: float = 10,
    y2: float = 10,
) -> Annotation:
    return Annotation(annotation_id, label, x1, y1, x2, y2)


def _engine_input(*frames: FrameKey) -> EngineInput:
    return EngineInput(
        idempotency_key="snapshot-11:duplicate:v1:shard-0",
        run_id=7,
        snapshot_id=11,
        engine=DUPLICATE_OVERLAP_ENGINE_NAME,
        engine_version=DUPLICATE_OVERLAP_ENGINE_VERSION,
        config=EngineConfig(
            engine=DUPLICATE_OVERLAP_ENGINE_NAME,
            version="bdd100k-guideline-v1",
            enabled=True,
            params={"iou_threshold": 0.85},
        ),
        seed=123,
        shard_index=0,
        units=tuple(EngineUnitRef(kind="frame", frame=frame) for frame in frames),
    )


def _json_value(value: Any) -> Any:
    """Exercise the actual dataclass -> JSON boundary before schema validation."""
    return json.loads(json.dumps(asdict(value)))


def _validate_contract_schema(name: str, payload: Any) -> None:
    base_uri = "urn:labelx:openapi"
    resource = Resource.from_contents(SPEC, default_specification=DRAFT4)
    registry = Registry().with_resource(base_uri, resource)
    Draft4Validator({"$ref": f"{base_uri}#/components/schemas/{name}"}, registry=registry).validate(
        payload
    )


def test_generates_contract_candidate_with_real_guideline_rule() -> None:
    frame = FrameKey(cvat_task_id=7, frame_number=42)
    candidates = generate_duplicate_overlap_candidates(
        frame=frame,
        annotations=[_annotation("ann-2", label="truck"), _annotation("ann-1")],
        matching_pairs=[MatchingPair("ann-2", "ann-1", 0.85)],
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.engine == "duplicate"
    assert candidate.engine_version == DUPLICATE_OVERLAP_ENGINE_VERSION
    assert candidate.family == "E3"
    assert candidate.frame == frame
    assert candidate.anchor.kind == "annotation_cluster"
    assert [obj.namespace for obj in candidate.anchor.objects] == ["cvat_shape", "cvat_shape"]
    assert [obj.id for obj in candidate.anchor.objects] == ["ann-1", "ann-2"]
    assert candidate.anchor.rule_id == DUPLICATE_OVERLAP_RULE_ID
    assert candidate.evidence.engine == "duplicate"
    assert candidate.evidence.rule_id == DUPLICATE_OVERLAP_RULE_ID
    assert candidate.evidence.srs_requirement == DUPLICATE_OVERLAP_SRS_REQUIREMENT
    assert candidate.evidence.annotation_ids == ("ann-1", "ann-2")
    assert candidate.evidence.labels == ("car", "truck")
    assert not candidate.evidence.same_label
    assert candidate.evidence.structural_warning and not candidate.evidence.is_kpi_error
    assert candidate.evidence.iou == 0.85

    guideline_rule_ids = {rule["id"] for rule in GUIDELINE["rules"]}
    assert candidate.evidence.rule_id in guideline_rule_ids
    assert candidate.evidence.rule_id == "DUP-01"


def test_tie_and_pair_order_produce_the_same_ordered_candidates() -> None:
    frame = FrameKey(cvat_task_id=1, frame_number=1)
    annotations = [_annotation("ann-3"), _annotation("ann-1"), _annotation("ann-2")]
    pairs = [
        MatchingPair("ann-3", "ann-1", 0.90),
        MatchingPair("ann-2", "ann-1", 0.90),
    ]
    forward = generate_duplicate_overlap_candidates(
        frame=frame, annotations=annotations, matching_pairs=pairs
    )
    reversed_pairs = generate_duplicate_overlap_candidates(
        frame=frame,
        annotations=reversed(annotations),
        matching_pairs=reversed(pairs),
    )

    assert forward == reversed_pairs
    assert [candidate.evidence.annotation_ids for candidate in forward] == [
        ("ann-1", "ann-2"),
        ("ann-1", "ann-3"),
    ]


def test_end_to_end_matching_retains_all_edges_and_stable_cluster_anchor() -> None:
    frame = FrameKey(cvat_task_id=1, frame_number=10)
    annotations = [_annotation("ann-3"), _annotation("ann-1"), _annotation("ann-2")]

    output = run_duplicate_overlap_engine(_engine_input(frame), {frame: annotations})

    # A global one-to-one solution could retain only one edge. Pairwise use of
    # T-023 retains all three, so every candidate carries the complete cluster.
    assert len(output.candidates) == 3
    assert {candidate.evidence.annotation_ids for candidate in output.candidates} == {
        ("ann-1", "ann-2"),
        ("ann-1", "ann-3"),
        ("ann-2", "ann-3"),
    }
    assert {
        tuple(obj.id for obj in candidate.anchor.objects) for candidate in output.candidates
    } == {("ann-1", "ann-2", "ann-3")}


def test_real_engine_output_validates_against_contract_and_covers_empty_frame() -> None:
    candidate_frame = FrameKey(cvat_task_id=1, frame_number=10)
    empty_frame = FrameKey(cvat_task_id=1, frame_number=11)
    output = run_duplicate_overlap_engine(
        _engine_input(candidate_frame, empty_frame),
        {
            candidate_frame: [_annotation("ann-1"), _annotation("ann-2", x2=8.5)],
            empty_frame: [
                _annotation("ann-3", x1=0, x2=10),
                _annotation("ann-4", x1=20, x2=30),
            ],
        },
    )

    assert len(output.candidates) == 1
    assert output.candidates[0].evidence.iou == 0.85
    assert [result.unit.frame for result in output.unit_results] == [candidate_frame, empty_frame]
    assert [result.outcome for result in output.unit_results] == ["completed", "completed"]
    assert len(output.unit_results) == len(output.candidates) + 1

    payload = _json_value(output)
    _validate_contract_schema("EngineOutput", payload)


def test_descriptor_matches_engine_contract() -> None:
    payload = _json_value(DUPLICATE_OVERLAP_DESCRIPTOR)
    _validate_contract_schema("EngineDescriptor", payload)
    assert payload["name"] == "duplicate"
    assert payload["unit"] == "frame"
    assert not payload["needs_model"] and not payload["needs_reference"]


@pytest.mark.parametrize("iou", [0.0, 0.849999])
def test_helper_does_not_create_a_candidate_below_threshold(iou: float) -> None:
    assert not generate_duplicate_overlap_candidates(
        frame=FrameKey(cvat_task_id=1, frame_number=1),
        annotations=[_annotation("ann-1"), _annotation("ann-2")],
        matching_pairs=[MatchingPair("ann-1", "ann-2", iou)],
    )
