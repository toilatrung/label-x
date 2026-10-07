from django.contrib import admin

from accounts.models import CvatIdentity, RoleAssignment


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["user", "role", "dataset_id", "created_at"]
    list_filter = ["role"]
    search_fields = ["user__username"]


@admin.register(CvatIdentity)
class CvatIdentityAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["user", "cvat_user_id", "cvat_username", "updated_at"]
    search_fields = ["user__username", "cvat_username"]
