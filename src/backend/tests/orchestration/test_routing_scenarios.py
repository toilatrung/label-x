"""Các nhánh routing đầu-cuối từ evidence Faster R-CNN."""

from orchestration.routing_policy import (
    RoutingPolicy,
    RoutingReason,
    route,
    routing_input_from_candidate,
)


def candidate(**evidence):
    return {
        "engine": "detector",
        "evidence": {
            "match_status": "matched",
            "artifact_verified": True,
            "class_id": 2,
            "class_name": "car",
            "confidence": 0.95,
            **evidence,
        },
    }


def test_branch_confident_detector_only():
    decision = route(RoutingPolicy(), routing_input_from_candidate(candidate()))
    assert decision.primary is RoutingReason.CLASSIFIER_ONLY
    assert not decision.call_qwen


def test_branch_low_detector_confidence_calls_qwen():
    decision = route(RoutingPolicy(), routing_input_from_candidate(candidate(confidence=0.4)))
    assert decision.primary is RoutingReason.LOW_SCORE
    assert decision.call_qwen


def test_branch_label_conflict_calls_qwen():
    decision = route(RoutingPolicy(), routing_input_from_candidate(candidate(annotated_class_id=7)))
    assert decision.primary is RoutingReason.LABEL_CONFLICT
    assert decision.call_qwen


def test_branch_non_detector_candidate_falls_back_to_qwen():
    decision = route(
        RoutingPolicy(),
        routing_input_from_candidate({"engine": "geometry", "evidence": {}}),
    )
    assert decision.primary is RoutingReason.CLASSIFIER_UNAVAILABLE
    assert decision.call_qwen


def test_branch_budget_exhausted_requires_human():
    data = routing_input_from_candidate(candidate(confidence=0.4), budget_exhausted=True)
    decision = route(RoutingPolicy(), data)
    assert decision.primary is RoutingReason.BUDGET_EXHAUSTED
    assert not decision.call_qwen and decision.human_review_required
