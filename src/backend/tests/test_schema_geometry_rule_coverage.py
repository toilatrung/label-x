"""Bổ sung AC T-027: test theo từng rule ID, anchor đầy đủ, ledger completed/not_checked."""

from __future__ import annotations

import pytest

from engines.geometry import GEOMETRY_ANCHOR_POLICY_VERSION, run_geometry_engine
from engines.interface import FrameKey, ObjectRef
from engines.schema_taxonomy import (
    SCHEMA_TAXONOMY_ANCHOR_POLICY_VERSION,
    generate_schema_taxonomy_candidates,
    run_schema_taxonomy_engine,
)
from engines.structural import AnnotationAttribute, StructuralFrame
from tests.test_schema_geometry_engines import (
    _annotation,
    _engine_input,
    _taxonomy,
)

FRAME = FrameKey(9, 0)
OK_ATTR = (AnnotationAttribute(spec_id=8, value="moving"),)


def _schema(annotation):
    return generate_schema_taxonomy_candidates(
        frame=FRAME, annotation=annotation, taxonomy=_taxonomy()
    )


def _frames(*annotations):
    return {FRAME: StructuralFrame(width=1280, height=720, annotations=tuple(annotations))}


# --- A-007: thuộc tính bắt buộc ---------------------------------------------------------
@pytest.mark.parametrize(
    ("attributes", "actual"),
    [
        ((), "<missing>"),
        ((AnnotationAttribute(8, ""),), ""),
        ((AnnotationAttribute(8, "flying"),), "flying"),
        ((AnnotationAttribute(8, "moving"), AnnotationAttribute(8, "parked")), "moving, parked"),
    ],
)
def test_a_007_invalid_required_attribute_yields_one_anchored_candidate(attributes, actual):
    (candidate,) = _schema(_annotation(attributes=attributes))
    assert candidate.anchor.rule_id == "A-007"
    assert candidate.anchor.kind == "annotation_rule"
    assert candidate.anchor.objects == (ObjectRef("cvat_shape", "ann-1"),)
    assert candidate.anchor.policy_version == SCHEMA_TAXONOMY_ANCHOR_POLICY_VERSION
    assert candidate.family == "structural" and candidate.frame == FRAME
    assert candidate.evidence.rule_id == "A-007"
    assert candidate.evidence.actual == actual
    assert candidate.evidence.expected.startswith("required motion_state")


def test_a_007_valid_attribute_produces_no_candidate():
    assert _schema(_annotation(attributes=OK_ATTR)) == ()


# --- S-001: nhãn ngoài taxonomy -----------------------------------------------------------
def test_s_001_candidate_has_full_anchor_and_skips_attribute_checks():
    (candidate,) = _schema(_annotation(label_id=999, attributes=()))
    assert candidate.anchor.rule_id == "S-001"
    assert candidate.anchor.objects == (ObjectRef("cvat_shape", "ann-1"),)
    assert candidate.anchor.policy_version == SCHEMA_TAXONOMY_ANCHOR_POLICY_VERSION


# --- G-014 / G-009 ------------------------------------------------------------------------
def test_g_014_single_candidate_lists_all_violations_with_full_anchor():
    inp = _engine_input("geometry", "1.0.0", FRAME)
    bad = _annotation(x1=50, x2=50, y1=0, y2=0)  # x1=x2, y1=y2, diện tích 0
    out = run_geometry_engine(inp, _frames(bad))
    (candidate,) = out.candidates
    assert candidate.anchor.rule_id == "G-014"
    assert candidate.anchor.objects == (ObjectRef("cvat_shape", "ann-1"),)
    assert candidate.anchor.policy_version == GEOMETRY_ANCHOR_POLICY_VERSION
    assert set(candidate.evidence.violations) >= {
        "x1_not_less_than_x2",
        "y1_not_less_than_y2",
        "area_below_minimum",
    }


def test_g_009_boundary_fit_is_never_reported():
    """G-009 giữ Not checked (FR-ENG-03): box khít kém nhưng hợp lệ -> không candidate."""
    inp = _engine_input("geometry", "1.0.0", FRAME)
    loose = _annotation(x1=0, y1=0, x2=1280, y2=720)  # phủ cả ảnh, hợp lệ G-014
    out = run_geometry_engine(inp, _frames(loose))
    assert out.candidates == ()
    assert all(c.anchor.rule_id != "G-009" for c in out.candidates)


# --- Ledger: completed / not_checked cho từng đơn vị -----------------------------------------
def test_ledger_completed_when_frame_has_eligible_annotations_even_without_findings():
    geo = run_geometry_engine(_engine_input("geometry", "1.0.0", FRAME), _frames(_annotation()))
    sch = run_schema_taxonomy_engine(
        _engine_input("schema", "1.0.0", FRAME),
        _frames(_annotation(attributes=OK_ATTR)),
        _taxonomy(),
    )
    for out in (geo, sch):
        assert out.candidates == ()
        assert [(r.outcome, r.attempts) for r in out.unit_results] == [("completed", 1)]


def test_ledger_has_one_row_per_unit_with_mixed_outcomes():
    frames = {
        FrameKey(9, 0): StructuralFrame(1280, 720, (_annotation(),)),
        FrameKey(9, 1): StructuralFrame(1280, 720, (_annotation(outside=True),)),
        FrameKey(9, 2): StructuralFrame(1280, 720, ()),
    }
    inp = _engine_input("geometry", "1.0.0", *frames)
    out = run_geometry_engine(inp, frames)
    assert [r.unit.frame for r in out.unit_results] == list(frames)
    assert [r.outcome for r in out.unit_results] == ["completed", "not_checked", "not_checked"]
    assert [getattr(r, "not_checked_reason", None) for r in out.unit_results][1:] == [
        "not_applicable",
        "not_applicable",
    ]


# --- Tất định & idempotent -----------------------------------------------------------------
def test_engines_are_deterministic_regardless_of_annotation_order():
    a = _annotation(annotation_id="a", x1=5, x2=5)
    b = _annotation(annotation_id="b", label_id=999)
    inp_g, inp_s = (
        _engine_input("geometry", "1.0.0", FRAME),
        _engine_input("schema", "1.0.0", FRAME),
    )
    for first, second in ((a, b), (b, a)):
        assert run_geometry_engine(inp_g, _frames(first, second)) == run_geometry_engine(
            inp_g, _frames(a, b)
        )
        assert run_schema_taxonomy_engine(
            inp_s, _frames(first, second), _taxonomy()
        ) == run_schema_taxonomy_engine(inp_s, _frames(a, b), _taxonomy())
