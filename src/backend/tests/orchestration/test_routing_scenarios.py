"""M04C-04 (phần thuần, mock/fixture): 7 nhánh A/B/C ở mức policy + guard.

CHƯA nối orchestration/DB/API/ledger: các assert API/DB/ledger của #291 làm sau khi A chốt #282
và có migration A/B. Kết quả ở đây KHÔNG phải runtime pass của luồng thật.
"""

from __future__ import annotations

import pytest

from orchestration.evaluation_guard import StaleRevisionError, check_revision
from orchestration.routing_policy import (
    RoutingPolicy,
    RoutingReason,
    route,
    routing_input_from_candidate,
)

POLICY = RoutingPolicy()


def candidate(**classifier):
    base = {
        "status": "completed",
        "crop_valid": True,
        "predicted_class_id": 3,
        "annotated_class_id": 3,
        "score": 0.95,
        "margin": 0.5,
        "classifier_unknown": False,
        "checkpoint_status": "smoke_only",
    }
    return {"classifier": {**base, **classifier}}


def test_branch_1_classifier_only():
    d = route(POLICY, routing_input_from_candidate(candidate()))
    assert (d.primary, d.call_qwen, d.human_review_required) == (
        RoutingReason.CLASSIFIER_ONLY,
        False,
        False,
    )
    assert d.checkpoint_status == "smoke_only"  # nguồn smoke vẫn hiện trong evidence


def test_branch_2_trigger_low_score_and_margin():
    d = route(POLICY, routing_input_from_candidate(candidate(score=0.6, margin=0.05)))
    assert d.call_qwen and d.reasons == (RoutingReason.LOW_SCORE, RoutingReason.LOW_MARGIN)


def test_branch_3_conflict_beats_high_score():
    d = route(POLICY, routing_input_from_candidate(candidate(annotated_class_id=4, score=0.999)))
    assert d.primary is RoutingReason.LABEL_CONFLICT and d.call_qwen


def test_branch_4_uncertain_classifier_abstains():
    d = route(
        POLICY,
        routing_input_from_candidate(
            candidate(predicted_class_id=None, score=None, margin=None, annotated_class_id=None)
        ),
    )
    assert d.primary is RoutingReason.UNKNOWN and d.call_qwen


def test_branch_5_provider_failure_path_keeps_human_in_loop():
    # Policy chỉ quyết gọi Qwen; kết quả lỗi provider là việc của VlmUnit (A). Ở đây khoá giả định:
    # candidate cần Qwen luôn có call_qwen=True và KHÔNG tự đặt human_review_required=True.
    d = route(POLICY, routing_input_from_candidate(candidate(score=0.2)))
    assert d.call_qwen and not d.human_review_required


def test_branch_6_budget_exhausted_skips_qwen_and_needs_human():
    d = route(
        POLICY,
        routing_input_from_candidate(candidate(annotated_class_id=4), budget_exhausted=True),
    )
    assert d.primary is RoutingReason.BUDGET_EXHAUSTED
    assert not d.call_qwen and d.human_review_required
    assert RoutingReason.LABEL_CONFLICT in d.reasons


def test_branch_7_stale_revision_is_rejected_before_any_routing():
    with pytest.raises(StaleRevisionError):
        check_revision(expected_revision="rev-old", current_revision="rev-new")


def test_manual_recheck_new_logical_evaluation_triggers_even_when_confident():
    d = route(POLICY, routing_input_from_candidate(candidate(), manual_recheck=True))
    assert d.primary is RoutingReason.MANUAL_RECHECK and d.call_qwen
