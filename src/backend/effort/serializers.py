from __future__ import annotations

from typing import Any

from rest_framework import serializers

from effort.models import EffortEvent
from effort.services import GAP_REASONS


class EffortGapSerializer(serializers.Serializer[dict[str, Any]]):
    """A span inside the event during which the user was not actively working."""

    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField()
    reason = serializers.ChoiceField(choices=[(value, value) for value in GAP_REASONS])

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["ended_at"] <= attrs["started_at"]:
            raise serializers.ValidationError(
                {"ended_at": "ended_at must be later than started_at."}
            )
        return attrs


class EffortEventInputSerializer(serializers.Serializer[dict[str, Any]]):
    client_event_id = serializers.UUIDField()
    frame_id = serializers.IntegerField(min_value=1)
    activity = serializers.ChoiceField(choices=EffortEvent.Activity.choices)
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField()
    gaps = EffortGapSerializer(many=True, required=False)
    policy_version = serializers.CharField(max_length=64, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["ended_at"] <= attrs["started_at"]:
            raise serializers.ValidationError(
                {"ended_at": "ended_at must be later than started_at."}
            )
        for gap in attrs.get("gaps", []):
            if gap["started_at"] < attrs["started_at"] or gap["ended_at"] > attrs["ended_at"]:
                raise serializers.ValidationError({"gaps": "Every gap must lie inside the event."})
        return attrs


class EffortEventBatchSerializer(serializers.Serializer[dict[str, Any]]):
    events = EffortEventInputSerializer(many=True, allow_empty=False)


class EffortEventReceiptSerializer(serializers.Serializer[dict[str, int]]):
    accepted = serializers.IntegerField(min_value=0)
    duplicates = serializers.IntegerField(min_value=0)
