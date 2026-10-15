"""Read the registered detector catalog used by versioned QC configurations."""

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import HasRoleAndDatasetScope
from config.serializers import ErrorSerializer
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
