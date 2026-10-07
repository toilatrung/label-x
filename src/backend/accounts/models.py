"""Vai trò theo scope dataset và identity mapping LabelX ↔ CVAT (E-02, T-011).

Người dùng là `django.contrib.auth.models.User`. Vai trò và scope theo
docs/04-api/rbac-matrix.html; contract `RoleAssignment`, `Session` trong docs/04-api/openapi.yaml.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Role(models.TextChoices):
    """Enum `Role` của contract (SRS tab:rbac và đoạn sau bảng)."""

    ANNOTATOR = "annotator", "Annotator"
    REVIEWER = "reviewer", "Reviewer"
    QA_LEAD = "qa_lead", "QA Lead"
    QC_ADMIN = "qc_admin", "QC Admin"
    SUPER_ADMIN = "super_admin", "Super Admin"
    PRODUCT_OWNER = "product_owner", "Product Owner"
    DATA_MODEL_OWNER = "data_model_owner", "Data/Model Owner"


# Chỉ hai vai trò này được có scope toàn hệ thống (dataset_id = null), rbac-matrix.html §1.
SYSTEM_WIDE_ROLES = (Role.SUPER_ADMIN, Role.QC_ADMIN)


class RoleAssignment(models.Model):
    """Một cặp (vai trò, dataset) của người dùng; một người có thể có nhiều bản ghi."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_assignments"
    )
    role = models.CharField(max_length=32, choices=Role.choices)
    # Dataset chưa có model (E-04/E-05); giữ id để T-012 kiểm scope, nối FK khi có model Dataset.
    dataset_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role", "dataset_id"],
                name="accounts_role_assignment_unique",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=models.Q(dataset_id__isnull=False)
                | models.Q(role__in=[r.value for r in SYSTEM_WIDE_ROLES]),
                name="accounts_role_assignment_system_wide_roles",
            ),
        ]

    def __str__(self) -> str:
        scope = "toàn hệ thống" if self.dataset_id is None else f"dataset {self.dataset_id}"
        return f"{self.user} — {self.role} ({scope})"


class CvatIdentity(models.Model):
    """Identity mapping LabelX ↔ người dùng CVAT, dùng cho kiểm self-review (FR-SEC-02)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cvat_identity"
    )
    cvat_user_id = models.PositiveIntegerField(unique=True)
    cvat_username = models.CharField(max_length=150, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user} ↔ CVAT #{self.cvat_user_id}"
