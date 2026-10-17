"""Configuration/guidelines VLM connection API; never serializes credentials."""

import math
from typing import Any, cast
from urllib.parse import urlparse

from django.contrib.auth.models import User
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import HasRoleAndDatasetScope
from audit.services import append_audit_event
from config.exceptions import ApiError
from config.serializers import ErrorSerializer
from orchestration.routing_policy import DEFAULT_SCORE_THRESHOLD
from runs.models import VlmConfiguration, VlmConnection
from vlm.config import (
    ALLOWED_MODELS,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MODEL,
    HOST_PROVIDER,
    default_api_key_env,
    validate_vlm_config,
)
from vlm.connection import credential_cipher


class VlmSettingsSerializer(serializers.Serializer[dict[str, Any]]):
    revision = serializers.IntegerField()
    base_url = serializers.CharField()
    model = serializers.ChoiceField(choices=sorted(ALLOWED_MODELS))
    api_key_configured = serializers.BooleanField()
    confidence_threshold = serializers.FloatField()


class VlmSettingsUpdateSerializer(serializers.Serializer[dict[str, Any]]):
    expected_revision = serializers.IntegerField(min_value=0)
    base_url = serializers.CharField(max_length=512)
    model = serializers.ChoiceField(choices=sorted(ALLOWED_MODELS))
    api_key = serializers.CharField(write_only=True, required=False, max_length=4096)
    confidence_threshold = serializers.FloatField(required=False, min_value=0, max_value=1)

    def validate_confidence_threshold(self, value: float) -> float:
        if isinstance(self.initial_data.get("confidence_threshold"), bool) or not math.isfinite(
            value
        ):
            raise serializers.ValidationError("Ngưỡng tin cậy phải là số trong [0, 1].")
        return value

    def validate_api_key(self, value: str) -> str:
        if not value.isascii() or any(c.isspace() or ord(c) < 33 or ord(c) == 127 for c in value):
            raise serializers.ValidationError("API key chứa ký tự không hợp lệ.")
        return value


def public_settings(connection: VlmConnection | None) -> dict[str, Any]:
    return {
        "revision": connection.pk if connection else 0,
        "base_url": connection.config["base_url"] if connection else "https://api.shopaikey.com/v1",
        "model": connection.config["model"] if connection else DEFAULT_MODEL,
        "api_key_configured": bool(connection and connection.encrypted_api_key),
        "confidence_threshold": (
            connection.confidence_threshold if connection else DEFAULT_SCORE_THRESHOLD
        ),
    }


class VlmSettingsView(APIView):
    permission_classes = [HasRoleAndDatasetScope]
    requires_dataset = False
    allowed_roles: tuple[Role, ...] = (Role.QC_ADMIN, Role.SUPER_ADMIN)
    action_name = "vlm_settings.update"
    object_type = "vlm_configuration"

    def get_permissions(self) -> list[Any]:
        self.allowed_roles = (
            (Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN)
            if self.request.method == "GET"
            else (Role.QC_ADMIN, Role.SUPER_ADMIN)
        )
        return list(super().get_permissions())

    @extend_schema(
        operation_id="vlm_settings_retrieve",
        responses={
            200: VlmSettingsSerializer,
            403: ErrorSerializer,
        },
        tags=["config"],
    )
    def get(self, request: Request) -> Response:
        pointer = VlmConfiguration.objects.select_related("connection").filter(pk=1).first()
        return Response(
            public_settings(pointer.connection if pointer else None),
            headers={"Cache-Control": "no-store"},
        )

    @extend_schema(
        operation_id="vlm_settings_update",
        request=VlmSettingsUpdateSerializer,
        responses={
            200: VlmSettingsSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
        tags=["config"],
    )
    def patch(self, request: Request) -> Response:
        serializer = VlmSettingsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        base_url = data["base_url"].rstrip("/")
        try:
            host = urlparse(base_url).hostname or ""
        except ValueError:
            raise ApiError(400, "VALIDATION_ERROR", "Base URL không hợp lệ.") from None
        config = {
            "provider": HOST_PROVIDER.get(host, ""),
            "base_url": base_url,
            "model": data["model"],
            "api_key_env": default_api_key_env(base_url),
            "prompt_version": "vlm-prompt-v0",
            "timeout_seconds": 60,
            "max_attempts": DEFAULT_MAX_ATTEMPTS,
            "budget": {"max_calls": 200},
        }
        errors = validate_vlm_config(config)
        if errors:
            raise ApiError(400, "VALIDATION_ERROR", " ".join(errors))
        with transaction.atomic():
            VlmConfiguration.objects.get_or_create(pk=1)
            pointer = VlmConfiguration.objects.select_for_update().get(pk=1)
            previous = pointer.connection
            if data["expected_revision"] != (pointer.connection_id or 0):
                raise ApiError(409, "INVALID_TRANSITION", "Cấu hình đã đổi. Tải lại trước khi lưu.")
            api_key = data.get("api_key")
            if api_key:
                encrypted = credential_cipher().encrypt(api_key.encode()).decode()
            elif previous and previous.config["base_url"] == base_url:
                encrypted = previous.encrypted_api_key
            else:
                raise ApiError(400, "VALIDATION_ERROR", "Nhập API key khi tạo hoặc đổi Base URL.")
            connection = VlmConnection.objects.create(
                config=config,
                encrypted_api_key=encrypted,
                confidence_threshold=data.get(
                    "confidence_threshold",
                    previous.confidence_threshold if previous else DEFAULT_SCORE_THRESHOLD,
                ),
            )
            pointer.connection = connection
            pointer.save(update_fields=["connection"])
            append_audit_event(
                actor=cast(User, request.user),
                action="vlm_settings.update",
                object_type="vlm_configuration",
                object_id=1,
                before=public_settings(previous),
                after=public_settings(connection),
                revision=str(connection.pk),
            )
        return Response(public_settings(connection), headers={"Cache-Control": "no-store"})
