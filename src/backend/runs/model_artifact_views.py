"""Read the registered detector catalog used by versioned QC configurations."""

from io import StringIO
from typing import Any

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import HasRoleAndDatasetScope, append_action_audit
from config.exceptions import ApiError
from config.serializers import ErrorSerializer
from runs.gpu_worker_views import WorkerAdminView
from runs.models import ModelArtifact


class RegisteredDetectorSerializer(serializers.ModelSerializer[Any]):
    class Meta:
        model = ModelArtifact
        fields = ("id", "name", "version", "checksum", "class_mapping_version", "class_mapping")
        read_only_fields = fields


class ModelArtifactListView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN)
    action_name = "model_artifacts.list"
    object_type = "model_artifact"
    requires_dataset = False

    @extend_schema(
        operation_id="model_artifacts_list",
        extensions={
            "x-labelx-trace": ["FR-ENG-01", "FR-ENG-05"],
            "x-labelx-roles": ["qa_lead", "qc_admin", "super_admin"],
        },
        responses={200: RegisteredDetectorSerializer(many=True), 403: ErrorSerializer},
        tags=["config"],
    )
    def get(self, request: Request) -> Response:
        return Response(RegisteredDetectorSerializer(ModelArtifact.objects.all(), many=True).data)


class ModelArtifactRegisterView(WorkerAdminView):
    action_name = "model_artifacts.register"
    object_type = "model_artifact"

    @extend_schema(
        operation_id="model_artifacts_register",
        extensions={
            "x-labelx-trace": ["FR-ENG-01", "FR-ENG-05", "FR-SEC-01"],
            "x-labelx-roles": ["qc_admin", "super_admin"],
        },
        request=None,
        responses={
            200: RegisteredDetectorSerializer(many=True),
            400: ErrorSerializer,
            403: ErrorSerializer,
            503: ErrorSerializer,
        },
        tags=["config"],
    )
    def post(self, request: Request) -> Response:
        if request.data:
            raise ApiError(400, "VALIDATION_ERROR", "Model được đọc từ manifest trên server.")
        try:
            with transaction.atomic():
                call_command("check_detector", register=True, stdout=StringIO())
                data = RegisteredDetectorSerializer(ModelArtifact.objects.all(), many=True).data
                append_action_audit(
                    request=request,
                    action=self.action_name,
                    object_type=self.object_type,
                    object_id="catalog",
                    before=None,
                    after={"registered_ids": [model["id"] for model in data]},
                )
        except CommandError:
            raise ApiError(
                503,
                "SERVICE_UNAVAILABLE",
                "Không xác minh được model. Kiểm tra manifest, worker, checksum và ánh xạ lớp.",
            ) from None
        return Response(data)
