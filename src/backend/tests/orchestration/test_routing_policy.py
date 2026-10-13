"""M04C-01: policy `classification-routing-v0` (hàm thuần, không DB)."""

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
CONFIDENT = {"score": 0.95, "margin": 0.5, "predicted_class_id": "car"}


def decide(**overrides):
    return route(POLICY, RoutingInput(**{**CONFIDENT, **overrides}))


def test_confident_classifier_only_does_not_call_qwen():
    d = decide(annotated_class_id="car")
    assert d.primary is RoutingReason.CLASSIFIER_ONLY
    assert not d.call_qwen
    assert not d.human_review_required


def test_thresholds_are_inclusive_at_boundary():
    assert decide(score=0.85, margin=0.15).primary is RoutingReason.CLASSIFIER_ONLY
    assert decide(score=0.8499, margin=0.5).primary is RoutingReason.LOW_SCORE
    assert decide(score=0.95, margin=0.1499).primary is RoutingReason.LOW_MARGIN


def test_low_score_and_low_margin_trigger_qwen_with_both_reasons():
    d = decide(score=0.5, margin=0.05)
    assert d.call_qwen
    assert d.reasons == (RoutingReason.LOW_SCORE, RoutingReason.LOW_MARGIN)


def test_unknown_triggers_qwen():
    d = decide(classifier_unknown=True, predicted_class_id=None, score=None, margin=None)
    assert d.primary is RoutingReason.UNKNOWN
    assert d.call_qwen


def test_conflict_beats_high_score():
    d = decide(score=0.999, margin=0.9, annotated_class_id="truck")
    assert d.primary is RoutingReason.LABEL_CONFLICT
    assert d.call_qwen


def test_no_conflict_when_label_missing_or_equal():
    assert decide(annotated_class_id=None).primary is RoutingReason.CLASSIFIER_ONLY
    assert decide(annotated_class_id="car").primary is RoutingReason.CLASSIFIER_ONLY


def test_manual_recheck_triggers_even_when_confident():
    d = decide(annotated_class_id="car", manual_recheck=True)
    assert d.primary is RoutingReason.MANUAL_RECHECK
    assert d.call_qwen


def test_priority_order_when_everything_applies():
    d = decide(
        manual_recheck=True,
        annotated_class_id="truck",
        classifier_unknown=True,
        score=0.1,
        margin=0.0,
    )
    assert d.reasons == (
        RoutingReason.MANUAL_RECHECK,
        RoutingReason.LABEL_CONFLICT,
        RoutingReason.UNKNOWN,
        RoutingReason.LOW_SCORE,
        RoutingReason.LOW_MARGIN,
    )
    assert d.reasons[0] is d.primary


def test_invalid_crop_never_calls_qwen_and_needs_human():
    d = decide(crop_valid=False, manual_recheck=True, annotated_class_id="truck")
    assert d.primary is RoutingReason.INVALID_CROP
    assert not d.call_qwen
    assert d.human_review_required


def test_budget_exhausted_blocks_qwen_but_keeps_trigger_reasons():
    d = decide(budget_exhausted=True, annotated_class_id="truck")
    assert d.primary is RoutingReason.BUDGET_EXHAUSTED
    assert d.reasons == (RoutingReason.BUDGET_EXHAUSTED, RoutingReason.LABEL_CONFLICT)
    assert not d.call_qwen
    assert d.human_review_required


def test_budget_exhausted_is_irrelevant_when_no_qwen_needed():
    d = decide(budget_exhausted=True, annotated_class_id="car")
    assert d.primary is RoutingReason.CLASSIFIER_ONLY
    assert not d.human_review_required


@pytest.mark.parametrize("bad", [None, math.nan, math.inf, True])
def test_missing_or_invalid_scores_are_not_confident(bad):
    assert decide(score=bad).call_qwen
    assert decide(margin=bad).call_qwen


def test_policy_record_is_stable_and_labels_threshold_as_temporary():
    record = POLICY.as_record()
    assert record["name"] == "classification-routing-v0"
    assert record["threshold_semantics"] == "routing_temporary"
    assert record == RoutingPolicy().as_record()
    other = RoutingPolicy(score_threshold=0.9).as_record()
    assert other["policy_sha256"] != record["policy_sha256"]
    assert "calibrat" not in str(record).replace("routing_temporary", "")


def test_decision_carries_policy_record():
    assert decide().policy == POLICY.as_record()


def test_from_config_defaults_and_overrides():
    assert RoutingPolicy.from_config(None) == RoutingPolicy()
    assert RoutingPolicy.from_config({}) == RoutingPolicy()
    custom = RoutingPolicy.from_config({"score_threshold": 0.9, "margin_threshold": 0.2})
    assert (custom.score_threshold, custom.margin_threshold) == (0.9, 0.2)


@pytest.mark.parametrize(
    "config",
    [
        {"score_threshold": 1.5},
        {"score_threshold": -0.1},
        {"margin_threshold": "0.1"},
        {"margin_threshold": True},
        {"score_threshold": math.nan},
        {"calibrated_threshold": 0.9},
    ],
)
def test_from_config_rejects_invalid(config):
    with pytest.raises(RoutingPolicyError):
        RoutingPolicy.from_config(config)


def test_adapter_builds_input_and_missing_fields_are_not_confident():
    full = routing_input_from_candidate(
        {"class_id": "car", "annotated_class_id": "car", "score": 0.9, "margin": 0.3}
    )
    assert route(POLICY, full).primary is RoutingReason.CLASSIFIER_ONLY
    empty = routing_input_from_candidate({}, manual_recheck=True, budget_exhausted=True)
    assert empty.manual_recheck and empty.budget_exhausted
    assert route(POLICY, routing_input_from_candidate({})).call_qwen
    assert not routing_input_from_candidate({"crop_valid": False}).crop_valid
