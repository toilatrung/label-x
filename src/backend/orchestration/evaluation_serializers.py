"""Serializer request cho POST /api/candidates/{id}/evaluations/ (M04C-02).

Chỉ nhận reason + expected_revision; mọi khoá khác (prompt, model, api_key, ảnh) bị từ chối.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from orchestration.evaluation_guard import MAX_REASON_LENGTH


class CandidateEvaluationCreateSerializer(serializers.Serializer[Any]):
    reason = serializers.CharField(max_length=MAX_REASON_LENGTH, trim_whitespace=True)
    expected_revision = serializers.CharField(max_length=128)

    def to_internal_value(self, data: Any) -> Any:
        if isinstance(data, dict):
            extra = set(data) - set(self.fields)
            if extra:
                raise serializers.ValidationError(
                    {name: "Trường không được hỗ trợ." for name in sorted(extra)}
                )
        return super().to_internal_value(data)
