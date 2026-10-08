"""Dịch vụ quản trị danh tính và định danh nhân sự nội bộ (F-1, T-011, T-012).

Quy tắc bảo mật:
- Chỉ SUPER_ADMIN hoặc QC_ADMIN (RoleAssignment) mới được gọi assign_employee_identity().
  is_staff / is_superuser KHÔNG được dùng làm bypass quyền nghiệp vụ.
- Cấm actor tự gán hoặc tự đổi EmployeeIdentity của chính mình (actor.pk == user.pk).
- Chuẩn hóa employee_id: không phân biệt hoa thường (EMP-001 và emp-001 cùng định danh).
- Mọi thao tác thực hiện trong transaction.atomic(); mapping bị khóa bằng select_for_update().
- Target phải đã có CvatIdentity — không tạo EmployeeIdentity khi target chưa có mapping CVAT.
- Audit dùng append_audit_event() (T-013); nếu audit thất bại thì rollback cả mapping.
- reason KHÔNG được để trống.
- Không mở qua public API; chỉ dùng qua management command hoặc internal service.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework import status

from accounts.models import CvatIdentity, EmployeeIdentity, Role, RoleAssignment
from audit.models import AuditEvent
from audit.services import append_audit_event
from config.exceptions import ApiError


def can_manage_employee_identities(actor: Any) -> bool:
    """Kiểm tra quyền quản trị danh tính nhân sự.

    Chỉ cho phép SUPER_ADMIN hoặc QC_ADMIN (RoleAssignment).
    is_staff / is_superuser KHÔNG được dùng — không phải quyền nghiệp vụ.
    """
    if not actor or not getattr(actor, "is_authenticated", False):
        return False
    return RoleAssignment.objects.filter(
        user=actor, role__in=[Role.SUPER_ADMIN, Role.QC_ADMIN]
    ).exists()


def assign_employee_identity(
    *,
    actor: Any,
    user: User,
    employee_id: str,
    display_name: str = "",
    reason: str,
) -> tuple[EmployeeIdentity, AuditEvent]:
    """Cấp hoặc liên kết EmployeeIdentity với CvatIdentity của một user.

    Yêu cầu bảo mật:
    - actor phải có RoleAssignment SUPER_ADMIN hoặc QC_ADMIN.
    - Cấm tự gán/tự sửa: actor.pk != user.pk (chống tự phong quyền).
    - target (user) phải đã có CvatIdentity; nếu chưa, từ chối trước khi tạo EmployeeIdentity.
    - Chuẩn hóa: không phân biệt hoa thường (EMP-001 == emp-001).
    - Toàn bộ thao tác (mapping + audit) trong một transaction.atomic().
    - Mapping được khóa bằng select_for_update() tránh race condition.
    - append_audit_event() (T-013) ghi audit; thất bại → rollback cả mapping.
    - reason KHÔNG được để trống.
    - Không mở qua public API client.
    """
    if not can_manage_employee_identities(actor):
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "FORBIDDEN",
            (
                "Chỉ SUPER_ADMIN hoặc QC_ADMIN mới có quyền cấp hoặc sửa đổi"
                " EmployeeIdentity. is_staff/is_superuser không được dùng làm bypass."
            ),
        )

    # Cấm tự gán hoặc tự sửa EmployeeIdentity của chính mình
    if hasattr(actor, "pk") and hasattr(user, "pk") and actor.pk == user.pk:
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "SELF_MODIFICATION_FORBIDDEN",
            (
                "Không được phép tự gán hoặc tự thay đổi EmployeeIdentity của chính mình."
                " Thao tác phải được thực hiện bởi quản trị viên độc lập khác."
            ),
        )

    clean_emp_id = employee_id.strip()
    if not clean_emp_id:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_INPUT",
            "employee_id không được để trống.",
        )

    clean_reason = reason.strip() if reason else ""
    if not clean_reason:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_INPUT",
            "reason không được để trống — mô tả căn cứ cấp định danh nhân sự.",
        )

    with transaction.atomic():
        # Khóa CvatIdentity của target trước khi thao tác (select_for_update).
        cvat_identity: CvatIdentity | None = (
            CvatIdentity.objects.select_for_update().filter(user=user).first()
        )

        # Bắt buộc target đã có CvatIdentity — không tạo EmployeeIdentity khi chưa có CVAT mapping.
        if cvat_identity is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "IDENTITY_MAPPING_MISSING",
                (
                    f"Người dùng {user.get_username()!r} chưa có CvatIdentity."
                    " Phải gán CVAT identity trước khi cấp EmployeeIdentity."
                ),
            )

        # Ghi lại trạng thái trước.
        before_mapping: dict[str, Any] = {
            "user_id": user.pk,
            "username": user.get_username(),
            "employee_id": (cvat_identity.employee.employee_id if cvat_identity.employee else None),
        }

        # Tìm kiếm không phân biệt hoa thường để chuẩn hóa cùng một định danh
        emp: EmployeeIdentity | None = EmployeeIdentity.objects.filter(
            employee_id__iexact=clean_emp_id
        ).first()
        if emp is None:
            emp = EmployeeIdentity.objects.create(
                employee_id=clean_emp_id,
                display_name=display_name or clean_emp_id,
            )

        # Xác minh: actor là User và có quyền → đánh dấu verified.
        if not emp.is_verified and isinstance(actor, User):
            emp.verified_at = timezone.now()
            emp.verified_by = actor
            emp.save(update_fields=["verified_at", "verified_by", "updated_at"])

        # Gắn EmployeeIdentity vào CvatIdentity.
        cvat_identity.employee = emp
        cvat_identity.save(update_fields=["employee", "updated_at"])

        after_mapping: dict[str, Any] = {
            "user_id": user.pk,
            "username": user.get_username(),
            "employee_id": emp.employee_id,
            "is_verified": emp.is_verified,
            "cvat_user_id": cvat_identity.cvat_user_id,
        }

        # Ghi audit bên trong transaction — thất bại → rollback toàn bộ.
        audit_event = append_audit_event(
            actor=actor,
            action="accounts.employee_identity.assigned",
            object_type="employee_identity",
            object_id=emp.employee_id,
            before=before_mapping,
            after=after_mapping,
            revision="v1",
            reason=clean_reason,
        )

    return emp, audit_event
