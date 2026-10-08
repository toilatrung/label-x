"""Django Admin cho guideline (T-017, FR-SEC-05).

GuidelineLoadRecord, GuidelineVersion, GuidelineRule, RuleMapping:
Chỉ xem; không có thao tác thêm/sửa/xóa qua Admin để bảo đảm tính toàn vẹn
và bất biến của cấu hình guideline và nhật ký nạp.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from guideline.models import GuidelineLoadRecord, GuidelineRule, GuidelineVersion, RuleMapping


@admin.register(GuidelineLoadRecord)
class GuidelineLoadRecordAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["actor_username", "result", "file_checksum", "row_count", "attempted_at"]
    search_fields = ["actor_username", "file_checksum"]
    list_filter = ["result", "attempted_at"]
    readonly_fields = [
        "actor_username",
        "actor",
        "attempted_at",
        "file_checksum",
        "row_count",
        "result",
        "errors",
    ]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(GuidelineVersion)
class GuidelineVersionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["version_tag", "name", "file_checksum", "loaded_at"]
    search_fields = ["version_tag", "name", "file_checksum"]
    readonly_fields = ["version_tag", "name", "file_checksum", "loaded_at"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(GuidelineRule)
class GuidelineRuleAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["rule_id", "version", "section", "content"]
    search_fields = ["rule_id", "content"]
    list_filter = ["version"]
    readonly_fields = ["rule_id", "version", "section", "content"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(RuleMapping)
class RuleMappingAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["version", "error_group", "class_name", "paired_class", "rule"]
    list_filter = ["version", "error_group"]
    search_fields = ["class_name", "paired_class", "rule__rule_id"]
    readonly_fields = ["version", "error_group", "class_name", "paired_class", "rule"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
