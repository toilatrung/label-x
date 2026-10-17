"""Issue #392: exact deterministic boundaries and honest aggregation evidence.

Full cases with missing infrastructure/contract behavior remain planned;
supplemental checks must not be substituted for those matrix bindings.
"""

from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

import pytest
from django.db import connection

from engines.duplicate_overlap import Annotation, run_duplicate_overlap_engine
from engines.geometry import (
    GEOMETRY_NOT_CHECKED_RULE_IDS,
    generate_geometry_candidates,
    run_geometry_engine,
)
from engines.interface import (
    Anchor,
    Candidate,
    EngineConfig,
    EngineInput,
    EngineOutput,
    EngineUnitRef,
    EngineUnitResult,
    FrameKey,
    NotCheckedEngineUnitResult,
    ObjectRef,
    public_status,
)
from engines.schema_taxonomy import (
    RequiredAttribute,
    Taxonomy,
    TaxonomyLabel,
    generate_schema_taxonomy_candidates,
)
from engines.structural import AnnotationAttribute, StructuralAnnotation, StructuralFrame
from orchestration import services
from orchestration.models import CandidateRecord, ShardCommit
from orchestration.services import commit_shard_output, ledger_counts, seed_ledger
from tests.orchestration.helpers import make_run

FRAME = FrameKey(9, 0)


def annotation(**changes):
    return replace(StructuralAnnotation("a", 4, (), 10, 10, 20, 20, 100, 100), **changes)


def engine_input(engine="geometry", *, run_id=7, frames=(FRAME,), shard=0):
    return EngineInput(
        f"p1-{run_id}-{engine}-{shard}",
        run_id,
        11,
        engine,
        "1.0.0",
        EngineConfig(engine, "guideline-v1", True, {}),
        1,
        shard,
        tuple(EngineUnitRef("frame", frame) for frame in frames),
    )


def test_eng_01_taxonomy_version_valid_unknown_and_missing_attribute():
    taxonomy = Taxonomy(
        "taxonomy-v1",
        (
            TaxonomyLabel(
                4,
                "car",
                (RequiredAttribute(8, "motion_state", "A-007", ("moving",)),),
            ),
        ),
    )
    valid = annotation(attributes=(AnnotationAttribute(8, "moving"),))
    assert (
        generate_schema_taxonomy_candidates(
            frame=FRAME,
            annotation=valid,
            taxonomy=taxonomy,
        )
        == ()
    )
    for bad, rule, expected, actual in (
        (annotation(label_id=999), "S-001", "label_id in taxonomy", "label_id=999"),
        (annotation(), "A-007", "required motion_state in [moving]", "<missing>"),
    ):
        (candidate,) = generate_schema_taxonomy_candidates(
            frame=FRAME,
            annotation=bad,
            taxonomy=taxonomy,
        )
        assert candidate.anchor.rule_id == candidate.evidence.rule_id == rule
        assert candidate.anchor.objects == (ObjectRef("cvat_shape", "a"),)
        assert candidate.evidence.taxonomy_version == "taxonomy-v1"
        assert (candidate.evidence.expected, candidate.evidence.actual) == (expected, actual)
        assert candidate.evidence.structural_warning is True
        assert candidate.evidence.is_kpi_error is False
        assert not hasattr(candidate, "state")  # Suspicion, no confirmed defect state.
        with pytest.raises(FrozenInstanceError):
            candidate.family = "confirmed"


def test_eng_02_bounds_area_inverted_and_unchecked_tightness():
    for axis in ("left", "top", "right", "bottom"):
        for distance in (1.999, 2, 2.001):
            changes = {
                "left": {"x1": -distance},
                "top": {"y1": -distance},
                "right": {"x2": 100 + distance},
                "bottom": {"y2": 100 + distance},
            }[axis]
            result = generate_geometry_candidates(frame=FRAME, annotation=annotation(**changes))
            assert bool(result) is (distance > 2), (axis, distance)
            if result:
                assert result[0].evidence.violations == ("outside_image_bounds",)
    for area in (23.999, 24, 24.001):
        result = generate_geometry_candidates(
            frame=FRAME,
            annotation=annotation(x1=0, y1=0, x2=area / 4, y2=4),
        )
        assert bool(result) is (area < 24)
        if result:
            assert result[0].evidence.violations == ("area_below_minimum",)
    for changes, violation in (
        ({"x1": 21}, "x1_not_less_than_x2"),
        ({"y1": 21}, "y1_not_less_than_y2"),
    ):
        (candidate,) = generate_geometry_candidates(frame=FRAME, annotation=annotation(**changes))
        assert violation in candidate.evidence.violations
    output = run_geometry_engine(
        engine_input(),
        {
            FRAME: StructuralFrame(100, 100, (annotation(x1=0, y1=0, x2=100, y2=100),)),
        },
    )
    assert output.candidates == ()
    assert "G-009" in GEOMETRY_NOT_CHECKED_RULE_IDS


def test_eng_03_real_box_iou_boundary_preserves_pair_classes_and_review():
    for iou in (0.849999, 0.85, 0.850001):
        boxes = (Annotation("a", "car", 0, 0, 10, 10), Annotation("b", "truck", 0, 0, iou * 10, 10))
        output = run_duplicate_overlap_engine(engine_input("duplicate"), {FRAME: boxes})
        assert len(output.candidates) == int(iou >= 0.85)
        if output.candidates:
            (candidate,) = output.candidates
            assert candidate.evidence.annotation_ids == ("a", "b")
            assert candidate.evidence.labels == ("car", "truck")
            assert candidate.evidence.iou == pytest.approx(iou)
            assert candidate.evidence.same_label is False
            assert candidate.evidence.structural_warning is True
            assert candidate.evidence.is_kpi_error is False
            assert not hasattr(candidate, "state")


@pytest.mark.django_db(transaction=True)
def test_agg_03_persisted_failed_disabled_unsupported_partial_ledger():
    assert connection.vendor == "postgresql", "AGG integration requires PostgreSQL"
    run = make_run()
    frames = tuple(FrameKey(9, i) for i in range(5))
    inp = engine_input("fake", run_id=run.pk, frames=frames)
    seed_ledger(run.pk, inp.engine, inp.units)
    output = EngineOutput(
        inp.idempotency_key,
        inp.engine,
        inp.engine_version,
        (),
        (
            EngineUnitResult(inp.units[0], "completed", 1),
            EngineUnitResult(inp.units[1], "failed", 3),  # Decode failure remains eligible.
            NotCheckedEngineUnitResult(inp.units[2], "not_checked", 1, "not_applicable"),
            NotCheckedEngineUnitResult(inp.units[3], "not_checked", 1, "disabled"),
            EngineUnitResult(inp.units[4], "failed", 1),
        ),
    )
    assert commit_shard_output(inp, output)
    counts = ledger_counts(run.pk, inp.engine)
    assert (counts.total, counts.eligible, counts.completed, counts.failed) == (5, 4, 1, 2)
    assert (counts.not_checked, counts.excluded, counts.blocked) == (2, 1, 1)
    assert counts.coverage == 0.25
    assert counts.needs_exclusion_warning
    assert str(public_status(counts, finished=True)) == "partial"
    assert CandidateRecord.objects.filter(run=run).count() == 0


@pytest.mark.django_db(transaction=True)
def test_supplemental_transaction_rollback_and_replay_are_immutable():
    """Metadata fault only; does not claim real worker death or S3 fault coverage."""
    assert connection.vendor == "postgresql"
    run = make_run()
    inp = engine_input("fake", run_id=run.pk)
    seed_ledger(run.pk, inp.engine, inp.units)
    candidate = Candidate(
        "fake",
        "1.0.0",
        "E3",
        FRAME,
        Anchor("pair", (ObjectRef("cvat_shape", "a"),), "v1", "DUP-01"),
        {"source": "worker", "iou": 0.9},
    )
    output = EngineOutput(
        inp.idempotency_key,
        "fake",
        "1.0.0",
        (candidate,),
        (EngineUnitResult(inp.units[0], "completed", 1),),
    )
    with patch.object(services, "_apply_unit_results", side_effect=RuntimeError("metadata fault")):
        with pytest.raises(RuntimeError, match="metadata fault"):
            commit_shard_output(inp, output)
    assert not ShardCommit.objects.filter(run=run).exists()
    assert not CandidateRecord.objects.filter(run=run).exists()
    assert ledger_counts(run.pk, "fake").pending == 1
    assert commit_shard_output(inp, output)
    before = list(CandidateRecord.objects.filter(run=run).values())
    changed = replace(output, candidates=(replace(candidate, evidence={"changed": True}),))
    assert commit_shard_output(inp, changed) is False
    assert list(CandidateRecord.objects.filter(run=run).values()) == before
    assert ledger_counts(run.pk, "fake").completed == 1
