"""T-025 registry adapters for T-027 structural engines.

The rule implementations stay pure.  These thin adapters own the database
read required to supply the immutable T-020 snapshot payload to a Celery
runner whose public signature is ``EngineInput -> EngineOutput``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from engines.geometry import GEOMETRY_DESCRIPTOR, run_geometry_engine
from engines.interface import EngineInput, EngineOutput, NotCheckedEngineUnitResult
from engines.schema_taxonomy import (
    SCHEMA_TAXONOMY_DESCRIPTOR,
    RequiredAttribute,
    Taxonomy,
    TaxonomyLabel,
    run_schema_taxonomy_engine,
)
from engines.structural import ordered_frame_units, structural_frames_from_snapshot
from orchestration.registry import EngineRegistry, registry
from snapshots.models import Snapshot


def run_registered_geometry_engine(engine_input: EngineInput) -> EngineOutput:
    """Load the immutable snapshot, then call the pure Geometry engine."""
    snapshot = _snapshot(engine_input.snapshot_id)
    return run_geometry_engine(
        engine_input,
        structural_frames_from_snapshot(snapshot.normalized_json),
    )


def run_registered_schema_taxonomy_engine(engine_input: EngineInput) -> EngineOutput:
    """Load snapshot/taxonomy inputs, then call the pure Schema engine."""
    snapshot = _snapshot(engine_input.snapshot_id)
    if not isinstance(engine_input.config.params.get("taxonomy"), Mapping):
        return EngineOutput(
            idempotency_key=engine_input.idempotency_key,
            engine=engine_input.engine,
            engine_version=engine_input.engine_version,
            candidates=(),
            unit_results=tuple(
                NotCheckedEngineUnitResult(
                    unit=unit,
                    outcome="not_checked",
                    attempts=1,
                    not_checked_reason="no_reference",
                )
                for unit in ordered_frame_units(engine_input.units)
            ),
        )
    taxonomy = taxonomy_from_params(
        engine_input.config.params,
        expected_version=snapshot.taxonomy_version,
    )
    return run_schema_taxonomy_engine(
        engine_input,
        structural_frames_from_snapshot(snapshot.normalized_json),
        taxonomy,
    )


def taxonomy_from_params(params: Mapping[str, Any], *, expected_version: str) -> Taxonomy:
    """Parse the versioned taxonomy embedded in Schema engine config."""
    raw = params.get("taxonomy")
    if not isinstance(raw, Mapping):
        raise ValueError("schema engine config must contain a taxonomy object")
    version = raw.get("version")
    if version != expected_version:
        raise ValueError("schema engine taxonomy version does not match the snapshot")
    raw_labels = raw.get("labels")
    if not isinstance(raw_labels, list) or not raw_labels:
        raise ValueError("schema engine taxonomy labels must be a non-empty list")

    labels: list[TaxonomyLabel] = []
    for raw_label in raw_labels:
        if not isinstance(raw_label, Mapping):
            raise ValueError("taxonomy label must be an object")
        raw_attributes = raw_label.get("required_attributes", [])
        if not isinstance(raw_attributes, list):
            raise ValueError("required_attributes must be a list")
        attributes = tuple(
            RequiredAttribute(
                spec_id=_required_int(attribute, "spec_id"),
                name=_required_text(attribute, "name"),
                rule_id=_required_text(attribute, "rule_id"),
                allowed_values=_allowed_values(attribute),
            )
            for attribute in raw_attributes
            if isinstance(attribute, Mapping)
        )
        if len(attributes) != len(raw_attributes):
            raise ValueError("required attribute must be an object")
        labels.append(
            TaxonomyLabel(
                label_id=_required_int(raw_label, "label_id"),
                name=_required_text(raw_label, "name"),
                required_attributes=attributes,
            )
        )
    return Taxonomy(version=expected_version, labels=tuple(labels))


def register_structural_engines(target: EngineRegistry = registry) -> None:
    """Register once; Django may call ``ready`` more than once in tooling."""
    for descriptor, runner in (
        (SCHEMA_TAXONOMY_DESCRIPTOR, run_registered_schema_taxonomy_engine),
        (GEOMETRY_DESCRIPTOR, run_registered_geometry_engine),
    ):
        try:
            existing = target.descriptor(descriptor.name, descriptor.version)
        except LookupError:
            target.register(descriptor, runner)
        else:
            if existing != descriptor:
                raise ValueError(
                    f"engine {descriptor.name}@{descriptor.version} has a conflicting descriptor"
                )


def _snapshot(snapshot_id: int) -> Snapshot:
    try:
        return Snapshot.objects.only("id", "taxonomy_version", "normalized_json").get(
            pk=snapshot_id,
            status=Snapshot.Status.LOCKED,
        )
    except Snapshot.DoesNotExist as exc:
        raise ValueError("engine snapshot must exist and be locked") from exc


def _required_int(payload: Mapping[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"taxonomy {field} must be an integer")
    return value


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"taxonomy {field} must be a non-empty string")
    return value


def _allowed_values(payload: Mapping[str, Any]) -> tuple[str, ...]:
    values = payload.get("allowed_values", [])
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ValueError("taxonomy allowed_values must be a list of strings")
    return tuple(values)
