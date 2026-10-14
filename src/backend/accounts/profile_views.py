"""Authenticated users may save only their own encrypted CVAT token."""

from typing import Any, cast

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import CvatProfile
from audit.services import append_audit_event
from config.serializers import ErrorSerializer
from cvat_adapter.credentials import credential_cipher


class ProfileSerializer(serializers.Serializer[dict[str, Any]]):
    cvat_token_configured = serializers.BooleanField()
    cvat_token_saved = serializers.BooleanField()


class ProfileUpdateSerializer(serializers.Serializer[dict[str, Any]]):
    cvat_service_token = serializers.CharField(
        write_only=True, max_length=4096, trim_whitespace=False
    )

    def validate_cvat_service_token(self, value: str) -> str:
        if not value.isascii() or any(ord(c) < 33 or ord(c) == 127 for c in value):
            raise serializers.ValidationError("Token CVAT chứa ký tự không hợp lệ.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if set(self.initial_data) != {"cvat_service_token"}:
            raise serializers.ValidationError("Chỉ được cập nhật token CVAT của bạn.")
        return attrs


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="auth_profile_retrieve",
        tags=["auth"],
        responses={200: ProfileSerializer, 403: ErrorSerializer},
    )
    def get(self, request: Request) -> Response:
        configured = CvatProfile.objects.filter(user=cast(User, request.user)).exists()
        return Response(
            {
                "cvat_token_configured": configured or bool(settings.CVAT_SERVICE_TOKEN),
                "cvat_token_saved": configured,
            },
            headers={"Cache-Control": "no-store"},
        )

    @extend_schema(
        operation_id="auth_profile_update",
        tags=["auth"],
        request=ProfileUpdateSerializer,
        responses={200: ProfileSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
    )
    def patch(self, request: Request) -> Response:
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        encrypted = (
            credential_cipher()
            .encrypt(serializer.validated_data["cvat_service_token"].encode())
            .decode()
        )
        with transaction.atomic():
            CvatProfile.objects.update_or_create(
                user=cast(User, request.user), defaults={"encrypted_token": encrypted}
            )
            append_audit_event(
                actor=cast(User, request.user),
                action="profile.cvat_token.update",
                object_type="user",
                object_id=request.user.pk,
                before=None,
                revision="saved",
                after={"cvat_token_configured": True},
            )
        return Response(
            {"cvat_token_configured": True, "cvat_token_saved": True},
            headers={"Cache-Control": "no-store"},
        )

    @extend_schema(
        operation_id="auth_profile_token_delete",
        tags=["auth"],
        responses={200: ProfileSerializer, 403: ErrorSerializer},
    )
    def delete(self, request: Request) -> Response:
        user = cast(User, request.user)
        with transaction.atomic():
            deleted, _ = CvatProfile.objects.filter(user=user).delete()
            if deleted:
                append_audit_event(
                    actor=user,
                    action="profile.cvat_token.delete",
                    object_type="user",
                    object_id=user.pk,
                    before=None,
                    after={"cvat_token_saved": False},
                    revision="deleted",
                )
        return Response(
            {"cvat_token_configured": bool(settings.CVAT_SERVICE_TOKEN), "cvat_token_saved": False},
            headers={"Cache-Control": "no-store"},
        )
