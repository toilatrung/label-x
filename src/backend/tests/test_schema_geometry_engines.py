"""Contract and rule tests for T-027's deterministic structural engines."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest
import yaml
from django.contrib.auth.models import User
from jsonschema import Draft4Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT4

from engines.geometry import (
    GEOMETRY_DESCRIPTOR,
    GEOMETRY_ENGINE_NAME,
    GEOMETRY_ENGINE_VERSION,
    GEOMETRY_NOT_CHECKED_RULE_IDS,
    GEOMETRY_RULE_ID,
    generate_geometry_candidates,
    run_geometry_engine,
)
from engines.interface import EngineConfig, EngineInput, EngineUnitRef, FrameKey
from engines.registration import (
    register_structural_engines,
    run_registered_geometry_engine,
    run_registered_schema_taxonomy_engine,
    taxonomy_from_params,
)
from engines.schema_taxonomy import (
    SCHEMA_TAXONOMY_DESCRIPTOR,
    SCHEMA_TAXONOMY_ENGINE_NAME,
    SCHEMA_TAXONOMY_ENGINE_VERSION,
    UNKNOWN_LABEL_RULE_ID,
    RequiredAttribute,
    Taxonomy,
    TaxonomyLabel,
    generate_schema_taxonomy_candidates,
    run_schema_taxonomy_engine,
)
from engines.structural import (
    StructuralAnnotation,
    StructuralFrame,
    structural_frames_from_snapshot,
)
from orchestration.registry import EngineRegistry
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot

ROOT = Path(__file__).resolve().parents[3]
SPEC = yaml.safe_load((ROOT / "docs/04-api/openapi.yaml").read_text(encoding="utf-8"))
SNAPSHOT = json.loads(
    (ROOT / "src/backend/fixtures/normalized-snapshot-v1.json").read_text(encoding="utf-8")
)


def _taxonomy() -> Taxonomy:
    return Taxonomy(
        version="bdd100k-10-v1",
        labels=(
            TaxonomyLabel(
                label_id=4,
                name="car",
                required_attributes=(
                    RequiredAttribute(
                        spec_id=8,
                        name="motion_state",
                        rule_id="A-007",
                        allowed_values=("moving", "parked", "stopped"),
                    ),
                ),
            ),
        ),
    )


def _engine_input(engine: str, version: str, *frames: FrameKey) -> EngineInput:
    return EngineInput(
        idempotency_key=f"snapshot-11:{engine}:v1:shard-0",
        run_id=7,
        snapshot_id=11,
        engine=engine,
        engine_version=version,
        config=EngineConfig(
            engine=engine,
            version="bdd100k-guideline-v1",
            enabled=True,
            params={},
        ),
        seed=123,
        shard_index=0,
        units=tuple(EngineUnitRef(kind="frame", frame=frame) for frame in frames),
    )


def _annotation(**changes: Any) -> StructuralAnnotation:
    base = StructuralAnnotation(
        annotation_id="ann-1",
        label_id=4,
        attributes=(),
        x1=10,
        y1=20,
        x2=110,
        y2=120,
        image_width=1280,
        image_height=720,
    )
    return replace(base, **changes)


def _json_value(value: Any) -> Any:
    return json.loads(json.dumps(asdict(value)))


def _validate_contract_schema(name: str, payload: Any) -> None:
    base_uri = "urn:labelx:openapi"
    resource = Resource.from_contents(SPEC, default_specification=DRAFT4)
    registry = Registry().with_resource(base_uri, resource)
    Draft4Validator({"$ref": f"{base_uri}#/components/schemas/{name}"}, registry=registry).validate(
        payload
    )


def test_t020_snapshot_fixture_drives_schema_rule_a_007_deterministically() -> None:
    frames = structural_frames_from_snapshot(SNAPSHOT)
    frame_keys = tuple(reversed(tuple(frames)))

    output = run_schema_taxonomy_engine(
        _engine_input(
            SCHEMA_TAXONOMY_ENGINE_NAME,
            SCHEMA_TAXONOMY_ENGINE_VERSION,
            *frame_keys,
        ),
        frames,
        _taxonomy(),
    )

    assert [candidate.anchor.rule_id for candidate in output.candidates] == ["A-007"]
    evidence = output.candidates[0].evidence
    assert evidence.expected == "required motion_state in [moving, parked, stopped]"
    assert evidence.actual == "<missing>"
    assert evidence.taxonomy_version == SNAPSHOT["taxonomy_version"]
    assert [result.outcome for result in output.unit_results] == ["completed", "completed"]
    assert [result.unit.frame.frame_number for result in output.unit_results] == [0, 2]
    _validate_contract_schema("EngineOutput", _json_value(output))


def test_schema_rule_s_001_reports_unknown_taxonomy_label() -> None:
    candidate = generate_schema_taxonomy_candidates(
        frame=FrameKey(9, 0),
        annotation=_annotation(label_id=999),
        taxonomy=_taxonomy(),
    )[0]

    assert candidate.anchor.kind == "annotation_rule"
    assert candidate.anchor.rule_id == UNKNOWN_LABEL_RULE_ID == "S-001"
    assert candidate.evidence.check == "taxonomy_label"
    assert candidate.evidence.expected == "label_id in taxonomy"
    assert candidate.evidence.actual == "label_id=999"


@pytest.mark.parametrize(
    ("changes", "violation"),
    [
        ({"x1": 10, "x2": 10}, "x1_not_less_than_x2"),
        ({"y1": 20, "y2": 20}, "y1_not_less_than_y2"),
        ({"x1": -2.01}, "outside_image_bounds"),
        ({"x1": 0, "y1": 0, "x2": 4, "y2": 5.99}, "area_below_minimum"),
    ],
)
def test_geometry_rule_g_014_has_evidence_for_each_check(
    changes: dict[str, Any], violation: str
) -> None:
    candidates = generate_geometry_candidates(
        frame=FrameKey(9, 0),
        annotation=_annotation(**changes),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.anchor.kind == "annotation_rule"
    assert candidate.anchor.rule_id == GEOMETRY_RULE_ID == "G-014"
    assert violation in candidate.evidence.violations
    assert candidate.evidence.expected and candidate.evidence.actual


def test_geometry_accepts_exact_bounds_tolerance_and_minimum_area() -> None:
    assert not generate_geometry_candidates(
        frame=FrameKey(9, 0),
        annotation=_annotation(x1=-2, y1=0, x2=2, y2=6),
    )
    assert GEOMETRY_NOT_CHECKED_RULE_IDS == ("G-009",)


@pytest.mark.parametrize(
    ("engine", "version", "runner"),
    [
        (SCHEMA_TAXONOMY_ENGINE_NAME, SCHEMA_TAXONOMY_ENGINE_VERSION, "schema"),
        (GEOMETRY_ENGINE_NAME, GEOMETRY_ENGINE_VERSION, "geometry"),
    ],
)
def test_outside_shape_is_not_applicable_in_each_engine_ledger(
    engine: str, version: str, runner: str
) -> None:
    frame_key = FrameKey(9, 0)
    frames = {
        frame_key: StructuralFrame(
            width=1280,
            height=720,
            annotations=(_annotation(outside=True),),
        )
    }
    engine_input = _engine_input(engine, version, frame_key)

    if runner == "schema":
        output = run_schema_taxonomy_engine(engine_input, frames, _taxonomy())
    else:
        output = run_geometry_engine(engine_input, frames)

    assert not output.candidates
    assert output.unit_results[0].outcome == "not_checked"
    assert output.unit_results[0].not_checked_reason == "not_applicable"
    _validate_contract_schema("EngineOutput", _json_value(output))


def test_geometry_fixture_output_and_descriptors_match_public_contract() -> None:
    frames = structural_frames_from_snapshot(SNAPSHOT)
    frame_keys = tuple(frames)
    output = run_geometry_engine(
        _engine_input(GEOMETRY_ENGINE_NAME, GEOMETRY_ENGINE_VERSION, *frame_keys),
        frames,
    )

    assert not output.candidates
    assert [result.outcome for result in output.unit_results] == ["completed", "completed"]
    _validate_contract_schema("EngineOutput", _json_value(output))
    for descriptor in (SCHEMA_TAXONOMY_DESCRIPTOR, GEOMETRY_DESCRIPTOR):
        _validate_contract_schema("EngineDescriptor", _json_value(descriptor))
        assert descriptor.unit == "frame"
        assert not descriptor.needs_model and not descriptor.needs_reference


def test_frame_unit_must_resolve_to_snapshot_frame() -> None:
    frame = FrameKey(9, 999)
    with pytest.raises(ValueError, match="missing snapshot frame"):
        run_geometry_engine(
            _engine_input(GEOMETRY_ENGINE_NAME, GEOMETRY_ENGINE_VERSION, frame),
            {},
        )


def test_t025_registry_receives_both_structural_engines() -> None:
    target = EngineRegistry()
    register_structural_engines(target)
    register_structural_engines(target)

    assert [descriptor.name for descriptor in target.descriptors()] == ["geometry", "schema"]
    assert callable(target.runner(GEOMETRY_ENGINE_NAME, GEOMETRY_ENGINE_VERSION))
    assert callable(target.runner(SCHEMA_TAXONOMY_ENGINE_NAME, SCHEMA_TAXONOMY_ENGINE_VERSION))


def test_taxonomy_config_must_match_snapshot_version() -> None:
    raw = {
        "taxonomy": {
            "version": "bdd100k-10-v1",
            "labels": [
                {
                    "label_id": 4,
                    "name": "car",
                    "required_attributes": [
                        {
                            "spec_id": 8,
                            "name": "motion_state",
                            "rule_id": "A-007",
                            "allowed_values": ["moving", "parked", "stopped"],
                        }
                    ],
                }
            ],
        }
    }
    assert taxonomy_from_params(raw, expected_version="bdd100k-10-v1") == _taxonomy()
    with pytest.raises(ValueError, match="does not match"):
        taxonomy_from_params(raw, expected_version="other-version")


@pytest.mark.django_db
def test_registered_t025_runners_load_locked_t020_snapshot() -> None:
    user = User.objects.create_user("t027-runner", password="safe-test-password")
    annotations = {
        "shapes": [
            {
                "id": 12,
                "type": "rectangle",
                "frame": 0,
                "label_id": 4,
                "points": [10.0, 20.0, 110.0, 120.0],
                "attributes": [],
                "occluded": True,
            },
            {
                "id": 91,
                "type": "rectangle",
                "frame": 2,
                "label_id": 4,
                "points": [20.123456, 40.0, 220.5, 181.0],
                "attributes": [{"spec_id": 8, "value": "moving"}],
            },
        ],
        "tracks": [],
    }
    frames_export = tuple(
        FrameExport(
            frame_index=index,
            source_frame_id=1000 + index,
            file_name=f"00000{index}.jpg",
            width=1280,
            height=720,
            media_bytes=f"frame-{index}".encode(),
            media_storage_key=f"snapshots/t027/{index}.jpg",
        )
        for index in (0, 2)
    )
    snapshot = create_locked_snapshot(
        dataset_id=42,
        created_by=user,
        jobs=(
            JobExport(
                cvat_job_id=17,
                cvat_task_id=9,
                source_updated_at="2026-10-09T07:05:45Z",
                annotations=annotations,
                frames=frames_export,
                assignee_cvat_user_id=501,
            ),
        ),
        taxonomy_version="bdd100k-10-v1",
        guideline_version="bdd100k-guideline-v1",
    )
    frames = tuple(structural_frames_from_snapshot(snapshot.normalized_json))

    geometry_input = replace(
        _engine_input(GEOMETRY_ENGINE_NAME, GEOMETRY_ENGINE_VERSION, *frames),
        snapshot_id=snapshot.pk,
    )
    geometry_output = run_registered_geometry_engine(geometry_input)
    assert not geometry_output.candidates
    assert all(result.outcome == "completed" for result in geometry_output.unit_results)

    schema_without_taxonomy = replace(
        _engine_input(
            SCHEMA_TAXONOMY_ENGINE_NAME,
            SCHEMA_TAXONOMY_ENGINE_VERSION,
            *frames,
        ),
        snapshot_id=snapshot.pk,
    )
    not_checked_output = run_registered_schema_taxonomy_engine(schema_without_taxonomy)
    assert all(result.outcome == "not_checked" for result in not_checked_output.unit_results)
    # Thiếu taxonomy = thiếu dữ liệu tham chiếu: giữ trong mẫu số, không được báo "sạch".
    assert all(
        result.not_checked_reason == "no_reference" for result in not_checked_output.unit_results
    )

    taxonomy_payload = {
        "taxonomy": {
            "version": "bdd100k-10-v1",
            "labels": [
                {
                    "label_id": 4,
                    "name": "car",
                    "required_attributes": [
                        {
                            "spec_id": 8,
                            "name": "motion_state",
                            "rule_id": "A-007",
                            "allowed_values": ["moving", "parked", "stopped"],
                        }
                    ],
                }
            ],
        }
    }
    schema_input = _engine_input(
        SCHEMA_TAXONOMY_ENGINE_NAME,
        SCHEMA_TAXONOMY_ENGINE_VERSION,
        *frames,
    )
    schema_input = replace(
        schema_input,
        snapshot_id=snapshot.pk,
        config=replace(schema_input.config, params=taxonomy_payload),
    )
    schema_output = run_registered_schema_taxonomy_engine(schema_input)
    assert [candidate.anchor.rule_id for candidate in schema_output.candidates] == ["A-007"]
