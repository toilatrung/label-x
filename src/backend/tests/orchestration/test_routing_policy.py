"""M04C-01: policy `classification-routing-v0` (hàm thuần, không DB)."""

from __future__ import annotations

import math

import pytest

from orchestration.routing_policy import (
    ClassifierNotReadyError,
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
    "margin": 0.5,
    "predicted_class_id": 3,
    "checkpoint_status": "trained",
}


def decide(**overrides):
    return route(POLICY, RoutingInput(**{**CONFIDENT, **overrides}))


def test_confident_trained_classifier_only_does_not_call_qwen():
    d = decide(annotated_class_id=3)
    assert d.primary is RoutingReason.CLASSIFIER_ONLY
    assert not d.call_qwen and not d.human_review_required


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
    assert d.primary is RoutingReason.UNKNOWN and d.call_qwen


def test_conflict_beats_high_score():
    d = decide(score=0.999, margin=0.9, annotated_class_id=4)
    assert d.primary is RoutingReason.LABEL_CONFLICT and d.call_qwen


def test_no_conflict_when_label_missing_or_equal():
    assert decide(annotated_class_id=None).primary is RoutingReason.CLASSIFIER_ONLY
    assert decide(annotated_class_id=3).primary is RoutingReason.CLASSIFIER_ONLY


@pytest.mark.parametrize(
    ("predicted", "annotated"), [("2", 2), (2, "2"), (True, 1), (1, True), (2.0, 2)]
)
def test_labels_of_wrong_type_never_become_a_fake_conflict(predicted, annotated):
    d = decide(predicted_class_id=predicted, annotated_class_id=annotated)
    assert RoutingReason.LABEL_CONFLICT not in d.reasons


def test_manual_recheck_triggers_even_when_confident():
    d = decide(annotated_class_id=3, manual_recheck=True)
    assert d.primary is RoutingReason.MANUAL_RECHECK and d.call_qwen


def test_priority_order_when_everything_applies():
    d = decide(
        manual_recheck=True,
        annotated_class_id=4,
        classifier_unknown=True,
        score=0.1,
        margin=0.0,
        checkpoint_status="smoke_only",
    )
    assert d.reasons == (
        RoutingReason.MANUAL_RECHECK,
        RoutingReason.LABEL_CONFLICT,
        RoutingReason.UNKNOWN,
        RoutingReason.CLASSIFIER_UNTRUSTED,
        RoutingReason.LOW_SCORE,
        RoutingReason.LOW_MARGIN,
    )
    assert d.reasons[0] is d.primary


def test_invalid_crop_never_calls_qwen_and_needs_human():
    d = decide(crop_valid=False, manual_recheck=True, annotated_class_id=4)
    assert d.primary is RoutingReason.INVALID_CROP
    assert not d.call_qwen and d.human_review_required


@pytest.mark.parametrize("bad", ["false", "true", None, 0, 1])
def test_crop_valid_must_be_a_real_true(bad):
    d = decide(crop_valid=bad)
    assert d.primary is RoutingReason.INVALID_CROP


def test_invalid_crop_beats_budget_exhausted():
    """Mutant T07: invalid_crop phải thắng budget_exhausted (không có crop để gửi)."""
    d = decide(crop_valid=False, budget_exhausted=True, annotated_class_id=4)
    assert d.primary is RoutingReason.INVALID_CROP
    assert RoutingReason.BUDGET_EXHAUSTED not in d.reasons


def test_budget_exhausted_blocks_qwen_but_keeps_trigger_reasons():
    d = decide(budget_exhausted=True, annotated_class_id=4)
    assert d.primary is RoutingReason.BUDGET_EXHAUSTED
    assert d.reasons == (RoutingReason.BUDGET_EXHAUSTED, RoutingReason.LABEL_CONFLICT)
    assert not d.call_qwen and d.human_review_required


def test_budget_exhausted_is_irrelevant_when_no_qwen_needed():
    d = decide(budget_exhausted=True, annotated_class_id=3)
    assert d.primary is RoutingReason.CLASSIFIER_ONLY and not d.human_review_required


@pytest.mark.parametrize("bad", [None, math.nan, math.inf, -math.inf, True, 5.0, -0.1, 1.01, "0.9"])
def test_missing_invalid_or_out_of_range_scores_are_not_confident(bad):
    assert decide(score=bad).call_qwen
    assert decide(margin=bad).call_qwen
    assert decide(score=bad).primary is RoutingReason.LOW_SCORE


@pytest.mark.parametrize("status", ["smoke_only", "", "unknown", "TRAINED"])
def test_untrusted_checkpoint_forces_qwen_and_human_review(status):
    d = decide(checkpoint_status=status, annotated_class_id=3)
    assert d.primary is RoutingReason.CLASSIFIER_UNTRUSTED
    assert d.call_qwen and d.human_review_required
    assert d.checkpoint_status == status


def test_untrusted_with_exhausted_budget_still_needs_human_and_skips_qwen():
    d = decide(checkpoint_status="smoke_only", budget_exhausted=True)
    assert d.primary is RoutingReason.BUDGET_EXHAUSTED
    assert RoutingReason.CLASSIFIER_UNTRUSTED in d.reasons
    assert not d.call_qwen and d.human_review_required


def test_unavailable_classifier_calls_qwen_but_is_not_low_score():
    d = decide(classifier_available=False, score=None, margin=None)
    assert d.primary is RoutingReason.CLASSIFIER_UNAVAILABLE
    assert d.reasons == (RoutingReason.CLASSIFIER_UNAVAILABLE,)
    assert d.call_qwen and not d.human_review_required


def test_policy_record_is_stable_and_labels_threshold_as_temporary():
    record = POLICY.as_record()
    assert record["name"] == "classification-routing-v0"
    assert record["threshold_semantics"] == "routing_temporary"
    assert record == RoutingPolicy().as_record()
    assert (
        RoutingPolicy(score_threshold=0.9).as_record()["policy_sha256"] != record["policy_sha256"]
    )


def test_decision_carries_policy_record_and_checkpoint_status():
    d = decide()
    assert d.policy == POLICY.as_record() and d.checkpoint_status == "trained"


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
        [],
        ["x"],
        "score_threshold",
        3,
    ],
)
def test_from_config_rejects_invalid_including_non_mapping(config):
    with pytest.raises(RoutingPolicyError):
        RoutingPolicy.from_config(config)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -1, 1.5, True, "0.5", None])
def test_direct_construction_validates_thresholds(bad):
    with pytest.raises(RoutingPolicyError):
        RoutingPolicy(score_threshold=bad)
    with pytest.raises(RoutingPolicyError):
        RoutingPolicy(margin_threshold=bad)


def _clf(**kw):
    base = {
        "status": "completed",
        "reason_code": "",
        "crop_valid": True,
        "predicted_class_id": 3,
        "annotated_class_id": 3,
        "score": 0.9,
        "margin": 0.3,
        "classifier_unknown": False,
        "checkpoint_status": "trained",
    }
    return {"classifier": {**base, **kw}}


def test_adapter_confident_trained_classifier_only():
    data = routing_input_from_candidate(_clf())
    assert route(POLICY, data).primary is RoutingReason.CLASSIFIER_ONLY


def test_adapter_conflict_with_integer_ids_beats_high_score():
    data = routing_input_from_candidate(_clf(annotated_class_id=4, score=0.99, margin=0.9))
    assert route(POLICY, data).primary is RoutingReason.LABEL_CONFLICT


@pytest.mark.parametrize(
    "cand", [{}, {"classifier": None}, {"classifier": "x"}, {"classifier": []}]
)
def test_adapter_missing_classifier_is_unavailable_not_invalid_crop(cand):
    data = routing_input_from_candidate(cand)
    d = route(POLICY, data)
    assert d.primary is RoutingReason.CLASSIFIER_UNAVAILABLE and d.call_qwen


@pytest.mark.parametrize("status", ["pending", "running"])
def test_adapter_pending_or_running_classifier_must_wait(status):
    with pytest.raises(ClassifierNotReadyError):
        routing_input_from_candidate(_clf(status=status, score=0.99, margin=0.9))


@pytest.mark.parametrize(
    "reason", ["inference_error", "timeout", "checkpoint_unavailable", "checksum_mismatch", "x"]
)
def test_adapter_infra_failure_is_unavailable_and_keeps_crop_valid(reason):
    data = routing_input_from_candidate(_clf(status="failed", reason_code=reason, score=None))
    d = route(POLICY, data)
    assert d.primary is RoutingReason.CLASSIFIER_UNAVAILABLE
    assert d.call_qwen and RoutingReason.LOW_SCORE not in d.reasons


@pytest.mark.parametrize("reason", ["invalid_crop", "box_too_small"])
def test_adapter_crop_failures_are_invalid_crop_never_qwen(reason):
    data = routing_input_from_candidate(
        _clf(status="failed", reason_code=reason, crop_valid=False, score=None)
    )
    d = route(POLICY, data)
    assert d.primary is RoutingReason.INVALID_CROP and not d.call_qwen


@pytest.mark.parametrize("bad", ["false", "true", None, 0, 1])
def test_adapter_crop_valid_must_be_real_bool(bad):
    data = routing_input_from_candidate(_clf(crop_valid=bad))
    assert route(POLICY, data).primary is RoutingReason.INVALID_CROP


def test_adapter_cancelled_classifier_is_unavailable():
    data = routing_input_from_candidate(_clf(status="cancelled"))
    assert route(POLICY, data).primary is RoutingReason.CLASSIFIER_UNAVAILABLE


def test_adapter_wrong_typed_labels_are_unavailable_not_conflict():
    for kw in (
        {"predicted_class_id": "2"},
        {"annotated_class_id": "2"},
        {"predicted_class_id": True},
    ):
        d = route(POLICY, routing_input_from_candidate(_clf(**kw)))
        assert d.primary is RoutingReason.CLASSIFIER_UNAVAILABLE
        assert RoutingReason.LABEL_CONFLICT not in d.reasons


def test_adapter_completed_without_prediction_is_unknown_even_if_flag_false():
    data = routing_input_from_candidate(
        _clf(predicted_class_id=None, score=None, margin=None, classifier_unknown=False)
    )
    assert data.classifier_unknown
    assert route(POLICY, data).primary is RoutingReason.UNKNOWN


@pytest.mark.parametrize("score", [None, 5.0, math.nan, -1.0])
def test_adapter_out_of_range_or_null_score_is_low_confidence(score):
    d = route(POLICY, routing_input_from_candidate(_clf(score=score)))
    assert d.call_qwen and d.primary is RoutingReason.LOW_SCORE


def test_adapter_smoke_only_checkpoint_is_untrusted_and_needs_human():
    d = route(POLICY, routing_input_from_candidate(_clf(checkpoint_status="smoke_only")))
    assert d.primary is RoutingReason.CLASSIFIER_UNTRUSTED
    assert d.call_qwen and d.human_review_required and d.checkpoint_status == "smoke_only"


def test_adapter_missing_checkpoint_status_is_untrusted():
    d = route(POLICY, routing_input_from_candidate(_clf(checkpoint_status=None)))
    assert d.primary is RoutingReason.CLASSIFIER_UNTRUSTED and d.checkpoint_status == ""


def test_adapter_flags_pass_through():
    data = routing_input_from_candidate(_clf(), manual_recheck=True, budget_exhausted=True)
    assert data.manual_recheck and data.budget_exhausted
    data = routing_input_from_candidate({}, manual_recheck=True, budget_exhausted=True)
    assert data.manual_recheck and data.budget_exhausted


def test_unknown_classifier_with_null_scores_goes_to_qwen():
    d = route(
        POLICY,
        routing_input_from_candidate(
            _clf(predicted_class_id=None, score=None, margin=None, annotated_class_id=None)
        ),
    )
    assert d.primary is RoutingReason.UNKNOWN and d.call_qwen


def test_route_called_directly_skips_conflict_for_wrong_typed_labels_so_use_the_adapter():
    """Khoá hành vi đã ghi trong docstring: route() trực tiếp bỏ qua conflict khi nhãn sai kiểu;
    đường đúng là adapter, nơi dữ liệu sai kiểu thành classifier_unavailable."""
    direct = decide(predicted_class_id="2", annotated_class_id=3)
    assert RoutingReason.LABEL_CONFLICT not in direct.reasons
    via_adapter = route(
        POLICY, routing_input_from_candidate(_clf(predicted_class_id="2", annotated_class_id=3))
    )
    assert via_adapter.primary is RoutingReason.CLASSIFIER_UNAVAILABLE
