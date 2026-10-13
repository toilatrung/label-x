import math

import pytest

from engines.detector import assignment, match_candidates
from engines.interface import FrameKey
from orchestration.detector_engine import CLASSES
from orchestration.routing_policy import RoutingReason, route_candidate

LABELS = {name: str(i + 100) for i, name in enumerate(CLASSES)}


def detection(bbox=(10, 10, 50, 50), label=2):
    scores = [0.01] * 11
    scores[label] = 0.9
    return {
        "bbox_xyxy": list(bbox),
        "class_id": label,
        "class_name": CLASSES[label],
        "confidence": 0.9,
        "class_scores": scores,
    }


def shape(label=102, bbox=(10, 10, 50, 50), ident=1):
    return {"points": list(bbox), "label_id": label, "source": {"kind": "shape", "id": ident}}


def candidates(shapes, detections):
    return match_candidates(
        frame=FrameKey(1, 0),
        width=200,
        height=120,
        shapes=shapes,
        detections=detections,
        classes=CLASSES,
        label_ids=LABELS,
        provenance={"run_id": 7},
        params={},
    )


def test_hungarian_not_greedy():
    assert assignment([[0.9, 0.8], [0.85, 0]]) == {1: 0, 0: 1}
    assert assignment([[], []]) == {}


def test_same_label_no_candidate_conflict_and_missing():
    assert candidates([shape()], [detection()]) == ()
    conflict = candidates([shape(label=103)], [detection()])[0]
    assert conflict.family == "E2" and conflict.evidence["matching_iou"] == 1
    assert conflict.evidence["proposal"]["class_id"] == "102"
    assert conflict.evidence["proposal"]["margin"] == pytest.approx(0.89)
    missing = candidates([], [detection()])[0]
    assert missing.anchor.kind == "detector_box" and missing.family == "E1"


def test_annotation_without_detector_is_human_not_qwen():
    candidate = candidates([shape()], [])[0]
    decision = route_candidate(
        {"engine": "detector", "evidence": candidate.evidence}, crop_valid=True
    )
    assert decision.primary == RoutingReason.DETECTOR_NO_MATCH
    assert not decision.call_qwen and decision.human_review_required


def test_one_to_one_and_deterministic():
    a, b = shape(ident=1), shape(ident=2, bbox=(80, 10, 120, 50))
    d, e = detection(), detection((80, 10, 120, 50), 3)
    assert candidates([a, b], [d, e]) == candidates([b, a], [e, d])


def test_background_wins_is_unknown_not_eleventh_class():
    prediction = detection()
    prediction["class_scores"] = [0.0] * 11
    prediction["class_scores"][2] = 0.35
    prediction["class_scores"][-1] = 0.65
    prediction["confidence"] = 0.35
    candidate = candidates([shape()], [prediction])[0]
    assert candidate.evidence["proposal"]["unknown"]
    decision = route_candidate(
        {"engine": "detector", "evidence": candidate.evidence}, crop_valid=True
    )
    assert decision.primary == RoutingReason.UNKNOWN and decision.call_qwen


def test_prediction_identity_is_run_and_frame_scoped():
    first = candidates([], [detection()])[0]
    second = match_candidates(
        frame=FrameKey(1, 0),
        width=200,
        height=120,
        shapes=[],
        detections=[detection()],
        classes=CLASSES,
        label_ids=LABELS,
        provenance={"run_id": 8},
        params={},
    )[0]
    assert first.anchor.objects[0].id.startswith("7:1:0:")
    assert first.anchor.objects != second.anchor.objects


@pytest.mark.parametrize(
    "field,value",
    [
        ("confidence", math.nan),
        ("class_id", True),
        ("bbox_xyxy", [0, 0, math.inf, 10]),
        ("bbox_xyxy", [-1, 0, 10, 10]),
        ("class_scores", []),
        ("class_name", "wrong"),
    ],
)
def test_invalid_detector_output_fail_closed(field, value):
    invalid = detection()
    invalid[field] = value
    with pytest.raises(ValueError):
        candidates([], [invalid])


@pytest.mark.parametrize("engine", ["schema", "geometry", "duplicate_overlap", "detector"])
def test_four_sources_no_classifier_gate(engine):
    decision = route_candidate(
        {"engine": engine, "classifier": {"status": "running"}}, crop_valid=True
    )
    assert decision.call_qwen and decision.primary == RoutingReason.STRUCTURAL_FINDING
    assert (
        route_candidate({"engine": engine}, crop_valid=False).primary == RoutingReason.INVALID_CROP
    )
    assert (
        route_candidate({"engine": engine}, crop_valid=True, budget_exhausted=True).primary
        == RoutingReason.BUDGET_EXHAUSTED
    )
