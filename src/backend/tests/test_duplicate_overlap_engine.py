"""Fixture tests for T-028's pure E3 candidate engine."""

from __future__ import annotations

import pytest

from engines.duplicate_overlap import (
    DUPLICATE_OVERLAP_RULE_ID,
    Annotation,
    MatchingPair,
    generate_duplicate_overlap_candidates,
)


def _annotations() -> tuple[Annotation, ...]:
    return (
        Annotation("ann-2", "truck"),
        Annotation("ann-1", "car"),
        Annotation("ann-3", "car"),
        Annotation("ann-4", "person"),
    )


def test_generates_e3_with_reviewer_evidence_and_no_kpi_error() -> None:
    candidates = generate_duplicate_overlap_candidates(
        frame_key="task-7:42",
        annotations=_annotations(),
        matching_pairs=[MatchingPair("ann-2", "ann-1", 0.85)],
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.family == "E3"
    assert candidate.anchor_annotation_id == "ann-1"
    assert candidate.structural_warning and not candidate.is_kpi_error
    assert candidate.evidence.rule_id == DUPLICATE_OVERLAP_RULE_ID
    assert candidate.evidence.annotation_ids == ("ann-1", "ann-2")
    assert candidate.evidence.labels == ("car", "truck")
    assert not candidate.evidence.same_label
    assert candidate.evidence.iou == 0.85


def test_tie_and_pair_order_produce_the_same_ordered_candidates() -> None:
    pairs = [
        MatchingPair("ann-3", "ann-1", 0.90),
        MatchingPair("ann-2", "ann-1", 0.90),
    ]
    forward = generate_duplicate_overlap_candidates(
        frame_key="f-1", annotations=_annotations(), matching_pairs=pairs
    )
    reversed_pairs = generate_duplicate_overlap_candidates(
        frame_key="f-1", annotations=reversed(_annotations()), matching_pairs=reversed(pairs)
    )

    assert forward == reversed_pairs
    assert [candidate.evidence.annotation_ids for candidate in forward] == [
        ("ann-1", "ann-2"),
        ("ann-1", "ann-3"),
    ]


def test_cluster_has_a_single_stable_anchor_and_full_cluster_evidence() -> None:
    candidates = generate_duplicate_overlap_candidates(
        frame_key="f-1",
        annotations=_annotations(),
        matching_pairs=[
            MatchingPair("ann-2", "ann-1", 0.91),
            MatchingPair("ann-3", "ann-2", 0.86),
            MatchingPair("ann-4", "ann-3", 0.84),
        ],
    )

    assert len(candidates) == 2
    assert {candidate.anchor_annotation_id for candidate in candidates} == {"ann-1"}
    assert {candidate.evidence.cluster_annotation_ids for candidate in candidates} == {
        ("ann-1", "ann-2", "ann-3")
    }


@pytest.mark.parametrize("iou", [0.0, 0.849999])
def test_does_not_create_a_candidate_below_threshold(iou: float) -> None:
    assert not generate_duplicate_overlap_candidates(
        frame_key="f-1",
        annotations=_annotations(),
        matching_pairs=[MatchingPair("ann-1", "ann-2", iou)],
    )
