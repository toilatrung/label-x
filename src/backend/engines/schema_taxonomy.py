"""Pure deterministic Schema/Taxonomy engine (T-027, FR-ENG-02)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from engines.interface import (
    Anchor,
    Candidate,
    EngineDescriptor,
    EngineInput,
    EngineOutput,
    EngineUnitResult,
    FrameKey,
    NotCheckedEngineUnitResult,
    ObjectRef,
)
from engines.structural import (
    StructuralAnnotation,
    StructuralFrame,
    frame_for_unit,
    ordered_frame_units,
)

SCHEMA_TAXONOMY_ENGINE_NAME = "schema"
SCHEMA_TAXONOMY_ENGINE_VERSION = "1.0.0"
SCHEMA_TAXONOMY_APPLICABILITY_VERSION = "1.0.0"
SCHEMA_TAXONOMY_ANCHOR_POLICY_VERSION = "1.0.0"
SCHEMA_TAXONOMY_SRS_REQUIREMENT = "FR-ENG-02"
UNKNOWN_LABEL_RULE_ID = "S-001"

SCHEMA_TAXONOMY_DESCRIPTOR = EngineDescriptor(
    name=SCHEMA_TAXONOMY_ENGINE_NAME,
    version=SCHEMA_TAXONOMY_ENGINE_VERSION,
    unit="frame",
    required=True,
    needs_model=False,
    needs_reference=False,
    applicability_version=SCHEMA_TAXONOMY_APPLICABILITY_VERSION,
)


@dataclass(frozen=True, order=True)
class RequiredAttribute:
    """A required attribute and its versioned structural rule."""

    spec_id: int
    name: str
    rule_id: str
    allowed_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaxonomyLabel:
    """A label valid in the selected taxonomy version."""

    label_id: int
    name: str
    required_attributes: tuple[RequiredAttribute, ...] = ()


@dataclass(frozen=True)
class Taxonomy:
    """Minimal immutable taxonomy contract required by the engine."""

    version: str
    labels: tuple[TaxonomyLabel, ...]


@dataclass(frozen=True)
class SchemaTaxonomyEvidence:
    """Expected/actual evidence required by FR-ENG-02."""

    engine: str
    rule_id: str
    srs_requirement: str
    annotation_id: str
    taxonomy_version: str
    check: str
    expected: str
    actual: str
    structural_warning: bool = True
    is_kpi_error: bool = False


def generate_schema_taxonomy_candidates(
    *,
    frame: FrameKey,
    annotation: StructuralAnnotation,
    taxonomy: Taxonomy,
) -> tuple[Candidate, ...]:
    """Return stable structural candidates for one eligible annotation."""
    labels = _labels_by_id(taxonomy)
    label = labels.get(annotation.label_id)
    if label is None:
        return (
            _candidate(
                frame=frame,
                annotation=annotation,
                taxonomy=taxonomy,
                rule_id=UNKNOWN_LABEL_RULE_ID,
                check="taxonomy_label",
                expected="label_id in taxonomy",
                actual=f"label_id={annotation.label_id}",
            ),
        )

    attributes_by_spec: dict[int, list[str]] = {}
    for attribute in annotation.attributes:
        attributes_by_spec.setdefault(attribute.spec_id, []).append(attribute.value)

    candidates: list[Candidate] = []
    for requirement in sorted(label.required_attributes):
        values = attributes_by_spec.get(requirement.spec_id, [])
        valid = len(values) == 1 and bool(values[0])
        if requirement.allowed_values:
            valid = valid and values[0] in requirement.allowed_values
        if valid:
            continue
        expected = f"required {requirement.name}"
        if requirement.allowed_values:
            expected += " in [" + ", ".join(sorted(requirement.allowed_values)) + "]"
        candidates.append(
            _candidate(
                frame=frame,
                annotation=annotation,
                taxonomy=taxonomy,
                rule_id=requirement.rule_id,
                check="required_attribute",
                expected=expected,
                actual="<missing>" if not values else ", ".join(values),
            )
        )
    return tuple(candidates)


def run_schema_taxonomy_engine(
    engine_input: EngineInput,
    frames_by_key: Mapping[FrameKey, StructuralFrame],
    taxonomy: Taxonomy,
) -> EngineOutput:
    """Run Schema/Taxonomy and emit one terminal ledger row per frame."""
    _validate_input(engine_input)
    _labels_by_id(taxonomy)

    candidates: list[Candidate] = []
    unit_results: list[EngineUnitResult] = []
    for unit in ordered_frame_units(engine_input.units):
        frame = frame_for_unit(unit, frames_by_key)
        eligible_annotations = tuple(
            annotation for annotation in frame.annotations if not annotation.outside
        )
        if not eligible_annotations:
            unit_results.append(
                NotCheckedEngineUnitResult(
                    unit=unit,
                    outcome="not_checked",
                    attempts=1,
                    not_checked_reason="not_applicable",
                )
            )
            continue
        for annotation in eligible_annotations:
            candidates.extend(
                generate_schema_taxonomy_candidates(
                    frame=unit.frame,
                    annotation=annotation,
                    taxonomy=taxonomy,
                )
            )
        unit_results.append(EngineUnitResult(unit=unit, outcome="completed", attempts=1))

    candidates.sort(key=lambda item: (item.frame, item.anchor.rule_id, item.anchor.objects))
    return EngineOutput(
        idempotency_key=engine_input.idempotency_key,
        engine=SCHEMA_TAXONOMY_ENGINE_NAME,
        engine_version=SCHEMA_TAXONOMY_ENGINE_VERSION,
        candidates=tuple(candidates),
        unit_results=tuple(unit_results),
    )


def _candidate(
    *,
    frame: FrameKey,
    annotation: StructuralAnnotation,
    taxonomy: Taxonomy,
    rule_id: str,
    check: str,
    expected: str,
    actual: str,
) -> Candidate:
    return Candidate(
        engine=SCHEMA_TAXONOMY_ENGINE_NAME,
        engine_version=SCHEMA_TAXONOMY_ENGINE_VERSION,
        family="structural",
        frame=frame,
        anchor=Anchor(
            kind="annotation_rule",
            objects=(ObjectRef(namespace="cvat_shape", id=annotation.annotation_id),),
            policy_version=SCHEMA_TAXONOMY_ANCHOR_POLICY_VERSION,
            rule_id=rule_id,
        ),
        evidence=SchemaTaxonomyEvidence(
            engine=SCHEMA_TAXONOMY_ENGINE_NAME,
            rule_id=rule_id,
            srs_requirement=SCHEMA_TAXONOMY_SRS_REQUIREMENT,
            annotation_id=annotation.annotation_id,
            taxonomy_version=taxonomy.version,
            check=check,
            expected=expected,
            actual=actual,
        ),
    )


def _labels_by_id(taxonomy: Taxonomy) -> dict[int, TaxonomyLabel]:
    labels = {label.label_id: label for label in taxonomy.labels}
    if len(labels) != len(taxonomy.labels):
        raise ValueError("taxonomy label_id must be unique")
    for label in taxonomy.labels:
        spec_ids = [attribute.spec_id for attribute in label.required_attributes]
        rule_ids = [attribute.rule_id for attribute in label.required_attributes]
        if len(set(spec_ids)) != len(spec_ids):
            raise ValueError("required attribute spec_id must be unique per label")
        if len(set(rule_ids)) != len(rule_ids):
            raise ValueError("required attribute rule_id must be unique per label")
    return labels


def _validate_input(engine_input: EngineInput) -> None:
    if engine_input.engine != SCHEMA_TAXONOMY_ENGINE_NAME:
        raise ValueError("engine input is not for the schema engine")
    if engine_input.engine_version != SCHEMA_TAXONOMY_ENGINE_VERSION:
        raise ValueError("engine version does not match the schema engine")
    if engine_input.config.engine != SCHEMA_TAXONOMY_ENGINE_NAME:
        raise ValueError("engine config is not for the schema engine")
    if not engine_input.config.enabled:
        raise ValueError("disabled engine must not be dispatched to a worker")
