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
CONFIDENT = {
    "score": 0.95,
    "predicted_class_id": 3,
    "source_trusted": True,
    "checkpoint_status": "verified",
}


def decide(**overrides):
    return route(POLICY, RoutingInput(**{**CONFIDENT, **overrides}))


def detector(**evidence):
    return {
        "engine": "detector",
        "evidence": {
            "match_status": "matched",
            "artifact_verified": True,
            "class_id": 3,
            "class_name": "car",
            "confidence": 0.95,
            **evidence,
        },
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


def test_margin_is_ignored_in_v0_so_low_margin_never_triggers():
    # Không có phân bố đầy đủ (kể cả background) ⇒ low_margin bị vô hiệu dù có margin.
    for margin in (None, 0.0, 0.1499, 0.9):
        decision = decide(margin=margin)
        assert decision.primary is RoutingReason.CLASSIFIER_ONLY
        assert RoutingReason.LOW_MARGIN not in decision.reasons


def test_untrusted_artifact_is_never_detector_only():
    decision = route(POLICY, routing_input_from_candidate(detector(artifact_verified=False)))
    assert decision.primary is RoutingReason.CLASSIFIER_UNTRUSTED
    assert decision.call_qwen and decision.human_review_required
    assert decision.checkpoint_status == "unverified"
    missing = detector()
    del missing["evidence"]["artifact_verified"]
    assert route(POLICY, routing_input_from_candidate(missing)).primary is (
        RoutingReason.CLASSIFIER_UNTRUSTED
    )


def test_direct_input_is_untrusted_by_default():
    decision = route(POLICY, RoutingInput(score=0.99, predicted_class_id=1))
    assert decision.primary is RoutingReason.CLASSIFIER_UNTRUSTED


@pytest.mark.parametrize("status", ["unmatched_detection", "unmatched_annotation"])
def test_detector_no_match_goes_to_reviewer_without_qwen(status):
    # Ưu tiên trước low_score: confidence thấp hoặc không có vẫn không gọi Qwen.
    for evidence in ({"confidence": 0.2}, {"confidence": None}):
        data = routing_input_from_candidate(detector(match_status=status, **evidence))
        decision = route(POLICY, data)
        assert decision.primary is RoutingReason.DETECTOR_NO_MATCH
        assert not decision.call_qwen and decision.human_review_required


def test_missing_match_status_fails_closed():
    candidate = detector()
    del candidate["evidence"]["match_status"]
    decision = route(POLICY, routing_input_from_candidate(candidate))
    assert decision.primary is RoutingReason.CLASSIFIER_UNAVAILABLE and decision.call_qwen


def test_routing_has_no_classifier_unit_dependency():
    import orchestration.models as models

    assert not hasattr(models, "ClassifierUnit")


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
