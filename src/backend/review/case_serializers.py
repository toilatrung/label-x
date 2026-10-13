"""Runtime schema for M-03 Decision Case and adjudication endpoints (read/write documentation)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

OUTCOME_CHOICES = ["confirm", "reject", "guideline_gap"]


class AdjudicationCreateSerializer(serializers.Serializer[Any]):
    outcome = serializers.ChoiceField(choices=OUTCOME_CHOICES)
    rule_id = serializers.CharField(max_length=32)
    correct_label = serializers.CharField(max_length=64, allow_null=True, required=False)
    reason = serializers.CharField(min_length=1)
    override_reason = serializers.CharField(required=False)


class DecisionCaseSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    issue_id = serializers.IntegerField()
    outcome = serializers.ChoiceField(choices=OUTCOME_CHOICES)
    actor_user_id = serializers.IntegerField()
    rule_id = serializers.CharField()
    correct_label = serializers.CharField(allow_null=True)
    reason = serializers.CharField()
    case_version = serializers.CharField()
    created_at = serializers.DateTimeField()


class DecisionCaseHistoryItemSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    case_version = serializers.CharField()
    outcome = serializers.ChoiceField(choices=OUTCOME_CHOICES)
    actor_user_id = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class DecisionCaseDetailSerializer(DecisionCaseSerializer):
    history = DecisionCaseHistoryItemSerializer(many=True)


class PaginatedDecisionCaseSerializer(serializers.Serializer[Any]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = DecisionCaseSerializer(many=True)
