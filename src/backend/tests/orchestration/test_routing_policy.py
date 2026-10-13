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


def _clf(**kw):
    base = {
        "status": "completed",
        "crop_valid": True,
        "predicted_class_id": 3,
        "annotated_class_id": 3,
        "score": 0.9,
        "margin": 0.3,
        "classifier_unknown": False,
    }
    return {"classifier": {**base, **kw}}


def test_adapter_confident_classifier_only():
    data = routing_input_from_candidate(_clf())
    assert route(POLICY, data).primary is RoutingReason.CLASSIFIER_ONLY


def test_adapter_conflict_with_integer_ids_beats_high_score():
    data = routing_input_from_candidate(_clf(annotated_class_id=4, score=0.99, margin=0.9))
    assert route(POLICY, data).primary is RoutingReason.LABEL_CONFLICT


def test_adapter_missing_or_null_classifier_is_not_confident_nor_invalid_crop():
    for cand in ({}, {"classifier": None}, {"classifier": "x"}):
        data = routing_input_from_candidate(cand)
        assert data.crop_valid
        decision = route(POLICY, data)
        assert decision.call_qwen and decision.primary is RoutingReason.LOW_SCORE


@pytest.mark.parametrize("status", ["pending", "running", "failed", "cancelled"])
def test_adapter_unfinished_classifier_ignores_stale_scores(status):
    data = routing_input_from_candidate(_clf(status=status, score=0.99, margin=0.9))
    assert data.score is None and data.predicted_class_id is None
    assert route(POLICY, data).call_qwen


def test_adapter_crop_invalid_never_calls_qwen():
    data = routing_input_from_candidate(_clf(status="failed", crop_valid=False, score=None))
    decision = route(POLICY, data)
    assert decision.primary is RoutingReason.INVALID_CROP and not decision.call_qwen


def test_adapter_completed_without_prediction_is_unknown_even_if_flag_false():
    data = routing_input_from_candidate(
        _clf(predicted_class_id=None, score=None, margin=None, classifier_unknown=False)
    )
    assert data.classifier_unknown
    assert route(POLICY, data).primary is RoutingReason.UNKNOWN


def test_adapter_null_score_or_margin_is_low_confidence():
    assert route(POLICY, routing_input_from_candidate(_clf(score=None))).call_qwen
    assert route(POLICY, routing_input_from_candidate(_clf(margin=None))).call_qwen


def test_adapter_flags_pass_through():
    data = routing_input_from_candidate(_clf(), manual_recheck=True, budget_exhausted=True)
    assert data.manual_recheck and data.budget_exhausted


@pytest.mark.parametrize("status", ["smoke_only", "trained", ""])
def test_checkpoint_status_reaches_every_decision_and_never_changes_routing(status):
    cases = [
        {},  # classifier_only
        {"annotated_class_id": 4},  # conflict
        {"crop_valid": False},  # invalid_crop
        {"budget_exhausted": True, "annotated_class_id": 4},  # budget
    ]
    for case in cases:
        with_status = decide(checkpoint_status=status, **case)
        baseline = decide(**case)
        assert with_status.checkpoint_status == status
        assert (with_status.primary, with_status.call_qwen, with_status.reasons) == (
            baseline.primary,
            baseline.call_qwen,
            baseline.reasons,
        )


def test_adapter_reads_checkpoint_status_and_defaults_to_empty():
    assert routing_input_from_candidate(_clf(checkpoint_status="smoke_only")).checkpoint_status == (
        "smoke_only"
    )
    assert routing_input_from_candidate({}).checkpoint_status == ""
    assert routing_input_from_candidate(_clf(checkpoint_status=None)).checkpoint_status == ""
