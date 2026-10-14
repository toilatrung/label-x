from __future__ import annotations

from typing import Any

from rest_framework import serializers

from releases.models import Release
from reports.serializers import GateResultSerializer


class ReleaseSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    run_id = serializers.IntegerField()
    snapshot_id = serializers.IntegerField()
    config_version_id = serializers.IntegerField()
    version_tag = serializers.CharField()
    status = serializers.ChoiceField(choices=Release.Status.choices)
    gate_status = serializers.ChoiceField(choices=Release.GateStatus.choices, required=False)
    created_by = serializers.IntegerField(source="created_by_id")
    created_at = serializers.DateTimeField()
    approved_by = serializers.IntegerField(source="approved_by_id", allow_null=True, required=False)
    approved_at = serializers.DateTimeField(allow_null=True, required=False)


class PaginatedReleaseListSerializer(serializers.Serializer[Any]):
    next = serializers.CharField(allow_null=True, required=False)
    previous = serializers.CharField(allow_null=True, required=False)
    results = ReleaseSerializer(many=True)


class ReleaseApproveSerializer(serializers.Serializer[Any]):
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class ManifestArtifactSerializer(serializers.Serializer[Any]):
    name = serializers.CharField()
    sha256 = serializers.CharField()
    size_bytes = serializers.IntegerField(min_value=0, required=False)


class ReleaseManifestSerializer(serializers.Serializer[Any]):
    release_id = serializers.IntegerField()
    generated_at = serializers.DateTimeField()
    checksum = serializers.CharField()
    snapshot_id = serializers.IntegerField()
    run_id = serializers.IntegerField()
    config_version_id = serializers.IntegerField()
    guideline_version = serializers.CharField(allow_null=True, required=False)
    score_version = serializers.CharField(allow_null=True, required=False)
    gate = GateResultSerializer(allow_null=True, required=False)
    artifacts = ManifestArtifactSerializer(many=True)
