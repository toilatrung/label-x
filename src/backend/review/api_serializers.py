"""Runtime schema (request/response) for M-03 review, lease, rework and policy endpoints.

Documentation-only: views keep building their payloads; these classes describe them for
OpenAPI generation and are not used to validate or transform runtime data.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter
from rest_framework import serializers

from review.models import FrameReview, Issue, ReviewDecision, ReworkRequest, ReworkVerification

IDEMPOTENCY_KEY_PARAM = OpenApiParameter(
    "Idempotency-Key",
    str,
    OpenApiParameter.HEADER,
    required=False,
    description="Khóa chống ghi trùng cho request ghi (chuỗi tối đa 36 ký tự).",
)

FAMILIES = Issue.Family.values
SEVERITIES = Issue.Severity.values
# Mirror of the contract enums (docs/04-api/openapi.yaml); documentation-only.
FRAME_STATES = FrameReview.State.values
ENGINE_NAMES = ["schema", "geometry", "duplicate", "detector", "metric", "vlm"]
ENGINE_STATUSES = ["running", "checked", "partial", "failed", "not_checked"]
NOT_CHECKED_REASONS = ["disabled", "no_model", "no_reference", "not_applicable", "not_triggered"]
DECISION_ACTIONS = [
    "confirm",
    "reject",
    "uncertain",
    "escalate",
    "request_fix",
    "adjudicate_confirm",
    "adjudicate_reject",
    "adjudicate_guideline_gap",
]
ACTOR_ROLES = ["reviewer", "qa_lead", "super_admin"]
REFERENCE_MATCH = ["matched", "not_matched", "not_evaluated"]


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
    cvat_job_id = serializers.IntegerField(required=False)
    rank = serializers.IntegerField(allow_null=True, required=False)
    review_state = serializers.ChoiceField(choices=FRAME_STATES)
    missing_evidence = serializers.BooleanField()
    image_url = serializers.URLField(required=False)
    width = serializers.IntegerField(required=False)
    height = serializers.IntegerField(required=False)
    cvat_deep_link = serializers.URLField(required=False)


class LeaseGrantSerializer(serializers.Serializer[Any]):
    lease = LeaseSerializer()
    frame = GrantedFrameSerializer()
    resumed = serializers.BooleanField(required=False)


class FrameSummarySerializer(serializers.Serializer[Any]):
    # cvat_job_id/rank/width/height are always sent, but the contract keeps them optional on
    # purpose (frontend generated types would otherwise break; see R-241-parity-result.json).
    id = serializers.IntegerField()
    run_id = serializers.IntegerField()
    frame_key = FrameKeySerializer()
    cvat_job_id = serializers.IntegerField(required=False)
    rank = serializers.IntegerField(allow_null=True, required=False)
    review_state = serializers.ChoiceField(choices=FRAME_STATES)
    missing_evidence = serializers.BooleanField()
    image_url = serializers.URLField(required=False)
    width = serializers.IntegerField(required=False)
    height = serializers.IntegerField(required=False)
    cvat_deep_link = serializers.URLField(required=False)


class FrameCompleteRequestSerializer(serializers.Serializer[Any]):
    lease_id = serializers.IntegerField(min_value=1)


class BBoxSerializer(serializers.Serializer[Any]):
    x1 = serializers.FloatField()
    y1 = serializers.FloatField()
    x2 = serializers.FloatField()
    y2 = serializers.FloatField()


class ObjectRefSerializer(serializers.Serializer[Any]):
    namespace = serializers.ChoiceField(choices=["cvat_shape", "detector", "reviewer_region"])
    id = serializers.CharField()


class AnchorSerializer(serializers.Serializer[Any]):
    kind = serializers.ChoiceField(
        choices=[
            "prediction_region",
            "annotation",
            "annotation_cluster",
            "annotation_rule",
            "manual_object",
            "manual_region",
        ]
    )
    objects = ObjectRefSerializer(many=True)
    rule_id = serializers.CharField(allow_null=True, required=False)
    bbox = BBoxSerializer(allow_null=True, required=False)
    policy_version = serializers.CharField()


class EvidenceSerializer(serializers.Serializer[Any]):
    engine = serializers.ChoiceField(choices=ENGINE_NAMES)
    rule_id = serializers.CharField(allow_null=True, required=False)
    expected = serializers.CharField(allow_null=True, required=False)
    actual = serializers.CharField(allow_null=True, required=False)
    prediction_bbox = BBoxSerializer(allow_null=True, required=False)
    prediction_class = serializers.CharField(allow_null=True, required=False)
    confidence = serializers.FloatField(allow_null=True, required=False)
    iou = serializers.FloatField(allow_null=True, required=False)


class IssueLinkSerializer(serializers.Serializer[Any]):
    kind = serializers.ChoiceField(choices=["recurrence_of", "suggested_recurrence_of"])
    issue_id = serializers.IntegerField()
    run_id = serializers.IntegerField(required=False)


class FrameAnnotationSourceSerializer(serializers.Serializer[Any]):
    kind = serializers.CharField()
    id = serializers.IntegerField()


class FrameAnnotationSerializer(serializers.Serializer[Any]):
    id = serializers.CharField()
    source: Any = FrameAnnotationSourceSerializer()
    label_id = serializers.IntegerField()
    bbox = BBoxSerializer(allow_null=True)
    rotation = serializers.FloatField(required=False)
    occluded = serializers.BooleanField(required=False)
    outside = serializers.BooleanField(required=False)
    z_order = serializers.IntegerField(required=False)
    attributes = serializers.ListField(child=serializers.DictField(), required=False)


class FramePredictionSerializer(serializers.Serializer[Any]):
    candidate_id = serializers.IntegerField()
    engine = serializers.CharField()
    engine_version = serializers.CharField()
    family = serializers.CharField()
    anchor = serializers.DictField()
    evidence = serializers.JSONField()


class ReviewDecisionRecordSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    issue_id = serializers.IntegerField()
    actor_user_id = serializers.IntegerField()
    actor_role = serializers.ChoiceField(choices=ACTOR_ROLES)
    decision = serializers.ChoiceField(choices=DECISION_ACTIONS)
    revision = serializers.CharField()
    reason = serializers.CharField(allow_blank=True)
    rule_ids = serializers.ListField(child=serializers.CharField())
    reference_version = serializers.CharField(allow_null=True)
    reference_match_status = serializers.ChoiceField(choices=REFERENCE_MATCH)
    reference_error_ids = serializers.ListField(child=serializers.CharField())
    recorded_at = serializers.DateTimeField()


class IssueSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    family = serializers.ChoiceField(choices=FAMILIES)
    origin = serializers.ChoiceField(choices=Issue.Origin.values)
    state = serializers.ChoiceField(choices=Issue.State.values)
    anchor = AnchorSerializer()
    n_i = serializers.IntegerField()
    # Always sent; optional in the contract on purpose (see FrameSummarySerializer).
    q_i = serializers.FloatField(allow_null=True, required=False)
    severity = serializers.ChoiceField(choices=SEVERITIES, allow_null=True, required=False)
    rule_ids = serializers.ListField(child=serializers.CharField(), required=False)
    evidence = EvidenceSerializer(many=True)
    links = IssueLinkSerializer(many=True)
    review_decisions = ReviewDecisionRecordSerializer(many=True)


class EngineStatusSerializer(serializers.Serializer[Any]):
    engine = serializers.ChoiceField(choices=ENGINE_NAMES)
    status = serializers.ChoiceField(choices=ENGINE_STATUSES)
    # Always sent; optional in the contract on purpose (see FrameSummarySerializer).
    reason = serializers.ChoiceField(choices=NOT_CHECKED_REASONS, allow_null=True, required=False)
    failed_units = serializers.IntegerField(required=False)


class FrameIssuesSerializer(serializers.Serializer[Any]):
    frame = FrameSummarySerializer()
    guideline_version = serializers.CharField(allow_null=True)
    # Always sent; optional in the contract on purpose (frontend types, see R-241 result).
    snapshot_revision = serializers.CharField(required=False)
    annotations = FrameAnnotationSerializer(many=True, required=False)
    predictions = FramePredictionSerializer(many=True, required=False)
    engines = EngineStatusSerializer(many=True)
    issues = IssueSerializer(many=True)


class ManualIssueCreateSerializer(serializers.Serializer[Any]):
    frame_id = serializers.IntegerField(min_value=1)
    lease_id = serializers.IntegerField(min_value=1)
    family = serializers.ChoiceField(choices=FAMILIES)
    anchor = AnchorSerializer()
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
    family = serializers.ChoiceField(choices=FAMILIES)
    severity = serializers.ChoiceField(choices=SEVERITIES, allow_null=True)
    reason = serializers.CharField(allow_null=True)
    rule_id = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()
    audit_event_id = serializers.IntegerField(required=False)


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


class ReworkCurrentRevisionSerializer(serializers.Serializer[Any]):
    rework_id = serializers.IntegerField()
    cvat_job_id = serializers.IntegerField()
    revision_sha256 = serializers.CharField(min_length=64, max_length=64)
    original_revision = serializers.CharField()
    unchanged = serializers.BooleanField()
    rework_status = serializers.ChoiceField(choices=ReworkRequest.Status.values, required=False)
    read_at = serializers.DateTimeField()


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
    outcome = serializers.ChoiceField(choices=ReworkVerification.Outcome.values)
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
