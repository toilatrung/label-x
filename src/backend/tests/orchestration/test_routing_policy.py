"""Policy routing Faster R-CNN -> Qwen theo CR-117."""

from __future__ import annotations

import math

import pytest

from orchestration.routing_policy import (
    RoutingInput,
    RoutingPolicy,
    RoutingPolicyError,
    RoutingReason,
    route,
    routing_input_from_candidate,
)

POLICY = RoutingPolicy()
CONFIDENT = {"score": 0.95, "predicted_class_id": 3, "checkpoint_status": "trained"}


def decide(**overrides):
    return route(POLICY, RoutingInput(**{**CONFIDENT, **overrides}))


def detector(**evidence):
    return {
        "engine": "detector",
        "evidence": {"class_id": 3, "class_name": "car", "confidence": 0.95, **evidence},
    }


def test_confident_detector_does_not_call_qwen():
    decision = route(POLICY, routing_input_from_candidate(detector()))
    assert decision.primary is RoutingReason.CLASSIFIER_ONLY
    assert not decision.call_qwen and not decision.human_review_required


def test_score_threshold_is_inclusive():
    assert decide(score=0.85).primary is RoutingReason.CLASSIFIER_ONLY
    assert decide(score=0.8499).primary is RoutingReason.LOW_SCORE


def test_detector_without_top_k_does_not_invent_low_margin():
    decision = route(POLICY, routing_input_from_candidate(detector(confidence=0.95)))
    assert RoutingReason.LOW_MARGIN not in decision.reasons


def test_margin_is_applied_only_when_explicitly_available():
    assert decide(margin=0.15).primary is RoutingReason.CLASSIFIER_ONLY
    assert decide(margin=0.1499).primary is RoutingReason.LOW_MARGIN


def test_conflict_beats_high_score():
    decision = route(POLICY, routing_input_from_candidate(detector(annotated_class_id=4)))
    assert decision.primary is RoutingReason.LABEL_CONFLICT and decision.call_qwen


def test_manual_recheck_triggers_qwen():
    decision = route(POLICY, routing_input_from_candidate(detector(), manual_recheck=True))
    assert decision.primary is RoutingReason.MANUAL_RECHECK and decision.call_qwen


def test_budget_exhausted_blocks_qwen_and_requires_review():
    data = routing_input_from_candidate(detector(annotated_class_id=4), budget_exhausted=True)
    decision = route(POLICY, data)
    assert decision.primary is RoutingReason.BUDGET_EXHAUSTED
    assert RoutingReason.LABEL_CONFLICT in decision.reasons
    assert not decision.call_qwen and decision.human_review_required


@pytest.mark.parametrize(
    "candidate",
    [
        {},
        {"engine": "geometry", "evidence": {}},
        {"engine": "detector", "evidence": None},
        {"engine": "detector", "evidence": {"class_id": "3", "confidence": 0.9}},
        {"engine": "detector", "evidence": {"class_id": 3, "confidence": "0.9"}},
        {"engine": "detector", "evidence": {"class_id": 3, "confidence": math.nan}},
    ],
)
def test_missing_or_invalid_detector_evidence_uses_safe_fallback(candidate):
    decision = route(POLICY, routing_input_from_candidate(candidate))
    assert decision.primary is RoutingReason.CLASSIFIER_UNAVAILABLE
    assert decision.reasons == (RoutingReason.CLASSIFIER_UNAVAILABLE,)
    assert decision.call_qwen


def test_adapter_preserves_valid_zero_class_and_score():
    data = routing_input_from_candidate(detector(class_id=0, confidence=0.0))
    assert data.predicted_class_id == 0 and data.score == 0.0
    assert route(POLICY, data).primary is RoutingReason.LOW_SCORE


def test_wrong_annotation_type_makes_source_unavailable():
    decision = route(POLICY, routing_input_from_candidate(detector(annotated_class_id="3")))
    assert decision.primary is RoutingReason.CLASSIFIER_UNAVAILABLE


def test_policy_record_is_stable_and_temporary():
    record = POLICY.as_record()
    assert record["name"] == "classification-routing-v0"
    assert record["threshold_semantics"] == "routing_temporary"
    assert record == RoutingPolicy().as_record()


@pytest.mark.parametrize(
    "config",
    [
        {"score_threshold": True},
        {"score_threshold": math.nan},
        {"margin_threshold": 2},
        {"unknown": 1},
    ],
)
def test_invalid_policy_config_is_rejected(config):
    with pytest.raises(RoutingPolicyError):
        RoutingPolicy.from_config(config)
