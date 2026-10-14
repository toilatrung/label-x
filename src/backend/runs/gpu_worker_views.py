"""System-admin configuration API; stores credential references, never credential values."""

from typing import Any

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role, RoleAssignment
from accounts.permissions import HasRoleAndDatasetScope, append_action_audit
from config.exceptions import ApiError
from config.serializers import ErrorSerializer
from runs.gpu_worker import credential, probe, selected, validate_url
from runs.models import GpuWorkerConfig, GpuWorkerSelection


class WorkerConfigSerializer(serializers.Serializer[Any]):
    revision = serializers.IntegerField(min_value=0)
    name = serializers.CharField(max_length=128)
    url = serializers.CharField(max_length=255)
    credential_ref = serializers.CharField(max_length=64)
    enabled = serializers.BooleanField()
    timeout_seconds = serializers.IntegerField(min_value=10, max_value=1800)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError(
                "Chỉ chấp nhận các field đã khai báo; không gửi token."
            )
        try:
            attrs["url"] = validate_url(attrs["url"])
            credential(attrs["credential_ref"])
        except (ValueError, RuntimeError) as exc:
            raise serializers.ValidationError(str(exc)) from None
        return attrs


class WorkerEnvelopeSerializer(serializers.Serializer[Any]):
    config = WorkerConfigSerializer(allow_null=True)
    credential_refs = serializers.ListField(child=serializers.CharField())
    allowed_hosts = serializers.ListField(child=serializers.CharField())


class WorkerProbeRequestSerializer(serializers.Serializer[Any]):
    revision = serializers.IntegerField(min_value=1)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if set(self.initial_data) != {"revision"}:
            raise serializers.ValidationError("Chỉ gửi revision của cấu hình đã lưu.")
        return attrs


class WorkerModelSerializer(serializers.Serializer[Any]):
    sha256 = serializers.CharField()
    version = serializers.CharField()
    class_mapping_version = serializers.CharField()
    verified = serializers.BooleanField()


class WorkerProbeSerializer(serializers.Serializer[Any]):
    revision = serializers.IntegerField()
    state = serializers.ChoiceField(choices=["ready", "unavailable", "disabled"])
    message = serializers.CharField()
    checked_at = serializers.DateTimeField()
    latency_ms = serializers.IntegerField(allow_null=True)
    device = serializers.CharField(allow_null=True)
    model = WorkerModelSerializer(allow_null=True)


def envelope(config: GpuWorkerConfig | None) -> dict[str, Any]:
    from django.conf import settings

    return {
        "config": None
        if config is None
        else {
            "revision": config.pk,
            "name": config.name,
            "url": config.url,
            "credential_ref": config.credential_ref,
            "enabled": config.enabled,
            "timeout_seconds": config.timeout_seconds,
        },
        "credential_refs": sorted(settings.GPU_WORKER_CREDENTIALS),
        "allowed_hosts": sorted(settings.GPU_WORKER_ALLOWED_HOSTS),
    }


class WorkerAdminView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = (Role.SUPER_ADMIN, Role.QC_ADMIN)
    requires_dataset = False
    scope_type = "system"
    action_name = "gpu_worker.configure"
    object_type = "gpu_worker"

    def check_permissions(self, request: Request) -> None:
        super().check_permissions(request)
        if not RoleAssignment.objects.filter(
            user_id=int(request.user.pk or 0), role__in=self.allowed_roles, dataset_id__isnull=True
        ).exists():
            raise ApiError(
                403, "FORBIDDEN", "Cần quyền quản trị toàn hệ thống để cấu hình GPU Worker."
            )


class WorkerConfigView(WorkerAdminView):
    @extend_schema(
        operation_id="gpu_worker_config_retrieve",
        extensions={
            "x-labelx-trace": ["FR-ENG-01", "FR-ENG-05", "FR-SEC-01"],
            "x-labelx-roles": ["super_admin", "qc_admin"],
        },
        responses={200: WorkerEnvelopeSerializer, 403: ErrorSerializer},
        tags=["gpu-worker"],
    )
    def get(self, request: Request) -> Response:
        return Response(envelope(selected()))

    @extend_schema(
        operation_id="gpu_worker_config_update",
        extensions={
            "x-labelx-trace": ["FR-ENG-01", "FR-ENG-05", "FR-SEC-01", "FR-SEC-05"],
            "x-labelx-roles": ["super_admin", "qc_admin"],
        },
        request=WorkerConfigSerializer,
        responses={
            200: WorkerEnvelopeSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
        tags=["gpu-worker"],
    )
    def put(self, request: Request) -> Response:
        payload = WorkerConfigSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        expected = data.pop("revision")
        with transaction.atomic():
            GpuWorkerSelection.objects.get_or_create(pk=1)
            pointer = GpuWorkerSelection.objects.select_for_update().get(pk=1)
            if (pointer.config_id or 0) != expected:
                raise ApiError(
                    409, "INVALID_TRANSITION", "Cấu hình đã thay đổi; hãy tải lại trước khi lưu."
                )
            before = envelope(pointer.config)["config"]
            config = GpuWorkerConfig.objects.create(**data)
            pointer.config = config
            pointer.save(update_fields=["config"])
            append_action_audit(
                request=request,
                action="gpu_worker.configure",
                object_type="gpu_worker",
                object_id=config.pk,
                before=before,
                after=envelope(config)["config"],
                revision=str(config.pk),
            )
        return Response(envelope(config))


class WorkerProbeView(WorkerAdminView):
    @extend_schema(
        operation_id="gpu_worker_probe",
        extensions={
            "x-labelx-trace": ["FR-ENG-05", "FR-SEC-01"],
            "x-labelx-roles": ["super_admin", "qc_admin"],
        },
        request=WorkerProbeRequestSerializer,
        responses={
            200: WorkerProbeSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
        tags=["gpu-worker"],
    )
    def post(self, request: Request) -> Response:
        payload = WorkerProbeRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        config = selected()
        if config is None or config.pk != payload.validated_data["revision"]:
            raise ApiError(409, "INVALID_TRANSITION", "Cấu hình đã thay đổi; hãy tải lại.")
        return Response(probe(config))
