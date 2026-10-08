"""RBAC and dataset scope permissions for LabelX API (T-012, Epic E-02, Issue #41).

Enforces:
- RBAC by role and dataset scope (AC 1).
- Separation of duties (requester != approver) and anti-self-review (AC 2).
- Fail-closed identity checks and non-overridable self-review invariant (DEC-011).
- Super Admin override with mandatory reason and audit labeling (AC 3).
- Strict RoleAssignment lookup without undocumented is_superuser bypass.
- Fail-closed dataset scope: missing, invalid type, or conflicting dataset_id is rejected.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, transaction
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from accounts.models import SYSTEM_WIDE_ROLES, CvatIdentity, Role, RoleAssignment
from audit.models import AuditEvent
from audit.services import append_audit_event
from config.exceptions import ApiError


def record_rejection_audit(
    *,
    request: Request,
    code: str,
    object_type: str,
    object_id: object,
    action: str,
    message: str = "",
) -> None:
    """Store pending rejection audit for AuditRejectionMiddleware outside atomic view."""
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return

    request_id = (
        getattr(request, "request_id", None)
        or getattr(getattr(request, "_request", None), "request_id", None)
        or str(uuid.uuid4())
    )
    normalized_action = f"{action}.rejected"
    reason_text = f"Rejected: {code} - {message}" if message else f"Rejected: {code}"
    details = {
        "code": code,
        "path": getattr(request, "path", ""),
        "method": getattr(request, "method", ""),
    }

    pending_event = {
        "actor": user,
        "action": normalized_action,
        "object_type": object_type,
        "object_id": str(object_id) or "global",
        "before": None,
        "after": details,
        "revision": request_id,
        "reason": reason_text,
    }

    has_middleware = getattr(request, "_has_audit_middleware", False) or getattr(
        getattr(request, "_request", None), "_has_audit_middleware", False
    )

    if has_middleware:
        # Buffer for AuditRejectionMiddleware outside view atomic transaction
        setattr(request, "_pending_rejection_audit", pending_event)  # noqa: B010
        underlying = getattr(request, "_request", None)
        if underlying is not None:
            underlying._pending_rejection_audit = pending_event
    else:
        # Standalone direct view call in unit tests: persist immediately
        setattr(request, "_pending_rejection_audit", pending_event)  # noqa: B010
        if connection.in_atomic_block:
            append_audit_event(
                actor=user,
                action=normalized_action,
                object_type=object_type,
                object_id=str(object_id) or "global",
                before=None,
                after=details,
                revision=request_id,
                reason=reason_text,
            )
        else:
            with transaction.atomic():
                append_audit_event(
                    actor=user,
                    action=normalized_action,
                    object_type=object_type,
                    object_id=str(object_id) or "global",
                    before=None,
                    after=details,
                    revision=request_id,
                    reason=reason_text,
                )


def flush_pending_rejection_audit(request: Any) -> AuditEvent | None:
    """Flush pending rejection audit when running direct view calls in tests."""
    pending = getattr(request, "_pending_rejection_audit", None)
    if not pending and hasattr(request, "_request"):
        pending = getattr(request._request, "_pending_rejection_audit", None)
    if pending:
        actor = pending.get("actor")
        if actor and isinstance(actor, User) and actor.is_authenticated:
            with transaction.atomic():
                event = append_audit_event(
                    actor=actor,
                    action=str(pending["action"]),
                    object_type=str(pending["object_type"]),
                    object_id=str(pending["object_id"]),
                    before=pending.get("before"),
                    after=pending.get("after"),
                    revision=str(pending.get("revision") or getattr(request, "request_id", "")),
                    reason=str(pending.get("reason", "")),
                )
            request._pending_rejection_audit = None
            if hasattr(request, "_request"):
                request._request._pending_rejection_audit = None
            return event
    return None


def append_action_audit(
    *,
    request: Request,
    action: str,
    object_type: str,
    object_id: object,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
    revision: str | None = None,
) -> AuditEvent:
    """Audit helper ensuring override audit event is labeled with is_override=True."""
    is_override = getattr(request, "is_override", False)
    override_reason = getattr(request, "override_reason", None) or reason
    payload_after = dict(after or {})
    if is_override:
        payload_after["is_override"] = True

    req_id = (
        getattr(request, "request_id", None)
        or getattr(getattr(request, "_request", None), "request_id", None)
        or revision
        or str(uuid.uuid4())
    )

    actor = getattr(request, "user", None)
    if not isinstance(actor, User):
        raise ApiError(status.HTTP_403_FORBIDDEN, "NOT_AUTHENTICATED", "Chưa đăng nhập.")

    override_reason_str = str(override_reason or "")
    return append_audit_event(
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=str(object_id),
        before=before,
        after=payload_after,
        revision=req_id,
        reason=override_reason_str,
    )


class HasRoleAndDatasetScope(BasePermission):
    """RBAC by role and dataset scope at API (Issue #41, AC 1)."""

    allowed_roles: tuple[Role, ...] | None = None
    action_name: str = "api.access"
    object_type: str = "dataset"

    def get_required_roles(self, request: Request, view: Any) -> tuple[Role, ...]:
        roles = getattr(view, "allowed_roles", None) or getattr(view, "required_roles", None)
        if roles is not None:
            return tuple(roles)
        if self.allowed_roles is not None:
            return self.allowed_roles
        return ()

    def get_target_dataset_id(self, request: Request, view: Any) -> int | None:
        return self._extract_dataset_id(request, view)

    def _extract_dataset_id(self, request: Request, view: Any) -> int | None:
        """Extract and validate dataset_id fail-closed across kwargs, query params, and body."""
        requires_dataset = getattr(view, "requires_dataset", None)
        if requires_dataset is None:
            requires_dataset = getattr(self, "requires_dataset", True)

        scope_type = getattr(view, "scope_type", None)
        if scope_type is None:
            scope_type = getattr(self, "scope_type", "dataset")

        if not requires_dataset or scope_type == "system":
            return None

        candidates: list[tuple[str, Any]] = []

        # 1. Server-side authoritative hook on view (get_dataset_id(request))
        hook = getattr(view, "get_dataset_id", None)
        if callable(hook):
            hook_val = hook(request)
            if hook_val is not None:
                candidates.append(("server_hook", hook_val))

        # 2. URL kwargs (only explicit dataset_id, NEVER generic pk!)
        kwargs = getattr(view, "kwargs", {}) or {}
        if "dataset_id" in kwargs and kwargs["dataset_id"] is not None:
            candidates.append(("kwargs.dataset_id", kwargs["dataset_id"]))

        # 3. Query params
        query_params = getattr(request, "query_params", getattr(request, "GET", {}))
        if hasattr(query_params, "get") and query_params.get("dataset_id") is not None:
            candidates.append(("query_params.dataset_id", query_params.get("dataset_id")))

        # 3. Body data
        data = getattr(request, "data", getattr(request, "POST", {}))
        if isinstance(data, dict) and data.get("dataset_id") is not None:
            candidates.append(("data.dataset_id", data.get("dataset_id")))

        action = getattr(view, "action_name", getattr(view, "operation_id", self.action_name))
        obj_type = getattr(view, "object_type", self.object_type)

        if not candidates:
            # Missing dataset_id on a dataset-scoped view -> fail-closed
            record_rejection_audit(
                request=request,
                code="OUT_OF_SCOPE",
                object_type=obj_type,
                object_id="missing",
                action=action,
                message="Thao tác yêu cầu phạm vi dataset nhưng không tìm thấy dataset_id.",
            )
            raise ApiError(
                status.HTTP_403_FORBIDDEN,
                "OUT_OF_SCOPE",
                "Thao tác yêu cầu phạm vi dataset nhưng không tìm thấy dataset_id.",
            )

        # Validate types and check for conflicts
        parsed_values: list[tuple[str, int]] = []
        for source_name, raw_val in candidates:
            if isinstance(raw_val, bool):
                record_rejection_audit(
                    request=request,
                    code="VALIDATION_ERROR",
                    object_type=obj_type,
                    object_id=str(raw_val),
                    action=action,
                    message=f"dataset_id từ {source_name} sai kiểu (phải là số nguyên dương).",
                )
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST,
                    "VALIDATION_ERROR",
                    f"dataset_id từ {source_name} sai kiểu (phải là số nguyên dương).",
                )

            val_str = str(raw_val).strip()
            if not val_str or not val_str.isdigit() or int(val_str) <= 0:
                record_rejection_audit(
                    request=request,
                    code="VALIDATION_ERROR",
                    object_type=obj_type,
                    object_id=val_str or "invalid",
                    action=action,
                    message=f"dataset_id từ {source_name} sai kiểu (phải là số nguyên dương).",
                )
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST,
                    "VALIDATION_ERROR",
                    f"dataset_id từ {source_name} sai kiểu (phải là số nguyên dương).",
                )

            parsed_values.append((source_name, int(val_str)))

        # Check for conflicts across sources
        first_source, first_val = parsed_values[0]
        for src, val in parsed_values[1:]:
            if val != first_val:
                record_rejection_audit(
                    request=request,
                    code="VALIDATION_ERROR",
                    object_type=obj_type,
                    object_id=f"{first_val}!={val}",
                    action=action,
                    message=(
                        f"Mâu thuẫn dataset_id giữa {first_source} ({first_val}) và {src} ({val})."
                    ),
                )
                raise ApiError(
                    status.HTTP_400_BAD_REQUEST,
                    "VALIDATION_ERROR",
                    f"Mâu thuẫn dataset_id giữa {first_source} ({first_val}) và {src} ({val}).",
                )

        return first_val

    def has_permission(self, request: Request, view: Any) -> bool:
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False

        # Strict: NO is_superuser bypass. Permissions derive solely from RoleAssignment.
        required_roles = self.get_required_roles(request, view)
        if not required_roles:
            raise ImproperlyConfigured(
                f"View '{view.__class__.__name__}' chưa cấu hình allowed_roles."
            )

        assignments = list(RoleAssignment.objects.filter(user_id=user.pk))
        matching_assignments = [a for a in assignments if a.role in required_roles]

        action = getattr(view, "action_name", getattr(view, "operation_id", self.action_name))
        obj_type = getattr(view, "object_type", self.object_type)

        if not matching_assignments:
            record_rejection_audit(
                request=request,
                code="FORBIDDEN",
                object_type=obj_type,
                object_id="global",
                action=action,
                message="Người dùng không có vai trò được phép thực hiện thao tác này.",
            )
            raise ApiError(
                status.HTTP_403_FORBIDDEN,
                "FORBIDDEN",
                "Người dùng không có vai trò được phép thực hiện thao tác này.",
            )

        target_dataset_id = self.get_target_dataset_id(request, view)
        object_id_str = str(target_dataset_id) if target_dataset_id is not None else "global"

        if target_dataset_id is not None:
            has_scope = any(
                a.dataset_id == target_dataset_id
                or (a.role in SYSTEM_WIDE_ROLES and a.dataset_id is None)
                for a in matching_assignments
            )
            if not has_scope:
                record_rejection_audit(
                    request=request,
                    code="OUT_OF_SCOPE",
                    object_type=obj_type,
                    object_id=object_id_str,
                    action=action,
                    message=(
                        f"Tài nguyên dataset {target_dataset_id} nằm ngoài phạm vi được phân công."
                    ),
                )
                raise ApiError(
                    status.HTTP_403_FORBIDDEN,
                    "OUT_OF_SCOPE",
                    f"Tài nguyên dataset {target_dataset_id} nằm ngoài phạm vi được phân công.",
                )

        return True


def check_anti_self_review(
    *,
    request: Request,
    author_cvat_user_id: int | None,
    action: str = "review.frame",
    object_type: str = "frame",
    object_id: object = "",
) -> None:
    """FR-SEC-02, FR-SEC-03, FR-SEC-06: Fail-closed identity check and anti-self-review invariant.

    Super Admin CANNOT override this check under any circumstances.
    """
    user = getattr(request, "user", None)
    user_id = int(user.pk) if user and user.pk is not None else 0
    identity = CvatIdentity.objects.filter(user_id=user_id).first()
    if identity is None:
        record_rejection_audit(
            request=request,
            code="IDENTITY_MAPPING_MISSING",
            object_type=object_type,
            object_id=str(object_id),
            action=action,
            message="Chưa liên kết danh tính CVAT. Mọi thao tác kiểm thử/review bị từ chối.",
        )
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "IDENTITY_MAPPING_MISSING",
            "Chưa liên kết danh tính CVAT. Mọi thao tác kiểm thử/review bị từ chối.",
        )

    if author_cvat_user_id is not None and identity.cvat_user_id == author_cvat_user_id:
        record_rejection_audit(
            request=request,
            code="SELF_REVIEW_FORBIDDEN",
            object_type=object_type,
            object_id=str(object_id),
            action=action,
            message="Người thẩm định không được phép tự review annotation do chính mình thực hiện.",
        )
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "SELF_REVIEW_FORBIDDEN",
            "Người thẩm định không được phép tự review annotation do chính mình thực hiện.",
        )


def check_separation_of_duties(
    *,
    request: Request,
    requester_user_id: int | None = None,
    requester_cvat_user_id: int | None = None,
    action: str = "approval.adjudicate",
    object_type: str = "request",
    object_id: object = "",
) -> None:
    """FR-SEC-04, AC 2: Separation of duties (approver != requester, cross-account check)."""
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "NOT_AUTHENTICATED",
            "Chưa đăng nhập hoặc phiên hết hạn.",
        )

    # Approver matching requester by LabelX user ID
    if requester_user_id is not None and user.pk == requester_user_id:
        record_rejection_audit(
            request=request,
            code="SAME_REQUESTER_APPROVER",
            object_type=object_type,
            object_id=str(object_id),
            action=action,
            message=(
                "Người phê duyệt không được trùng với người yêu cầu (vi phạm nguyên tắc bốn mắt)."
            ),
        )
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "SAME_REQUESTER_APPROVER",
            "Người phê duyệt không được trùng với người yêu cầu (vi phạm nguyên tắc bốn mắt).",
        )

    # When cross-account check is required or requester has CVAT identity
    if requester_cvat_user_id is not None:
        user_id = int(user.pk) if user.pk is not None else 0
        identity = CvatIdentity.objects.filter(user_id=user_id).first()
        if identity is None:
            # Fail-closed when identity is missing on approver
            record_rejection_audit(
                request=request,
                code="IDENTITY_MAPPING_MISSING",
                object_type=object_type,
                object_id=str(object_id),
                action=action,
                message="Người phê duyệt chưa liên kết danh tính CVAT (fail-closed).",
            )
            raise ApiError(
                status.HTTP_403_FORBIDDEN,
                "IDENTITY_MAPPING_MISSING",
                "Người phê duyệt chưa liên kết danh tính CVAT (fail-closed).",
            )

        if identity.cvat_user_id == requester_cvat_user_id:
            record_rejection_audit(
                request=request,
                code="SAME_REQUESTER_APPROVER",
                object_type=object_type,
                object_id=str(object_id),
                action=action,
                message=(
                    "Người phê duyệt trùng danh tính thực tế với người yêu cầu qua tài khoản khác."
                ),
            )
            raise ApiError(
                status.HTTP_403_FORBIDDEN,
                "SAME_REQUESTER_APPROVER",
                "Người phê duyệt trùng danh tính thực tế với người yêu cầu qua tài khoản khác.",
            )


def check_super_admin_override(
    *,
    request: Request,
    override_flag: bool | None = None,
    reason_field: str = "override_reason",
    action: str = "override.action",
    object_type: str = "operation",
    object_id: object = "global",
) -> str | None:
    """FR-SEC-06, AC 3: Super Admin override validation with audit labeling."""
    query_params = getattr(request, "query_params", getattr(request, "GET", {}))
    data = getattr(request, "data", getattr(request, "POST", {}))

    if override_flag is None:
        val = query_params.get("override")
        if val is None and isinstance(data, dict):
            val = data.get("override")
        if val is not None:
            override_flag = str(val).strip().lower() in ("true", "1", "yes")
        else:
            override_flag = False

    if not override_flag:
        return None

    user = getattr(request, "user", None)
    caller_id = int(user.pk) if user and user.pk is not None else 0
    # Strict: only RoleAssignment(role=SUPER_ADMIN), NO is_superuser shortcut!
    is_super_admin = RoleAssignment.objects.filter(
        user_id=caller_id, role=Role.SUPER_ADMIN
    ).exists()
    if not is_super_admin:
        record_rejection_audit(
            request=request,
            code="FORBIDDEN",
            object_type=object_type,
            object_id=str(object_id),
            action=action,
            message="Chỉ Super Admin mới có quyền thực hiện thao tác ghi đè.",
        )
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "FORBIDDEN",
            "Chỉ Super Admin mới có quyền thực hiện thao tác ghi đè.",
        )

    reason = query_params.get(reason_field)
    if (reason is None or not str(reason).strip()) and isinstance(data, dict):
        reason = data.get(reason_field) or data.get("reason")

    if reason is None or not str(reason).strip():
        record_rejection_audit(
            request=request,
            code="BUSINESS_RULE_UNMET",
            object_type=object_type,
            object_id=str(object_id),
            action=action,
            message="Ghi đè của Super Admin bắt buộc phải có lý do (override_reason).",
        )
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "BUSINESS_RULE_UNMET",
            "Ghi đè của Super Admin bắt buộc phải có lý do (override_reason).",
        )

    reason_str = str(reason).strip()
    # Mark override on request for downstream audit logging
    setattr(request, "is_override", True)  # noqa: B010
    setattr(request, "override_reason", reason_str)  # noqa: B010
    return reason_str
