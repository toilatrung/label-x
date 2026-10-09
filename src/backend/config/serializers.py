"""Serializer dùng chung cho schema `Error` của contract (docs/04-api/openapi.yaml)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

# Enum `ErrorCode` của contract; test_error_codes_match_contract giữ hai nguồn trùng nhau.
ERROR_CODES = [
    "VALIDATION_ERROR",
    "INVALID_CREDENTIALS",
    "NOT_AUTHENTICATED",
    "FORBIDDEN",
    "OUT_OF_SCOPE",
    "SELF_REVIEW_FORBIDDEN",
    "SAME_REQUESTER_APPROVER",
    "IDENTITY_MAPPING_MISSING",
    "NOT_FOUND",
    "LEASE_CONFLICT",
    "INVALID_TRANSITION",
    "REVISION_UNCHANGED",
    "IDEMPOTENCY_KEY_REUSED",
    "SCOPE_BUSY",
    "ISSUE_EXISTS",
    "BUSINESS_RULE_UNMET",
    "INSUFFICIENT_SAMPLE",
]


class ErrorSerializer(serializers.Serializer[dict[str, Any]]):
    code = serializers.ChoiceField(choices=ERROR_CODES)
    message = serializers.CharField()
    request_id = serializers.CharField()
    details = serializers.DictField(required=False)
