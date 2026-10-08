"""Models cho module GDL — Tra cứu guideline.

Theo CR-101 (pilot), FR-GDL-01…03 hoãn sang tệp tĩnh có rule ID:
- GuidelineVersion: một phiên bản guideline đã nạp, nhận diện bằng checksum.
- GuidelineRule: một rule trong guideline, có rule_id duy nhất trong phiên bản.
- RuleMapping: ánh xạ (nhóm lỗi, lớp, cặp lớp) → rule (FR-GDL-02).
"""

from __future__ import annotations

import re
from typing import Any

from django.conf import settings
from django.db import models


def get_latest_guideline_version() -> GuidelineVersion | None:
    """Lấy phiên bản guideline mới nhất theo version_tag số học, không phụ thuộc thứ tự nạp."""
    versions = list(GuidelineVersion.objects.all())
    if not versions:
        return None

    def version_sort_key(v: GuidelineVersion) -> tuple[list[int], Any]:
        nums = [int(n) for n in re.findall(r"\d+", v.version_tag)]
        return (nums if nums else [0], v.loaded_at)

    return max(versions, key=version_sort_key)


class GuidelineVersion(models.Model):
    """Phiên bản guideline đã nạp từ tệp."""

    version_tag = models.CharField(max_length=32, unique=True, help_text="Ví dụ: v1")
    name = models.CharField(max_length=200, help_text="Tên hiển thị cho phiên bản")
    loaded_at = models.DateTimeField(auto_now_add=True)
    file_checksum = models.CharField(
        max_length=64,
        unique=True,
        help_text="SHA-256 của tệp guideline, dùng cho idempotency",
    )

    class Meta:
        ordering = ["-loaded_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.version_tag})"


class GuidelineRule(models.Model):
    """Một rule trong guideline (FR-GDL-01)."""

    version = models.ForeignKey(GuidelineVersion, on_delete=models.CASCADE, related_name="rules")
    rule_id = models.CharField(max_length=32, help_text="Ví dụ: VEH-01")
    section = models.CharField(max_length=64, help_text="Ví dụ: §2.1")
    content = models.TextField(help_text="Nội dung trích đoạn của rule")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["version", "rule_id"], name="uq_guideline_rule_version_id"
            ),
        ]
        ordering = ["rule_id"]

    def __str__(self) -> str:
        return f"{self.rule_id} ({self.version.version_tag})"


class RuleMapping(models.Model):
    """Ánh xạ (nhóm lỗi, lớp, cặp lớp) → rule (FR-GDL-02).

    Cho phép Workspace tra rule theo ngữ cảnh: ví dụ nhóm lỗi E2
    với lớp car và cặp lớp truck → quy tắc VEH-01, VEH-03.
    """

    version = models.ForeignKey(GuidelineVersion, on_delete=models.CASCADE, related_name="mappings")
    error_group = models.CharField(
        max_length=16, blank=True, default="", help_text="Nhóm lỗi: E1, E2, E3"
    )
    class_name = models.CharField(
        max_length=64, blank=True, default="", help_text="Tên lớp: car, truck, …"
    )
    paired_class = models.CharField(
        max_length=64, blank=True, default="", help_text="Lớp cặp (nếu có): truck"
    )
    rule = models.ForeignKey(GuidelineRule, on_delete=models.CASCADE, related_name="mappings")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["version", "error_group", "class_name", "paired_class", "rule"],
                name="uq_rule_mapping_context_rule",
            ),
        ]
        ordering = ["error_group", "class_name"]

    def __str__(self) -> str:
        parts = [p for p in [self.error_group, self.class_name, self.paired_class] if p]
        return f"({', '.join(parts)}) → {self.rule.rule_id}"


class GuidelineLoadRecord(models.Model):
    """Append-only record of each guideline load attempt (T-017)."""

    class Result(models.TextChoices):
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        SKIPPED = "skipped", "Skipped"

    actor_username = models.CharField(max_length=150)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="guideline_loads",
    )
    attempted_at = models.DateTimeField(auto_now_add=True)
    file_checksum = models.CharField(max_length=64)
    row_count = models.PositiveIntegerField(default=0)
    result = models.CharField(max_length=16, choices=Result.choices)
    errors = models.JSONField(default=list)

    class Meta:
        ordering = ["-attempted_at", "-id"]

    def __str__(self) -> str:
        return f"{self.actor_username} — {self.result} ({self.file_checksum[:12]})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            raise ValueError("GuidelineLoadRecord is append-only.")
        super().save(*args, **kwargs)
