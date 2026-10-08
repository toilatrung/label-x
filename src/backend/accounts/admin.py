"""Django Admin cho accounts — chỉ xem, tránh bypass service/audit.

Nguyên tắc (F-1):
- EmployeeIdentity và trường CvatIdentity.employee KHÔNG được thêm/sửa/xóa qua admin.
- Mọi thay đổi phải đi qua assign_employee_identity() để đảm bảo transaction, audit và kiểm quyền.
- Admin chỉ dùng để tra cứu và kiểm toán; không phải kênh cấp quyền.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from accounts.models import CvatIdentity, EmployeeIdentity, RoleAssignment


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["user", "role", "dataset_id", "created_at"]
    list_filter = ["role"]
    search_fields = ["user__username"]


@admin.register(EmployeeIdentity)
class EmployeeIdentityAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """EmployeeIdentity: CHỈ XEM — mọi thay đổi phải qua assign_employee_identity()."""

    list_display = ["employee_id", "display_name", "verified_at", "verified_by", "created_at"]
    search_fields = ["employee_id", "display_name", "verified_by__username"]
    list_filter = ["verified_at"]
    readonly_fields = [
        "employee_id",
        "display_name",
        "verified_at",
        "verified_by",
        "created_at",
        "updated_at",
    ]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(CvatIdentity)
class CvatIdentityAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """CvatIdentity: trường employee CHỈ XEM — gán qua assign_employee_identity()."""

    list_display = ["user", "cvat_user_id", "cvat_username", "employee", "updated_at"]
    search_fields = ["user__username", "cvat_username", "employee__employee_id"]
    readonly_fields = ["employee", "updated_at"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
