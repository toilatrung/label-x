"""Serializer theo schema `LoginRequest`, `Session`, `RoleAssignment` của contract."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from rest_framework import serializers

from accounts.models import CvatIdentity, Role, RoleAssignment


class LoginRequestSerializer(serializers.Serializer[dict[str, Any]]):
    username = serializers.CharField(trim_whitespace=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class RoleAssignmentSerializer(serializers.Serializer[dict[str, Any]]):
    role = serializers.ChoiceField(choices=Role.choices)
    dataset_id = serializers.IntegerField(allow_null=True)


class SessionUserSerializer(serializers.Serializer[dict[str, Any]]):
    id = serializers.IntegerField()
    username = serializers.CharField()
    display_name = serializers.CharField()


class IdentityMappingSerializer(serializers.Serializer[dict[str, Any]]):
    status = serializers.ChoiceField(choices=["mapped", "missing"])
    cvat_user_id = serializers.IntegerField(allow_null=True, required=False)


class SessionSerializer(serializers.Serializer[dict[str, Any]]):
    user = SessionUserSerializer()
    roles = RoleAssignmentSerializer(many=True)
    identity_mapping = IdentityMappingSerializer()


def build_session(user: AbstractBaseUser | AnonymousUser) -> dict[str, Any]:
    """Dữ liệu `Session` cho người dùng đã đăng nhập."""
    full_name = user.get_full_name().strip() if hasattr(user, "get_full_name") else ""
    roles = [
        {"role": a.role, "dataset_id": a.dataset_id}
        for a in RoleAssignment.objects.filter(user_id=user.pk or 0).order_by("id")
    ]
    identity = CvatIdentity.objects.filter(user_id=user.pk or 0).first()
    mapping: dict[str, Any] = (
        {"status": "mapped", "cvat_user_id": identity.cvat_user_id}
        if identity
        else {"status": "missing", "cvat_user_id": None}
    )
    return {
        "user": {
            "id": user.pk,
            "username": user.get_username(),
            "display_name": full_name or user.get_username(),
        },
        "roles": roles,
        "identity_mapping": mapping,
    }


class WorkflowRuleSerializer(serializers.Serializer[dict[str, Any]]):
    rule = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    enforced = serializers.BooleanField()


class WorkflowPermissionsSerializer(serializers.Serializer[dict[str, Any]]):
    matrix = serializers.ListField(child=serializers.DictField())
    rules = WorkflowRuleSerializer(many=True)
    user_roles = RoleAssignmentSerializer(many=True)
