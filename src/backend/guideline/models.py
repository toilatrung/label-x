"""Models cho module GDL — Tra cứu guideline.

Theo CR-101 (pilot), FR-GDL-01…03 hoãn sang tệp tĩnh có rule ID:
- GuidelineVersion: một phiên bản guideline đã nạp, nhận diện bằng checksum.
- GuidelineRule: một rule trong guideline, có rule_id duy nhất trong phiên bản.
- RuleMapping: ánh xạ (nhóm lỗi, lớp, cặp lớp) → rule (FR-GDL-02).
"""

from django.db import models


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
