"""Permissions cho module GDL (tra cứu guideline)."""

from __future__ import annotations

from accounts.models import Role
from accounts.permissions import HasRoleAndDatasetScope


class HasGuidelineRole(HasRoleAndDatasetScope):
    """Quyền truy cập guideline (openapi.yaml x-labelx-roles, rbac-matrix.html).

    Vai trò cho phép: reviewer, qa_lead, qc_admin, super_admin.
    Annotator và các vai trò khác không có quyền (403 FORBIDDEN kèm bản ghi audit log).
    Chưa đăng nhập trả về 403 NOT_AUTHENTICATED (xử lý qua exception handler).
    Guideline là tài nguyên toàn hệ thống, không yêu cầu scope dataset.
    """

    allowed_roles = (Role.REVIEWER, Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN)
    action_name = "guidelines.rules"
    object_type = "guideline"
    requires_dataset = False
