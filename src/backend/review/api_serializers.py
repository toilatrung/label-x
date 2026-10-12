"""Runtime schema (request/response) for M-03 review, lease, rework and policy endpoints.

Documentation-only: views keep building their payloads; these classes describe them for
OpenAPI generation and are not used to validate or transform runtime data.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from review.models import FrameReview, Issue, ReviewDecision, ReworkRequest

FAMILIES = Issue.Family.values
SEVERITIES = Issue.Severity.values


class PolicySerializer(serializers.Serializer[Any]):
    policy_version = serializers.CharField()
    source: Any = serializers.CharField()
    decision_status = serializers.CharField()
    lease_ttl_seconds = serializers.IntegerField()
    resume_reservation_seconds = serializers.IntegerField()
    idle_threshold_seconds = serializers.IntegerField()
    idle_gap_rule = serializers.CharField()
    immediate_exclusion_reasons = serializers.ListField(child=serializers.CharField())
    renew_on = serializers.CharField()


class QueueNextRequestSerializer(serializers.Serializer[Any]):
    run_id = serializers.IntegerField(min_value=1)


class LeaseSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    frame_id = serializers.IntegerField()
    holder_user_id = serializers.IntegerField()
    expires_at = serializers.DateTimeField()


class FrameKeySerializer(serializers.Serializer[Any]):
    cvat_task_id = serializers.IntegerField()
    frame_number = serializers.IntegerField()


class GrantedFrameSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    run_id = serializers.IntegerField()
    frame_key = FrameKeySerializer()
    cvat_job_id = serializers.IntegerField()
    rank = serializers.IntegerField()
    review_state = serializers.ChoiceField(choices=FrameReview.State.values)
    missing_evidence = serializers.JSONField()
    width = serializers.IntegerField()
    height = serializers.IntegerField()


class LeaseGrantSerializer(serializers.Serializer[Any]):
    lease = LeaseSerializer()
    frame = GrantedFrameSerializer()
    resumed = serializers.BooleanField()


class FrameSummarySerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    run_id = serializers.IntegerField()
    frame_key = FrameKeySerializer()
    cvat_job_id = serializers.IntegerField()
    rank = serializers.IntegerField(allow_null=True)
    review_state = serializers.ChoiceField(choices=FrameReview.State.values)
    missing_evidence = serializers.BooleanField()
    image_url = serializers.CharField()
    width = serializers.IntegerField()
    height = serializers.IntegerField()
    cvat_deep_link = serializers.CharField()


class FrameCompleteRequestSerializer(serializers.Serializer[Any]):
    lease_id = serializers.IntegerField(min_value=1)


class ReviewDecisionRecordSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    issue_id = serializers.IntegerField()
    actor_user_id = serializers.IntegerField()
    actor_role = serializers.CharField()
    decision = serializers.ChoiceField(choices=ReviewDecision.Action.values)
    revision = serializers.CharField()
    reason = serializers.CharField(allow_null=True)
    rule_ids = serializers.ListField(child=serializers.CharField())
    reference_version = serializers.CharField(allow_null=True)
    reference_match_status = serializers.CharField()
    reference_error_ids = serializers.ListField(child=serializers.CharField())
    recorded_at = serializers.DateTimeField()


class IssueSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    family = serializers.ChoiceField(choices=FAMILIES)
    origin = serializers.ChoiceField(choices=Issue.Origin.values)
    state = serializers.ChoiceField(choices=Issue.State.values)
    anchor = serializers.JSONField()
    n_i = serializers.JSONField(allow_null=True)
    q_i = serializers.JSONField(allow_null=True)
    severity = serializers.ChoiceField(choices=SEVERITIES, allow_null=True)
    rule_ids = serializers.ListField(child=serializers.CharField())
    evidence = serializers.JSONField()
    links = serializers.JSONField()
    review_decisions = ReviewDecisionRecordSerializer(many=True)


class EngineStatusSerializer(serializers.Serializer[Any]):
    engine = serializers.CharField()
    status = serializers.CharField()
    reason = serializers.CharField(allow_null=True)
    failed_units = serializers.IntegerField()


class FrameIssuesSerializer(serializers.Serializer[Any]):
    frame = FrameSummarySerializer()
    guideline_version = serializers.CharField(allow_null=True)
    snapshot_revision = serializers.CharField()
    annotations = serializers.ListField(child=serializers.DictField())
    predictions = serializers.ListField(child=serializers.DictField())
    engines = EngineStatusSerializer(many=True)
    issues = IssueSerializer(many=True)


class ManualIssueCreateSerializer(serializers.Serializer[Any]):
    frame_id = serializers.IntegerField(min_value=1)
    lease_id = serializers.IntegerField(min_value=1)
    family = serializers.ChoiceField(choices=FAMILIES)
    anchor = serializers.JSONField()
    description = serializers.CharField(required=False, allow_blank=True)


class IssueDecisionCreateSerializer(serializers.Serializer[Any]):
    lease_id = serializers.IntegerField(min_value=1)
    action = serializers.ChoiceField(choices=["confirm", "reject", "uncertain", "escalate"])
    revision = serializers.CharField()
    family = serializers.ChoiceField(choices=FAMILIES, required=False)
    severity = serializers.ChoiceField(choices=SEVERITIES, required=False)
    reason = serializers.CharField(required=False)
    rule_id = serializers.CharField(required=False)
    override_reason = serializers.CharField(required=False)


class IssueDecisionSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    issue_id = serializers.IntegerField()
    action = serializers.ChoiceField(choices=ReviewDecision.Action.values)
    actor_user_id = serializers.IntegerField()
    revision = serializers.CharField()
    family = serializers.ChoiceField(choices=FAMILIES, allow_null=True)
    severity = serializers.ChoiceField(choices=SEVERITIES, allow_null=True)
    reason = serializers.CharField(allow_null=True)
    rule_id = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()
    audit_event_id = serializers.IntegerField(allow_null=True)


class PaginatedEscalationSerializer(serializers.Serializer[Any]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = IssueSerializer(many=True)


class ReworkCreateRequestSerializer(serializers.Serializer[Any]):
    issue_id = serializers.IntegerField(min_value=1)
    instruction = serializers.CharField(min_length=1)
    annotator_user_id = serializers.IntegerField(min_value=1)
    due_at = serializers.DateTimeField()
    severity = serializers.ChoiceField(choices=SEVERITIES)
    cvat_deep_link = serializers.URLField()


class ReworkSubmissionRequestSerializer(serializers.Serializer[Any]):
    cvat_revision = serializers.CharField(min_length=1, max_length=64)


class ReworkVerifyRequestSerializer(serializers.Serializer[Any]):
    passed = serializers.BooleanField()
    revision = serializers.CharField(max_length=64)
    reason = serializers.CharField(required=False, allow_blank=True)
    override_reason = serializers.CharField(required=False, allow_blank=True)


class ReworkRequestSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    issue_id = serializers.IntegerField()
    annotator_user_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=ReworkRequest.Status.values)
    original_revision = serializers.CharField()
    submitted_revision = serializers.CharField(allow_null=True)
    recheck_run_id = serializers.IntegerField(allow_null=True)
    due_at = serializers.DateTimeField()
    cvat_deep_link = serializers.CharField()


class ReworkReadSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    dataset_id = serializers.IntegerField()
    issue_id = serializers.IntegerField()
    frame_id = serializers.IntegerField()
    annotator_user_id = serializers.IntegerField()
    created_by_user_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=ReworkRequest.Status.values)
    instruction = serializers.CharField()
    severity = serializers.ChoiceField(choices=SEVERITIES)
    original_revision = serializers.CharField()
    submitted_revision = serializers.CharField(allow_null=True)
    recheck_run_id = serializers.IntegerField(allow_null=True)
    due_at = serializers.DateTimeField()
    cvat_deep_link = serializers.CharField()
    submitted_at = serializers.DateTimeField(allow_null=True)
    resolved_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    round_count = serializers.IntegerField()


class ReworkVerificationSummarySerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    outcome = serializers.CharField(help_text="pass | fail")
    verifier_user_id = serializers.IntegerField()
    reason = serializers.CharField(allow_blank=True)
    verified_at = serializers.DateTimeField()


class ReworkRoundSerializer(serializers.Serializer[Any]):
    round = serializers.IntegerField()
    revision = serializers.CharField()
    snapshot_id = serializers.IntegerField()
    recheck_run_id = serializers.IntegerField()
    recheck_run_status = serializers.CharField()
    submitted_at = serializers.DateTimeField(allow_null=True)
    verification = ReworkVerificationSummarySerializer(allow_null=True)
    result_status = serializers.ChoiceField(choices=ReworkRequest.Status.values)


class ReworkDetailSerializer(ReworkReadSerializer):
    review_state = serializers.ChoiceField(choices=FrameReview.State.values)
    timeline = ReworkRoundSerializer(many=True)


class PaginatedReworkSerializer(serializers.Serializer[Any]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = ReworkReadSerializer(many=True)
    counts = serializers.DictField(child=serializers.IntegerField())
