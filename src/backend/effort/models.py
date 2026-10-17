"""Immutable, idempotent client effort events (FR-EVL-06)."""

from django.conf import settings
from django.db import models


class EffortEvent(models.Model):
    class Activity(models.TextChoices):
        VIEW_FRAME = "view_frame", "View frame"
        REVIEW_ISSUE = "review_issue", "Review issue"
        ADJUDICATE = "adjudicate", "Adjudicate"
        RECHECK_VERIFY = "recheck_verify", "Recheck / verify"

    client_event_id = models.UUIDField(unique=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="effort_events",
    )
    frame = models.ForeignKey(
        "review.FrameReview",
        on_delete=models.PROTECT,
        related_name="effort_events",
    )
    dataset_id = models.PositiveBigIntegerField(db_index=True)
    activity = models.CharField(max_length=32, choices=Activity.choices)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    active_ms = models.PositiveBigIntegerField()
    config_source = models.CharField(max_length=255)
    t_idle_seconds = models.PositiveIntegerField(null=True, blank=True)
    config_snapshot = models.JSONField(default=dict)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "effort_event"
        ordering = ["started_at", "id"]
        indexes = [
            models.Index(fields=["actor", "started_at"], name="effort_actor_start_idx"),
            models.Index(fields=["frame", "started_at"], name="effort_frame_start_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ended_at__gt=models.F("started_at")),
                name="effort_event_positive_interval",
            )
        ]

    def __str__(self) -> str:
        return f"{self.client_event_id} ({self.activity}, frame={self.frame_id})"
