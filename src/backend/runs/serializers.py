"""Serializers for QC Run API matching OpenAPI contract (docs/04-api/openapi.yaml)."""

from __future__ import annotations

from typing import Any, cast

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from orchestration.models import CandidateRecord
from review.api_serializers import EngineStatusSerializer, FrameKeySerializer
from review.lineage import run_lineage_fields
from review.models import FrameReview
from runs.config_guard import validate_config_safety
from runs.models import ConfigVersion, ModelArtifact, QCRun, RunRankingEntry, WorkUnit
from runs.routing_config import validate_routing_thresholds
from runs.vlm_read import build_vlm_view, run_vlm_engine_state
from vlm.config import validate_vlm_config


class RunCreateSerializer(serializers.Serializer[Any]):
    """Schema for RunCreate."""

    snapshot_id = serializers.IntegerField(min_value=1)
    config_version_id = serializers.IntegerField(min_value=1)
    seed = serializers.IntegerField()


class ModelArtifactSerializer(serializers.ModelSerializer[Any]):
    """Schema for ModelArtifact."""

    class Meta:
        model = ModelArtifact
        fields = ["name", "version", "checksum"]


class EngineRunStatusSerializer(serializers.Serializer[Any]):
    """Schema for EngineRunStatus."""

    engine = serializers.CharField()
    status = serializers.CharField()
    reason = serializers.CharField(allow_null=True, required=False)
    failed_units = serializers.IntegerField(default=0)


class RunSerializer(serializers.ModelSerializer[Any]):
    """Schema for Run matching OpenAPI components.schemas.Run."""

    model_artifact = ModelArtifactSerializer(read_only=True, allow_null=True)
    engines = serializers.SerializerMethodField()
    origin_run_id = serializers.IntegerField(
        source="origin_run.id", allow_null=True, read_only=True
    )

    class Meta:
        model = QCRun
        fields = [
            "id",
            "snapshot_id",
            "config_version_id",
            "seed",
            "status",
            "is_final",
            "origin_run_id",
            "score_version",
            "model_artifact",
            "engines",
            "created_by",
            "created_at",
            "finished_at",
        ]
        read_only_fields = fields

    @extend_schema_field(EngineStatusSerializer(many=True))
    def get_engines(self, obj: QCRun) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for er in obj.engine_results.all():
            results.append(
                {
                    "engine": er.engine,
                    "status": er.status,
                    "reason": er.reason,
                    "failed_units": er.failed_units,
                }
            )
        return results


class VerificationLineageItemSerializer(serializers.Serializer[Any]):
    verification_id = serializers.IntegerField()
    rework_id = serializers.IntegerField()
    recheck_run_id = serializers.IntegerField()
    outcome = serializers.ChoiceField(choices=("pass", "fail"))
    revision = serializers.CharField()
    verified_at = serializers.DateTimeField()


class SelectedFinalSourceSerializer(serializers.Serializer[Any]):
    cvat_job_id = serializers.IntegerField()
    rework_id = serializers.IntegerField()
    verification_id = serializers.IntegerField()
    source_run_id = serializers.IntegerField()
    source_revision = serializers.CharField()


class RunDetailSerializer(RunSerializer):
    """GET /api/runs/{id}/: Run plus final-run lineage and operational source (D05)."""

    verification_lineage = serializers.SerializerMethodField()
    selected_final_sources = serializers.SerializerMethodField()
    operational_source = serializers.SerializerMethodField()

    class Meta(RunSerializer.Meta):
        fields = [
            *RunSerializer.Meta.fields,
            "verification_lineage",
            "selected_final_sources",
            "operational_source",
        ]
        read_only_fields = fields

    def _lineage(self, obj: QCRun) -> dict[str, object]:
        cached = getattr(obj, "_lineage_fields", None)
        if cached is None:
            cached = run_lineage_fields(obj)
            obj._lineage_fields = cached  # type: ignore[attr-defined]
        return cast(dict[str, object], cached)

    @extend_schema_field(VerificationLineageItemSerializer(many=True))
    def get_verification_lineage(self, obj: QCRun) -> list[dict[str, object]]:
        return cast(list[dict[str, object]], self._lineage(obj)["verification_lineage"])

    @extend_schema_field(SelectedFinalSourceSerializer(many=True))
    def get_selected_final_sources(self, obj: QCRun) -> list[dict[str, object]]:
        return cast(list[dict[str, object]], self._lineage(obj)["selected_final_sources"])

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_operational_source(self, obj: QCRun) -> object:
        return self._lineage(obj)["operational_source"]


class PaginatedRunListSerializer(serializers.Serializer[Any]):
    """Schema for PaginatedRunList."""

    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = RunSerializer(many=True)


class ConfigVersionSerializer(serializers.ModelSerializer[Any]):
    class Meta:
        model = ConfigVersion
        fields = [
            "id",
            "name",
            "status",
            "engines",
            "thresholds",
            "models",
            "created_by",
            "created_at",
            "published_at",
        ]
        read_only_fields = fields


class ConfigVersionCreateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=128)
    engines = serializers.DictField()
    thresholds = serializers.DictField(required=False, default=dict)
    models = serializers.DictField(required=False, default=dict)

    def validate_engines(self, value: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "schema",
            "geometry",
            "duplicate",
            "detector",
            "metric",
            "vlm",
        }
        if not value or any(
            name not in allowed
            or not isinstance(config, dict)
            or not isinstance(config.get("enabled"), bool)
            for name, config in value.items()
        ):
            raise serializers.ValidationError(
                "Engine phải có tên hợp lệ và cờ enabled dạng boolean."
            )
        if not any(config["enabled"] for config in value.values()):
            raise serializers.ValidationError("Cần bật ít nhất một engine.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        errors = validate_config_safety(
            attrs.get("engines", {}), attrs.get("thresholds", {}), attrs.get("models", {})
        )
        if errors:
            raise serializers.ValidationError({"config": errors})
        return attrs

    def validate_thresholds(self, value: dict[str, Any]) -> dict[str, Any]:
        errors = validate_routing_thresholds(value)
        if errors:
            raise serializers.ValidationError(errors)
        return value

    def validate_models(self, value: dict[str, Any]) -> dict[str, Any]:
        """models.vlm phải đúng schema Qwen (M04A-01): allowlist model/host, không secret/prompt."""
        if "vlm" in value:
            errors = validate_vlm_config(value["vlm"])
            if errors:
                raise serializers.ValidationError(errors)
        return value


class PaginatedConfigVersionSerializer(serializers.Serializer[Any]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = ConfigVersionSerializer(many=True)


class WorkUnitSerializer(serializers.ModelSerializer[Any]):
    class Meta:
        model = WorkUnit
        fields = [
            "id",
            "engine",
            "shard_key",
            "shard_index",
            "status",
            "attempt",
            "last_error",
            "started_at",
            "finished_at",
        ]
        read_only_fields = fields


class PaginatedWorkUnitSerializer(serializers.Serializer[Any]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = WorkUnitSerializer(many=True)


class LedgerEntrySerializer(serializers.Serializer[Any]):
    engine = serializers.CharField()
    status = serializers.CharField()
    required = serializers.BooleanField()  # type: ignore[assignment]
    unit = serializers.CharField()
    total = serializers.IntegerField()
    eligible = serializers.IntegerField()
    excluded = serializers.IntegerField()
    applicability_version = serializers.CharField()
    completed = serializers.IntegerField()
    failed = serializers.IntegerField()
    pending = serializers.IntegerField()
    not_checked = serializers.IntegerField()
    not_checked_reasons = serializers.DictField(child=serializers.IntegerField())
    coverage = serializers.FloatField(allow_null=True)


VLM_STATES = [
    "disabled",
    "no_model",
    "not_applicable",
    "not_triggered",
    "pending",
    "running",
    "checked",
    "uncertain",
    "failed",
    "cancelled",
]


class CandidateVlmSerializer(serializers.Serializer[Any]):
    """Evidence VLM (Qwen) của candidate; chỉ là đề xuất, không phải quyết định review."""

    # Chuỗi thuần (không enum tự sinh) để không va chạm tên enum của drf-spectacular; giá trị hợp lệ
    # nằm trong help_text và được test khoá lại.
    state = serializers.CharField(help_text="Một trong: " + ", ".join(VLM_STATES))
    engine_status = serializers.CharField(
        help_text="checked | partial | failed | not_checked | running (payload FE v0)"
    )
    source: Any = serializers.CharField(help_text="Luôn là qwen")
    conclusion = serializers.CharField(
        allow_null=True, help_text="confirmed | uncertain | null; chỉ là đề xuất AI"
    )
    class_id = serializers.CharField(allow_null=True)
    class_name = serializers.CharField(allow_null=True)
    reason_code = serializers.CharField(
        allow_null=True,
        help_text="invalid_crop | provider_error | parse_failure | budget_exhausted | null",
    )
    evidence_id = serializers.IntegerField(allow_null=True)
    evaluation_id = serializers.CharField(allow_null=True)
    model_version = serializers.CharField(allow_null=True)
    provider = serializers.CharField(allow_null=True)
    provider_host = serializers.CharField(allow_null=True)
    response_model = serializers.CharField(allow_null=True)
    prompt_version = serializers.CharField(allow_null=True)
    policy_version = serializers.CharField(allow_null=True)
    snapshot_revision = serializers.CharField(allow_null=True)
    attempts = serializers.IntegerField()
    request_id = serializers.CharField(allow_null=True)
    crop_sha256 = serializers.CharField(allow_null=True)
    crop = serializers.DictField(allow_null=True)
    rationale = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField(allow_null=True)


class CandidateSerializer(serializers.ModelSerializer[Any]):
    """Schema for Candidate matching OpenAPI components.schemas.Candidate."""

    frame = serializers.SerializerMethodField()
    severity = serializers.SerializerMethodField()
    vlm = serializers.SerializerMethodField()

    class Meta:
        model = CandidateRecord
        fields = [
            "id",
            "engine",
            "engine_version",
            "family",
            "severity",
            "frame",
            "anchor",
            "evidence",
            "vlm",
        ]
        read_only_fields = fields

    def get_frame(self, obj: CandidateRecord) -> dict[str, int]:
        return {
            "cvat_task_id": obj.cvat_task_id,
            "frame_number": obj.frame_number,
        }

    def get_severity(self, obj: CandidateRecord) -> str | None:
        return getattr(obj, "severity", None)

    @extend_schema_field(CandidateVlmSerializer)
    def get_vlm(self, obj: CandidateRecord) -> dict[str, Any]:
        units = self.context.get("vlm_units", {})
        states = self.context.setdefault("vlm_engine_state", {})
        if obj.run_id not in states:
            states[obj.run_id] = run_vlm_engine_state(obj.run_id)
        return build_vlm_view(units.get(obj.pk), states[obj.run_id])


class PaginatedCandidateListSerializer(serializers.Serializer[Any]):
    """Schema for PaginatedCandidateList."""

    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    raw_count = serializers.IntegerField(allow_null=True)
    dedup_count = serializers.IntegerField()
    results = CandidateSerializer(many=True)


@extend_schema_field({"type": "object", "additionalProperties": {"type": "integer"}})
class IssueCountsField(serializers.JSONField):
    """Stored JSON passed through unchanged; only the OpenAPI description is typed."""


@extend_schema_field({"type": "object", "additionalProperties": True})
class ExplanationField(serializers.JSONField):
    """Stored JSON passed through unchanged; only the OpenAPI description is typed."""


class RankedFrameSerializer(serializers.ModelSerializer[Any]):
    """Stored ranking row matching and extending the public RankedFrame schema."""

    frame_id = serializers.IntegerField(source="snapshot_frame_id", read_only=True)
    frame_key = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    baseline_score = serializers.SerializerMethodField()
    queue = serializers.SerializerMethodField()
    source: Any = serializers.ChoiceField(
        choices=["risk", "random_audit"], source="ranking.source", read_only=True
    )
    score_version = serializers.CharField(source="ranking.score_version", read_only=True)
    review_state = serializers.SerializerMethodField()
    lease_holder_user_id = serializers.SerializerMethodField()
    issue_counts = IssueCountsField(read_only=True)
    explanation = ExplanationField(read_only=True)

    class Meta:
        model = RunRankingEntry
        fields = [
            "frame_id",
            "frame_key",
            "rank",
            "score",
            "baseline_score",
            "score_version",
            "queue",
            "source",
            "review_state",
            "missing_evidence",
            "issue_counts",
            "explanation",
            "lease_holder_user_id",
        ]
        read_only_fields = fields

    @extend_schema_field(FrameKeySerializer)
    def get_frame_key(self, obj: RunRankingEntry) -> dict[str, int]:
        return {
            "cvat_task_id": obj.snapshot_frame.snapshot_job.cvat_task_id,
            "frame_number": obj.snapshot_frame.frame_index,
        }

    def get_score(self, obj: RunRankingEntry) -> float:
        return float(obj.score)

    def get_baseline_score(self, obj: RunRankingEntry) -> float:
        return float(obj.baseline_score)

    @extend_schema_field(serializers.ChoiceField(choices=["risk", "random"]))
    def get_queue(self, obj: RunRankingEntry) -> str:
        return "random" if obj.ranking.source == "random_audit" else "risk"

    @extend_schema_field(serializers.ChoiceField(choices=FrameReview.State.values))
    def get_review_state(self, obj: RunRankingEntry) -> str:
        # Annotated by RunRankingView from persisted FrameReview/Lease rows (expiry-aware).
        return str(getattr(obj, "effective_review_state", None) or "unreviewed")

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_lease_holder_user_id(self, obj: RunRankingEntry) -> int | None:
        holder = getattr(obj, "active_lease_holder_id", None)
        return int(holder) if holder is not None else None


class PaginatedRankedFrameListSerializer(serializers.Serializer[Any]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    source: Any = serializers.ChoiceField(choices=["risk", "random_audit"])
    content_hash = serializers.CharField()
    ranking_hash = serializers.CharField()
    results = RankedFrameSerializer(many=True)
