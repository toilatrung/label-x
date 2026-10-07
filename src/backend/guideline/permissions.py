"""Permissions cho module GDL (tra cứu guideline)."""

from __future__ import annotations

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request


class HasGuidelineRole(BasePermission):
    """Quyền truy cập guideline (openapi.yaml x-labelx-roles, rbac-matrix.html).

    Vai trò cho phép: reviewer, qa_lead, qc_admin, super_admin.
    Annotator và user thường không có quyền (403 FORBIDDEN).
    Chưa đăng nhập trả về 403 NOT_AUTHENTICATED (xử lý qua exception handler).
    """

    ALLOWED_ROLES = {"reviewer", "qa_lead", "qc_admin", "super_admin"}

    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.groups.filter(name__in=self.ALLOWED_ROLES).exists()
