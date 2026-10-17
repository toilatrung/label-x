"""Pure deterministic Geometry engine (T-027, FR-ENG-03)."""

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

GEOMETRY_ENGINE_NAME = "geometry"
GEOMETRY_ENGINE_VERSION = "1.0.0"
GEOMETRY_APPLICABILITY_VERSION = "1.0.0"
GEOMETRY_ANCHOR_POLICY_VERSION = "1.0.0"
GEOMETRY_RULE_ID = "G-014"
GEOMETRY_NOT_CHECKED_RULE_IDS = ("G-009",)
GEOMETRY_SRS_REQUIREMENT = "FR-ENG-03"
DEFAULT_BOUNDS_TOLERANCE_PX = 2.0
DEFAULT_MIN_AREA_PX2 = 24.0

GEOMETRY_DESCRIPTOR = EngineDescriptor(
    name=GEOMETRY_ENGINE_NAME,
    version=GEOMETRY_ENGINE_VERSION,
    unit="frame",
    required=True,
    needs_model=False,
    needs_reference=False,
    applicability_version=GEOMETRY_APPLICABILITY_VERSION,
)


@dataclass(frozen=True)
class GeometryEvidence:
    """All deterministic geometry violations for one annotation."""

    engine: str
    rule_id: str
    srs_requirement: str
    annotation_id: str
    bbox: tuple[float, float, float, float]
    image_size: tuple[int, int]
    bounds_tolerance_px: float
    min_area_px2: float
    area_px2: float
    violations: tuple[str, ...]
    expected: str
    actual: str
    structural_warning: bool = True
    is_kpi_error: bool = False


def generate_geometry_candidates(
    *,
    frame: FrameKey,
    annotation: StructuralAnnotation,
    bounds_tolerance_px: float = DEFAULT_BOUNDS_TOLERANCE_PX,
    min_area_px2: float = DEFAULT_MIN_AREA_PX2,
) -> tuple[Candidate, ...]:
    """Return at most one deduplicated G-014 warning for an annotation."""
    _validate_thresholds(bounds_tolerance_px, min_area_px2)
    if annotation.image_width <= 0 or annotation.image_height <= 0:
        raise ValueError("image dimensions must be positive")

    width = annotation.x2 - annotation.x1
    height = annotation.y2 - annotation.y1
    area = max(0.0, width) * max(0.0, height)
    violations: list[str] = []
    if annotation.x1 >= annotation.x2:
        violations.append("x1_not_less_than_x2")
    if annotation.y1 >= annotation.y2:
        violations.append("y1_not_less_than_y2")
    tolerance = bounds_tolerance_px
    if (
        annotation.x1 < -tolerance
        or annotation.y1 < -tolerance
        or annotation.x2 > annotation.image_width + tolerance
        or annotation.y2 > annotation.image_height + tolerance
    ):
        violations.append("outside_image_bounds")
    if area < min_area_px2:
        violations.append("area_below_minimum")
    if not violations:
        return ()

    evidence = GeometryEvidence(
        engine=GEOMETRY_ENGINE_NAME,
        rule_id=GEOMETRY_RULE_ID,
        srs_requirement=GEOMETRY_SRS_REQUIREMENT,
        annotation_id=annotation.annotation_id,
        bbox=annotation.bbox,
        image_size=(annotation.image_width, annotation.image_height),
        bounds_tolerance_px=bounds_tolerance_px,
        min_area_px2=min_area_px2,
        area_px2=area,
        violations=tuple(violations),
        expected=(
            "x1 < x2; y1 < y2; bbox within image ± "
            f"{bounds_tolerance_px:g}px; area >= {min_area_px2:g}px²"
        ),
        actual=(
            f"bbox={annotation.bbox}; image={annotation.image_width}x{annotation.image_height}; "
            f"area={area:g}px²"
        ),
    )
    return (
        Candidate(
            engine=GEOMETRY_ENGINE_NAME,
            engine_version=GEOMETRY_ENGINE_VERSION,
            family="structural",
            frame=frame,
            anchor=Anchor(
                kind="annotation_rule",
                objects=(ObjectRef(namespace="cvat_shape", id=annotation.annotation_id),),
                policy_version=GEOMETRY_ANCHOR_POLICY_VERSION,
                rule_id=GEOMETRY_RULE_ID,
            ),
            evidence=evidence,
        ),
    )


def run_geometry_engine(
    engine_input: EngineInput,
    frames_by_key: Mapping[FrameKey, StructuralFrame],
) -> EngineOutput:
    """Run Geometry and emit one terminal ledger row per frame."""
    _validate_input(engine_input)
    tolerance = _number_param(
        engine_input,
        "bounds_tolerance_px",
        DEFAULT_BOUNDS_TOLERANCE_PX,
    )
    min_area = _number_param(engine_input, "min_area_px2", DEFAULT_MIN_AREA_PX2)
    _validate_thresholds(tolerance, min_area)

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
                generate_geometry_candidates(
                    frame=unit.frame,
                    annotation=annotation,
                    bounds_tolerance_px=tolerance,
                    min_area_px2=min_area,
                )
            )
        unit_results.append(EngineUnitResult(unit=unit, outcome="completed", attempts=1))

    candidates.sort(key=lambda item: (item.frame, item.anchor.rule_id, item.anchor.objects))
    return EngineOutput(
        idempotency_key=engine_input.idempotency_key,
        engine=GEOMETRY_ENGINE_NAME,
        engine_version=GEOMETRY_ENGINE_VERSION,
        candidates=tuple(candidates),
        unit_results=tuple(unit_results),
    )


def _number_param(engine_input: EngineInput, name: str, default: float) -> float:
    value = engine_input.config.params.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be a number")
    return float(value)


def _validate_thresholds(bounds_tolerance_px: float, min_area_px2: float) -> None:
    if bounds_tolerance_px < 0:
        raise ValueError("bounds_tolerance_px must be non-negative")
    if min_area_px2 < 0:
        raise ValueError("min_area_px2 must be non-negative")


def _validate_input(engine_input: EngineInput) -> None:
    if engine_input.engine != GEOMETRY_ENGINE_NAME:
        raise ValueError("engine input is not for the geometry engine")
    if engine_input.engine_version != GEOMETRY_ENGINE_VERSION:
        raise ValueError("engine version does not match the geometry engine")
    if engine_input.config.engine != GEOMETRY_ENGINE_NAME:
        raise ValueError("engine config is not for the geometry engine")
    if not engine_input.config.enabled:
        raise ValueError("disabled engine must not be dispatched to a worker")
