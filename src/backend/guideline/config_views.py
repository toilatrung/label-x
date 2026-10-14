"""Guideline upload and explicit, audited dataset policy assignment."""

from __future__ import annotations

from typing import Any, cast

import httpx
from django.contrib.auth.models import User
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import HasRoleAndDatasetScope, append_action_audit
from config.exceptions import ApiError
from config.serializers import ErrorSerializer
from guideline.importing import load_guideline, preview_guideline
from guideline.models import DatasetGuideline, GuidelineVersion
from guideline.taxonomy import GuidelineBindingError, bind_taxonomy
from snapshots.dataset_views import _client


class GuidelineTaxonomyAttributeSerializer(serializers.Serializer[Any]):
    name = serializers.CharField()
    rule_id = serializers.CharField()
    allowed_values = serializers.ListField(
        child=serializers.CharField(trim_whitespace=False), required=False, default=list
    )


class GuidelineTaxonomyLabelSerializer(serializers.Serializer[Any]):
    name = serializers.CharField()
    required_attributes = GuidelineTaxonomyAttributeSerializer(
        many=True, required=False, default=list
    )


class GuidelineTaxonomyDefinitionSerializer(serializers.Serializer[Any]):
    version = serializers.CharField()
    labels = GuidelineTaxonomyLabelSerializer(many=True, allow_empty=False)


class GuidelineFileSerializer(serializers.Serializer[Any]):
    content = serializers.CharField(max_length=1_000_000, trim_whitespace=False)


class GuidelinePreviewRuleSerializer(serializers.Serializer[Any]):
    rule_id = serializers.CharField()
    section = serializers.CharField()


class GuidelinePreviewSerializer(serializers.Serializer[Any]):
    version = serializers.CharField()
    name = serializers.CharField()
    rules = GuidelinePreviewRuleSerializer(many=True)
    taxonomy = GuidelineTaxonomyDefinitionSerializer(allow_null=True)


class GuidelineImportSerializer(GuidelineFileSerializer):
    taxonomy = GuidelineTaxonomyDefinitionSerializer(required=False)


class GuidelineImportResultSerializer(serializers.Serializer[Any]):
    version = serializers.CharField()
    checksum = serializers.CharField()
    taxonomy = GuidelineTaxonomyDefinitionSerializer()
    skipped = serializers.BooleanField()


class DatasetGuidelineSerializer(serializers.Serializer[Any]):
    dataset_id = serializers.IntegerField()
    guideline_version = serializers.CharField(allow_null=True)
    guideline_checksum = serializers.CharField(allow_null=True)
    taxonomy_version = serializers.CharField(allow_null=True)
    taxonomy_ready = serializers.BooleanField()
    revision = serializers.IntegerField()


class DatasetGuidelineUpdateSerializer(serializers.Serializer[Any]):
    guideline_version = serializers.CharField(max_length=32)
    expected_revision = serializers.IntegerField(min_value=0)


def binding_data(dataset_id: int, binding: DatasetGuideline | None) -> dict[str, Any]:
    guideline = binding.guideline if binding else None
    return {
        "dataset_id": dataset_id,
        "guideline_version": guideline.version_tag if guideline else None,
        "guideline_checksum": guideline.file_checksum if guideline else None,
        "taxonomy_version": guideline.taxonomy.get("version") if guideline else None,
        "taxonomy_ready": bool(guideline and guideline.taxonomy),
        "revision": binding.revision if binding else 0,
    }


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class GuidelineImportView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.QC_ADMIN, Role.SUPER_ADMIN)
    action_name = "guidelines.import"
    object_type = "guideline"
    requires_dataset = False

    @extend_schema(
        operation_id="guidelines_import",
        extensions={"x-labelx-trace": ["FR-GDL-02"], "x-labelx-roles": ["qc_admin", "super_admin"]},
        request=GuidelineImportSerializer,
        responses={
            200: GuidelineImportResultSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
        },
        tags=["guidelines"],
    )
    def post(self, request: Request) -> Response:
        serializer = GuidelineImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def audit_import(version: GuidelineVersion, skipped: bool) -> None:
            append_action_audit(
                request=request,
                action="guideline.import",
                object_type="guideline",
                object_id=version.pk,
                after={
                    "version": version.version_tag,
                    "checksum": version.file_checksum,
                    "skipped": skipped,
                },
                revision=version.file_checksum,
            )

        try:
            version, skipped = load_guideline(
                serializer.validated_data["content"].encode("utf-8"),
                cast(User, request.user).username,
                on_loaded=audit_import,
                manual_taxonomy=serializer.validated_data.get("taxonomy"),
                require_taxonomy=True,
            )
        except CommandError as exc:
            raise ApiError(400, "VALIDATION_ERROR", str(exc)) from exc
        return Response(
            {
                "version": version.version_tag,
                "checksum": version.file_checksum,
                "taxonomy": version.taxonomy,
                "skipped": skipped,
            }
        )


class DatasetGuidelineView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles: tuple[Role, ...] = (Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN, Role.REVIEWER)
    action_name = "datasets.guideline"
    object_type = "dataset"
    requires_dataset = True

    def get_dataset_id(self, request: Request) -> int:
        return int(self.kwargs["id"])

    def get_permissions(self) -> list[HasRoleAndDatasetScope]:
        if self.request.method == "PUT":
            self.allowed_roles = (Role.QC_ADMIN, Role.SUPER_ADMIN)
        return super().get_permissions()  # type: ignore[return-value]

    @extend_schema(
        operation_id="datasets_guideline_retrieve",
        extensions={
            "x-labelx-trace": ["FR-SNP-03", "FR-GDL-02"],
            "x-labelx-roles": ["qa_lead", "qc_admin", "super_admin", "reviewer"],
        },
        responses={200: DatasetGuidelineSerializer, 403: ErrorSerializer},
        tags=["datasets"],
    )
    def get(self, request: Request, id: int) -> Response:
        binding = DatasetGuideline.objects.select_related("guideline").filter(dataset_id=id).first()
        return Response(binding_data(id, binding))

    @extend_schema(
        operation_id="datasets_guideline_update",
        extensions={
            "x-labelx-trace": ["FR-SNP-03", "FR-GDL-02"],
            "x-labelx-roles": ["qc_admin", "super_admin"],
        },
        request=DatasetGuidelineUpdateSerializer,
        responses={
            200: DatasetGuidelineSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
            502: ErrorSerializer,
        },
        tags=["datasets"],
    )
    def put(self, request: Request, id: int) -> Response:
        serializer = DatasetGuidelineUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        guideline = GuidelineVersion.objects.filter(version_tag=data["guideline_version"]).first()
        if guideline is None or not guideline.taxonomy:
            raise ApiError(400, "VALIDATION_ERROR", "Chọn Guideline đã import taxonomy.")
        client = _client()
        try:
            client.get_project(id)
            bind_taxonomy(
                id, client.list_labels(project_id=id), guideline_version=guideline.version_tag
            )
        except GuidelineBindingError as exc:
            raise ApiError(400, "VALIDATION_ERROR", str(exc)) from exc
        except httpx.HTTPError as exc:
            raise ApiError(502, "BUSINESS_RULE_UNMET", "Không đọc được Dataset CVAT.") from exc
        finally:
            client.close()
        try:
            with transaction.atomic():
                binding = DatasetGuideline.objects.select_for_update().filter(dataset_id=id).first()
                before = binding_data(id, binding)
                if data["expected_revision"] != before["revision"]:
                    raise ApiError(
                        409, "INVALID_TRANSITION", "Mapping đã thay đổi. Tải lại để tiếp tục."
                    )
                if binding:
                    binding.guideline = guideline
                    binding.revision += 1
                    binding.updated_by = cast(User, request.user)
                    binding.save()
                else:
                    binding = DatasetGuideline.objects.create(
                        dataset_id=id, guideline=guideline, updated_by=cast(User, request.user)
                    )
                after = binding_data(id, binding)
                append_action_audit(
                    request=request,
                    action="dataset.guideline.update",
                    object_type="dataset",
                    object_id=id,
                    before=before,
                    after=after,
                    revision=str(binding.revision),
                )
        except IntegrityError as exc:
            raise ApiError(
                409, "INVALID_TRANSITION", "Mapping đã thay đổi. Tải lại để tiếp tục."
            ) from exc
        return Response(after)


class GuidelinePreviewView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.QC_ADMIN, Role.SUPER_ADMIN)
    action_name = "guidelines.preview"
    object_type = "guideline"
    requires_dataset = False

    @extend_schema(
        operation_id="guidelines_preview",
        extensions={"x-labelx-trace": ["FR-GDL-02"], "x-labelx-roles": ["qc_admin", "super_admin"]},
        request=GuidelineFileSerializer,
        responses={200: GuidelinePreviewSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
        tags=["guidelines"],
    )
    def post(self, request: Request) -> Response:
        serializer = GuidelineFileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            preview = preview_guideline(serializer.validated_data["content"].encode("utf-8"))
        except CommandError as exc:
            raise ApiError(400, "VALIDATION_ERROR", str(exc)) from exc
        return Response(preview)
