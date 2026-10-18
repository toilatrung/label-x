"""Serializers for QC Run API matching OpenAPI contract (docs/04-api/openapi.yaml)."""

from __future__ import annotations

from typing import Any, cast

from django.core.files.storage import storages
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers

from orchestration.evaluation_read import evaluation_summary
from orchestration.models import CandidateRecord
from ranking import read_v1
from review.api_serializers import EngineStatusSerializer, FrameKeySerializer
from review.lineage import run_lineage_fields
from review.models import FrameReview
from runs.config_guard import validate_config_safety
from runs.models import (
    AIModel,
    ConfigVersion,
    ModelArtifact,
    QCRun,
    RunRankingEntry,
    WorkUnit,
)
from runs.progress import engine_progress
from runs.routing_config import validate_routing_thresholds
from runs.vlm_read import build_vlm_view, run_vlm_engine_state
from vlm.config import validate_vlm_config


class RunCreateSerializer(serializers.Serializer[Any]):
    """Schema for RunCreate."""

    snapshot_id = serializers.IntegerField(min_value=1)
    config_version_id = serializers.IntegerField(min_value=1)
    metric_reference_id = serializers.IntegerField(min_value=1, required=False)
    seed = serializers.IntegerField()


class RunRetryFailedSerializer(serializers.Serializer[Any]):
    engine = serializers.ChoiceField(
        choices=("schema", "geometry", "duplicate", "detector", "metric", "vlm"),
        required=False,
        help_text="Chỉ chạy lại đơn vị lỗi của engine được chọn; giữ kết quả engine khác.",
    )


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

    include_progress = False
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
        work_units = list(obj.work_units.all()) if self.include_progress else []
        for er in obj.engine_results.all():
            row: dict[str, Any] = {
                "engine": er.engine,
                "status": er.status,
                "reason": er.reason,
                "failed_units": er.failed_units,
            }
            if self.include_progress:
                progress = engine_progress(obj, er.engine, work_units=work_units)
                if er.status != "running" and not progress["pending"]:
                    progress["phase"] = "finished"
                row["progress"] = progress
            results.append(row)
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

    include_progress = True
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


@extend_schema_serializer(component_name="Model")
class ModelSerializer(serializers.ModelSerializer[AIModel]):
    class Meta:
        model = AIModel
        fields = [
            "id",
            "name",
            "kind",
            "version",
            "enabled",
            "revision",
            "updated_at",
        ]
        read_only_fields = ["id", "revision", "updated_at"]


class ModelPatchSerializer(serializers.Serializer[Any]):
    expected_revision = serializers.IntegerField(required=True)
    enabled = serializers.BooleanField(required=False)
    version = serializers.CharField(required=False, max_length=64)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if "enabled" not in attrs and "version" not in attrs:
            raise serializers.ValidationError(
                "Cần cung cấp ít nhất một trường 'enabled' hoặc 'version'."
            )
        return attrs


@extend_schema_serializer(component_name="PaginatedModelList")
class PaginatedModelListSerializer(serializers.Serializer[Any]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = ModelSerializer(many=True)


@extend_schema_serializer(component_name="ConfigRule")
class ConfigRuleSerializer(serializers.Serializer[Any]):
    rule_id = serializers.CharField()
    name = serializers.CharField()
    enabled = serializers.BooleanField()
    parameters = serializers.DictField(required=False, default=dict)


@extend_schema_serializer(component_name="ConfigVersionRules")
class ConfigVersionRulesSerializer(serializers.Serializer[Any]):
    config_version_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["draft", "published"])
    rules = ConfigRuleSerializer(many=True)
    release_thresholds = serializers.DictField()
    sampling_policy = serializers.DictField()


class ConfigVersionCreateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=128)
    engines = serializers.DictField()
    thresholds = serializers.DictField(required=False, default=dict)
    models = serializers.DictField(required=False, default=dict)
    rules = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    release_thresholds = serializers.DictField(required=False, default=dict)
    sampling_policy = serializers.DictField(required=False, default=dict)

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
        """models.vlm đúng schema VLM: allowlist model/host, không secret/prompt."""
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
    engine = serializers.ChoiceField(
        choices=["detector", "duplicate", "geometry", "metric", "schema", "vlm"]
    )
    status = serializers.ChoiceField(
        choices=["checked", "failed", "not_checked", "partial", "running"]
    )
    required = serializers.BooleanField(required=False)  # type: ignore[assignment]
    unit = serializers.ChoiceField(choices=["frame", "shape"])
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
    "skipped",
    "pending",
    "running",
    "checked",
    "uncertain",
    "failed",
    "cancelled",
]


class CandidateVlmSerializer(serializers.Serializer[Any]):
    """Evidence VLM (Qwen/Gemini) của candidate; chỉ là đề xuất, không phải quyết định review."""

    # Chuỗi thuần (không enum tự sinh) để không va chạm tên enum của drf-spectacular; giá trị hợp lệ
    # nằm trong help_text và được test khoá lại.
    state = serializers.CharField(help_text="Một trong: " + ", ".join(VLM_STATES))
    engine_status = serializers.CharField(
        help_text="checked | partial | failed | not_checked | running (payload FE v0)"
    )
    source: Any = serializers.CharField(help_text="qwen | gemini, theo model đã khoá")
    conclusion = serializers.CharField(
        allow_null=True, help_text="confirmed | uncertain | null; chỉ là đề xuất AI"
    )
    class_id = serializers.CharField(allow_null=True)
    class_name = serializers.CharField(allow_null=True)
    reason_code = serializers.CharField(
        allow_null=True,
        help_text=(
            "invalid_crop | provider_error | parse_failure | budget_exhausted | "
            "provider_unavailable | deadline_exceeded | null"
        ),
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


class CandidateLatestEvaluationSerializer(serializers.Serializer[Any]):
    """Lần đánh giá AI mới nhất của candidate (BLOCKER-034 B-4)."""

    id = serializers.IntegerField()
    generation = serializers.IntegerField()
    status: Any = serializers.CharField(
        help_text="pending | running | completed | failed | cancelled"
    )


class CandidateSerializer(serializers.ModelSerializer[Any]):
    """Schema for Candidate matching OpenAPI components.schemas.Candidate."""

    frame = serializers.SerializerMethodField()
    severity = serializers.SerializerMethodField()
    vlm = serializers.SerializerMethodField()
    latest_evaluation = serializers.SerializerMethodField()

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
            "latest_evaluation",
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

    @extend_schema_field(CandidateLatestEvaluationSerializer(allow_null=True))
    def get_latest_evaluation(self, obj: CandidateRecord) -> dict[str, Any] | None:
        # Context do view nạp một lần cho cả trang (latest_evaluations), không truy vấn từng dòng.
        return evaluation_summary(self.context.get("latest_evaluations", {}).get(obj.pk))


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
    priority = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    dominant_tier = serializers.SerializerMethodField()
    issue_counts_by_tier = serializers.SerializerMethodField()
    evidence_group = serializers.SerializerMethodField()
    evidence_scope = serializers.SerializerMethodField()

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
            "priority",
            "thumbnail_url",
            "dominant_tier",
            "issue_counts_by_tier",
            "evidence_group",
            "evidence_scope",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.IntegerField(allow_null=True, min_value=0, max_value=5))
    def get_dominant_tier(self, obj: RunRankingEntry) -> int | None:
        return read_v1.dominant_tier(obj.ranking.score_version, obj.explanation)

    @extend_schema_field(
        serializers.DictField(child=serializers.IntegerField(min_value=0), allow_null=True)
    )
    def get_issue_counts_by_tier(self, obj: RunRankingEntry) -> dict[str, int] | None:
        return read_v1.issue_counts_by_tier(obj.ranking.score_version, obj.explanation)

    @extend_schema_field(serializers.ChoiceField(choices=read_v1.EVIDENCE_GROUPS, allow_null=True))
    def get_evidence_group(self, obj: RunRankingEntry) -> str | None:
        return read_v1.evidence_group(obj.ranking.score_version, obj.explanation)

    @extend_schema_field({"type": "object", "additionalProperties": True, "nullable": True})
    def get_evidence_scope(self, obj: RunRankingEntry) -> dict[str, Any] | None:
        return read_v1.evidence_scope(obj.ranking.score_version, obj.explanation)

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

    @extend_schema_field(serializers.ChoiceField(choices=["high", "medium", "low"]))
    def get_priority(self, obj: RunRankingEntry) -> str:
        total = max(int(self.context.get("ranking_total", 0)), 1)
        if obj.rank <= (total + 2) // 3:
            return "high"
        if obj.rank <= (total * 2 + 2) // 3:
            return "medium"
        return "low"

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_thumbnail_url(self, obj: RunRankingEntry) -> str | None:
        key = obj.snapshot_frame.media_storage_key
        return storages["snapshots"].url(key) if key else None


@extend_schema_serializer(component_name="RankedFrame")
class RankedFrameResponseSerializer(RankedFrameSerializer):
    """Describe optional contract additions without marking method fields required."""

    priority: Any = serializers.ChoiceField(choices=["high", "medium", "low"], required=False)
    thumbnail_url: Any = serializers.URLField(allow_null=True, required=False)
    dominant_tier: Any = serializers.IntegerField(
        allow_null=True, required=False, min_value=0, max_value=5
    )
    issue_counts_by_tier: Any = serializers.DictField(
        child=serializers.IntegerField(min_value=0), allow_null=True, required=False
    )
    evidence_group: Any = serializers.ChoiceField(
        choices=read_v1.EVIDENCE_GROUPS, allow_null=True, required=False
    )
    evidence_scope: Any = serializers.DictField(allow_null=True, required=False)


class RankingEvidenceCountsSerializer(serializers.Serializer[Any]):
    suspected = serializers.IntegerField(min_value=0)
    unassessed = serializers.IntegerField(min_value=0)
    no_suspicions = serializers.IntegerField(min_value=0)


class RankingPriorityCountsSerializer(serializers.Serializer[Any]):
    high = serializers.IntegerField(min_value=0)
    medium = serializers.IntegerField(min_value=0)
    low = serializers.IntegerField(min_value=0)


class PaginatedRankedFrameListSerializer(serializers.Serializer[Any]):
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    source: Any = serializers.ChoiceField(choices=["risk", "random_audit"])
    content_hash = serializers.CharField()
    ranking_hash = serializers.CharField()
    priority_counts = RankingPriorityCountsSerializer(required=False)
    tier_counts: Any = serializers.DictField(
        child=serializers.IntegerField(min_value=0), allow_null=True, required=False
    )
    evidence_counts = RankingEvidenceCountsSerializer(allow_null=True, required=False)
    results = RankedFrameResponseSerializer(many=True)


class RunLineageNodeSerializer(serializers.Serializer[Any]):
    run_id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=["original", "rework_verification", "final"])
    snapshot_id = serializers.IntegerField()
    rework_id = serializers.IntegerField(allow_null=True)
    created_at = serializers.DateTimeField()


class RunLineageSerializer(serializers.Serializer[Any]):
    run_id = serializers.IntegerField()
    origin_run_id = serializers.IntegerField(allow_null=True)
    final_run_id = serializers.IntegerField(allow_null=True)
    chain = RunLineageNodeSerializer(many=True)
