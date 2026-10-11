"""Persistent frame ownership. PostgreSQL, not Redis, is authoritative."""

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
