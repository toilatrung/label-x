"""Persistent frame ownership. PostgreSQL, not Redis, is authoritative."""

from typing import Any

from django.conf import settings
from django.db import models
from django.db.models import Q


class FrameReview(models.Model):
    class State(models.TextChoices):
        UNREVIEWED = "unreviewed", "Unreviewed"
        IN_REVIEW = "in_review", "In review"
        INCOMPLETE = "incomplete", "Incomplete"
        REVIEWED = "reviewed", "Reviewed"
        AWAITING_FOLLOWUP = "awaiting_followup", "Awaiting followup"
        COMPLETED = "completed", "Completed"

    run = models.ForeignKey("runs.QCRun", on_delete=models.PROTECT, related_name="frame_reviews")
    snapshot_frame = models.ForeignKey(
        "snapshots.SnapshotFrame", on_delete=models.PROTECT, related_name="reviews"
    )
    state = models.CharField(max_length=24, choices=State.choices, default=State.UNREVIEWED)
    previous_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )
    incomplete_since = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "frame_review"
        constraints = [
            models.UniqueConstraint(
                fields=["run", "snapshot_frame"], name="review_unique_run_frame"
            ),
        ]

    def __str__(self) -> str:
        return f"FrameReview {self.pk} (run={self.run_id}, state={self.state})"


class Lease(models.Model):
    frame_review = models.ForeignKey(FrameReview, on_delete=models.PROTECT, related_name="leases")
    holder = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    queue_source = models.CharField(max_length=8, choices=[("risk", "Risk"), ("random", "Random")])
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    renewed_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "review_lease"
        constraints = [
            models.UniqueConstraint(
                fields=["holder"],
                condition=Q(closed_at__isnull=True),
                name="review_one_open_lease_per_holder",
            ),
            models.UniqueConstraint(
                fields=["frame_review"],
                condition=Q(closed_at__isnull=True),
                name="review_one_open_lease_per_frame",
            ),
        ]
        indexes = [
            models.Index(fields=["holder", "expires_at"], name="review_lease_holder_exp_idx")
        ]

    def __str__(self) -> str:
        return f"Lease {self.pk} (frame={self.frame_review_id}, holder={self.holder_id})"


class Issue(models.Model):
    """Reviewer-owned issue projection; an engine candidate remains immutable."""

    class State(models.TextChoices):
        PENDING_REVIEW = "pending_review", "Pending review"
        IN_REVIEW = "in_review", "In review"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"
        ESCALATED = "escalated", "Escalated"
        FIX_PENDING = "fix_pending", "Fix pending"
        RECHECK_PENDING = "recheck_pending", "Recheck pending"
        RESOLVED = "resolved", "Resolved"
        REOPENED = "reopened", "Reopened"

    class Origin(models.TextChoices):
        ENGINE = "engine", "Engine"
        REVIEWER = "reviewer", "Reviewer"

    class Family(models.TextChoices):
        E1 = "E1", "Missing box"
        E2 = "E2", "Wrong class"
        E3 = "E3", "Duplicate box"
        STRUCTURAL = "structural", "Structural"

    class Severity(models.TextChoices):
        CRITICAL = "critical", "Critical"
        MEDIUM = "medium", "Medium"
        MINOR = "minor", "Minor"

    frame_review = models.ForeignKey(FrameReview, on_delete=models.PROTECT, related_name="issues")
    candidate = models.ForeignKey(
        "orchestration.CandidateRecord", null=True, blank=True, on_delete=models.PROTECT
    )
    family = models.CharField(max_length=16, choices=Family.choices)
    origin = models.CharField(max_length=16, choices=Origin.choices)
    state = models.CharField(max_length=24, choices=State.choices, default=State.PENDING_REVIEW)
    anchor = models.JSONField()
    description = models.TextField(blank=True)
    n_i = models.PositiveIntegerField(default=1)
    q_i = models.FloatField(null=True, blank=True)
    severity = models.CharField(  # noqa: DJ001 - OpenAPI requires JSON null before confirmation
        max_length=16, choices=Severity.choices, null=True, blank=True
    )
    rule_ids = models.JSONField(default=list)
    reviewer_evidence = models.JSONField(default=list)
    links = models.JSONField(default=list)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )
    idempotency_key = models.CharField(  # noqa: DJ001 - NULL excludes requests without a key
        max_length=36, null=True, blank=True
    )
    request_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "review_issue"
        constraints = [
            models.UniqueConstraint(
                fields=["candidate"],
                condition=Q(candidate__isnull=False),
                name="review_issue_one_per_candidate",
            ),
            models.UniqueConstraint(
                fields=["created_by", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="review_issue_manual_idempotency",
            ),
        ]

    def __str__(self) -> str:
        return f"Issue {self.pk} (frame={self.frame_review_id}, state={self.state})"


class ReviewDecisionQuerySet(models.QuerySet["ReviewDecision"]):
    def update(self, **kwargs: Any) -> int:
        raise ValueError("ReviewDecision is append-only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValueError("ReviewDecision is append-only")


class ReviewDecision(models.Model):
    """Append-only human decision; the issue state is only its current projection."""

    class Action(models.TextChoices):
        CONFIRM = "confirm", "Confirm"
        REJECT = "reject", "Reject"
        UNCERTAIN = "uncertain", "Uncertain"
        ESCALATE = "escalate", "Escalate"
        REQUEST_FIX = "request_fix", "Request fix"

    class ReferenceMatch(models.TextChoices):
        MATCHED = "matched", "Matched"
        NOT_MATCHED = "not_matched", "Not matched"
        NOT_EVALUATED = "not_evaluated", "Not evaluated"

    issue = models.ForeignKey(Issue, on_delete=models.PROTECT, related_name="review_decisions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    actor_role = models.CharField(max_length=16)
    action = models.CharField(max_length=16, choices=Action.choices)
    revision = models.CharField(max_length=64)
    reason = models.TextField(blank=True)
    rule_ids = models.JSONField(default=list)
    reference_version = models.CharField(  # noqa: DJ001 - DEC-009 distinguishes no reference
        max_length=128, null=True, blank=True
    )
    reference_match_status = models.CharField(
        max_length=16, choices=ReferenceMatch.choices, default=ReferenceMatch.NOT_EVALUATED
    )
    reference_error_ids = models.JSONField(default=list)
    audit_event = models.OneToOneField("audit.AuditEvent", on_delete=models.PROTECT)
    idempotency_key = models.CharField(  # noqa: DJ001 - NULL excludes requests without a key
        max_length=36, null=True, blank=True
    )
    request_hash = models.CharField(max_length=64, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    objects = ReviewDecisionQuerySet.as_manager()

    class Meta:
        db_table = "review_decision"
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "actor", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="review_decision_idempotency",
            ),
        ]

    def __str__(self) -> str:
        return f"ReviewDecision {self.pk} ({self.action} on issue={self.issue_id})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            raise ValueError("ReviewDecision is append-only")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValueError("ReviewDecision is append-only")


class DecisionCaseQuerySet(models.QuerySet["DecisionCase"]):
    def update(self, **kwargs: Any) -> int:
        raise ValueError("DecisionCase is append-only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValueError("DecisionCase is append-only")


class DecisionCase(models.Model):
    """Versioned human adjudication decision case; append-only history (UC-12, FR-ESC-04)."""

    class Outcome(models.TextChoices):
        CONFIRM = "confirm", "Confirm"
        REJECT = "reject", "Reject"
        GUIDELINE_MISSING = "guideline_missing", "Guideline missing"

    issue = models.ForeignKey(Issue, on_delete=models.PROTECT, related_name="decision_cases")
    review_decision = models.ForeignKey(
        ReviewDecision,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="decision_cases",
    )
    case_version = models.CharField(max_length=16)
    outcome = models.CharField(max_length=24, choices=Outcome.choices)
    rule_id = models.CharField(max_length=32)
    correct_label = models.CharField(  # noqa: DJ001 - OpenAPI nullable label
        max_length=64, null=True, blank=True
    )
    reason = models.TextField()
    override_reason = models.TextField(blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    idempotency_key = models.CharField(  # noqa: DJ001
        max_length=36, null=True, blank=True
    )
    request_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = DecisionCaseQuerySet.as_manager()

    class Meta:
        db_table = "review_decision_case"
        ordering = ["created_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "case_version"],
                name="review_decision_case_unique_version_per_issue",
            ),
            models.UniqueConstraint(
                fields=["issue", "actor", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="review_decision_case_idempotency",
            ),
        ]

    def __str__(self) -> str:
        return f"DecisionCase {self.pk} ({self.outcome} {self.case_version} issue={self.issue_id})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            raise ValueError("DecisionCase is append-only")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValueError("DecisionCase is append-only")


class ReworkRequest(models.Model):
    """Mutable rework projection; immutable decisions and verifications keep its history."""

    class Status(models.TextChoices):
        FIX_PENDING = "fix_pending", "Fix pending"
        RECHECK_PENDING = "recheck_pending", "Recheck pending"
        RESOLVED = "resolved", "Resolved"
        REOPENED = "reopened", "Reopened"

    issue = models.ForeignKey(Issue, on_delete=models.PROTECT, related_name="rework_requests")
    annotator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assigned_reworks"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_reworks"
    )
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.FIX_PENDING, db_index=True
    )
    instruction = models.TextField()
    severity = models.CharField(max_length=16, choices=Issue.Severity.choices)
    cvat_deep_link = models.URLField(max_length=1024)
    original_revision = models.CharField(max_length=64)
    submitted_revision = models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001
    recheck_snapshot = models.ForeignKey(
        "snapshots.Snapshot",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="rework_requests",
    )
    recheck_run = models.ForeignKey(
        "runs.QCRun",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="rework_requests",
    )
    due_at = models.DateTimeField()
    create_idempotency_key = models.CharField(max_length=36, null=True, blank=True)  # noqa: DJ001
    create_request_hash = models.CharField(max_length=64, blank=True)
    submission_idempotency_key = models.CharField(max_length=36, null=True, blank=True)  # noqa: DJ001
    submission_request_hash = models.CharField(max_length=64, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rework_request"
        ordering = ["created_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["issue"],
                condition=Q(status__in=["fix_pending", "recheck_pending"]),
                name="rework_one_active_per_issue",
            ),
            models.UniqueConstraint(
                fields=["created_by", "create_idempotency_key"],
                condition=Q(create_idempotency_key__isnull=False),
                name="rework_create_idempotency",
            ),
        ]

    def __str__(self) -> str:
        return f"ReworkRequest {self.pk} (issue={self.issue_id}, status={self.status})"


class ReworkRecheck(models.Model):
    """Immutable link from one submission round to its new snapshot and re-check run."""

    rework = models.ForeignKey(ReworkRequest, on_delete=models.PROTECT, related_name="rechecks")
    round = models.PositiveIntegerField(default=1)
    snapshot = models.ForeignKey("snapshots.Snapshot", on_delete=models.PROTECT)
    run = models.ForeignKey("runs.QCRun", on_delete=models.PROTECT)
    revision = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=36, null=True, blank=True)  # noqa: DJ001
    request_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rework_recheck"
        ordering = ["rework_id", "round"]
        constraints = [
            models.UniqueConstraint(
                fields=["rework", "snapshot"], name="rework_recheck_unique_snapshot"
            ),
            models.UniqueConstraint(fields=["rework", "round"], name="rework_recheck_unique_round"),
            models.UniqueConstraint(
                fields=["rework", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="rework_recheck_idempotency",
            ),
        ]

    def __str__(self) -> str:
        return f"ReworkRecheck {self.pk} (rework={self.rework_id}, round={self.round})"


class ReworkVerificationQuerySet(models.QuerySet["ReworkVerification"]):
    def update(self, **kwargs: Any) -> int:
        raise ValueError("ReworkVerification is append-only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValueError("ReworkVerification is append-only")


class ReworkVerification(models.Model):
    class Outcome(models.TextChoices):
        PASS = "pass", "Pass"
        FAIL = "fail", "Fail"

    rework = models.ForeignKey(
        ReworkRequest, on_delete=models.PROTECT, related_name="verifications"
    )
    verifier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recheck_run = models.ForeignKey("runs.QCRun", on_delete=models.PROTECT)
    outcome = models.CharField(max_length=8, choices=Outcome.choices)
    revision = models.CharField(max_length=64)
    reason = models.TextField(blank=True)
    audit_event = models.OneToOneField("audit.AuditEvent", on_delete=models.PROTECT)
    idempotency_key = models.CharField(max_length=36, null=True, blank=True)  # noqa: DJ001
    request_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ReworkVerificationQuerySet.as_manager()

    class Meta:
        db_table = "rework_verification"
        constraints = [
            models.UniqueConstraint(
                fields=["rework", "verifier", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="rework_verify_idempotency",
            )
        ]

    def __str__(self) -> str:
        return f"ReworkVerification {self.pk} ({self.outcome}, rework={self.rework_id})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            raise ValueError("ReworkVerification is append-only")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValueError("ReworkVerification is append-only")


class FinalRunVerificationQuerySet(models.QuerySet["FinalRunVerification"]):
    def update(self, **kwargs: Any) -> int:
        raise ValueError("FinalRunVerification is append-only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValueError("FinalRunVerification is append-only")


class FinalRunVerification(models.Model):
    """Immutable lineage from a full-scope final run to its rework evidence."""

    final_run = models.ForeignKey(
        "runs.QCRun", on_delete=models.PROTECT, related_name="verification_lineage"
    )
    verification = models.ForeignKey(
        ReworkVerification, on_delete=models.PROTECT, related_name="final_run_links"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = FinalRunVerificationQuerySet.as_manager()

    class Meta:
        db_table = "final_run_link"
        ordering = ["verification_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["final_run", "verification"],
                name="final_run_link_unique_verification",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"FinalRunVerification (run={self.final_run_id}, verification={self.verification_id})"
        )

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            raise ValueError("FinalRunVerification is append-only")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValueError("FinalRunVerification is append-only")
