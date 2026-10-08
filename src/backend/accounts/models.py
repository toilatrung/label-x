"""Vai trò theo scope dataset và identity mapping LabelX ↔ CVAT (E-02, T-011).

Người dùng là `django.contrib.auth.models.User`. Vai trò và scope theo
docs/04-api/rbac-matrix.html; contract `RoleAssignment`, `Session` trong docs/04-api/openapi.yaml.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower


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


class EmployeeIdentity(models.Model):
    """Định danh nhân sự ổn định liên kết nhiều LabelX/CVAT account về cùng một thể nhân.

    Thiết kế (F-1 fix, T-012):
    - employee_id do quản trị nội bộ cấp (HR/IT), KHÔNG cho phép người dùng tự khai báo.
    - Chuẩn hóa: không phân biệt hoa thường (EMP-001 và emp-001 là cùng một định danh),
      được bảo vệ bằng UniqueConstraint(Lower('employee_id')).
    - verified_at/verified_by ghi nhận xác minh thực thể; chỉ SUPER_ADMIN/QC_ADMIN được ghi.
    - is_verified đúng khi CÓ CẢ verified_at và verified_by (constraint bảo đảm hai trường
      cùng null hoặc cùng có giá trị).
    - Nhiều CvatIdentity có thể trỏ tới cùng EmployeeIdentity (quan hệ nhiều-1).
    - Dữ liệu cũ chưa đối soát giữ FK null trên CvatIdentity; không backfill tự động.
    - Account chưa được gán EmployeeIdentity đã xác minh không được phê duyệt (fail-closed).
    - verified_by dùng PROTECT: không xóa người xác minh âm thầm.
    - CvatIdentity.employee dùng PROTECT: không xóa EmployeeIdentity khi đang được liên kết.
    """

    employee_id = models.CharField(
        max_length=128,
        unique=True,
        help_text=(
            "Định danh nhân sự ổn định do quản trị nội bộ cấp (HR/IT). "
            "Không cho phép người dùng tự khai báo hoặc tự sửa."
        ),
    )
    display_name = models.CharField(max_length=255, blank=True)
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Thời điểm xác minh mapping. Null = chưa xác minh.",
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="employee_verifications",
        help_text=(
            "SUPER_ADMIN/QC_ADMIN đã xác minh mapping này. "
            "PROTECT: không được xóa người xác minh khi còn mapping."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["employee_id"]
        constraints = [
            # verified_at và verified_by phải cùng null hoặc cùng có giá trị.
            models.CheckConstraint(
                condition=(
                    models.Q(verified_at__isnull=True, verified_by__isnull=True)
                    | models.Q(verified_at__isnull=False, verified_by__isnull=False)
                ),
                name="accounts_employee_identity_verified_fields_consistent",
            ),
            # Chuẩn hóa không phân biệt hoa thường ở mức database
            models.UniqueConstraint(
                Lower("employee_id"),
                name="accounts_employee_identity_employee_id_ci_unique",
            ),
        ]

    def __str__(self) -> str:
        status_label = "verified" if self.is_verified else "unverified"
        return f"Employee({self.employee_id}) [{status_label}]"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.employee_id:
            self.employee_id = self.employee_id.strip()
        super().save(*args, **kwargs)

    @property
    def is_verified(self) -> bool:
        """True khi CÓ CẢ verified_at và verified_by (cùng null = chưa xác minh)."""
        return self.verified_at is not None and self.verified_by_id is not None


class CvatIdentity(models.Model):
    """Identity mapping LabelX ↔ người dùng CVAT, dùng cho kiểm self-review (FR-SEC-02).

    employee: nullable FK tới EmployeeIdentity. Nhiều CvatIdentity có thể trỏ tới cùng
    EmployeeIdentity để phát hiện đa tài khoản của cùng nhân sự. Account cũ chưa đối soát
    giữ employee=None -- không được phép phê duyệt cho đến khi được xác minh (fail-closed).
    PROTECT: không được phép xóa EmployeeIdentity khi đang có CvatIdentity liên kết.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cvat_identity"
    )
    cvat_user_id = models.PositiveIntegerField(unique=True)
    cvat_username = models.CharField(max_length=150, blank=True)
    employee = models.ForeignKey(
        EmployeeIdentity,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cvat_identities",
        help_text=(
            "Liên kết tới EmployeeIdentity. Null = chưa đối soát; "
            "không được phép phê duyệt khi null (fail-closed). "
            "PROTECT: không được xóa EmployeeIdentity khi còn CvatIdentity trỏ tới."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        emp = f" emp={self.employee.employee_id}" if self.employee else ""
        return f"{self.user} ↔ CVAT #{self.cvat_user_id}{emp}"
