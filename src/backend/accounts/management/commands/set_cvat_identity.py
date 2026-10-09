"""Lưu identity mapping LabelX ↔ CVAT cho kiểm self-review (FR-SEC-02, T-011, F-1).

Kiểm tra đầu vào TRƯỚC mọi mutation.
Bọc toàn bộ (cập nhật CVAT mapping, gán EmployeeIdentity và ghi audit) trong một
outer transaction.atomic(). Bất kỳ lỗi quyền, validation hoặc audit nào cũng rollback toàn bộ.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import IntegrityError, transaction

from accounts.models import CvatIdentity
from config.exceptions import ApiError


class Command(BaseCommand):
    help = "Gắn tài khoản LabelX với user CVAT: set_cvat_identity <username> <cvat_user_id>"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("username", help="Username của tài khoản LabelX cần gắn")
        parser.add_argument("cvat_user_id", type=int, help="CVAT user ID")
        parser.add_argument("--cvat-username", default="", help="CVAT username (tùy chọn)")
        parser.add_argument(
            "--employee-id",
            default="",
            help=(
                "Mã định danh nhân viên ổn định (EmployeeIdentity). "
                "Bắt buộc cung cấp --actor và --reason khi dùng tùy chọn này."
            ),
        )
        parser.add_argument(
            "--actor",
            default="",
            help=(
                "Username của người thực hiện (phải có SUPER_ADMIN hoặc QC_ADMIN role). "
                "Bắt buộc khi dùng --employee-id."
            ),
        )
        parser.add_argument(
            "--reason",
            default="",
            help="Lý do cấp/thay đổi EmployeeIdentity mapping (bắt buộc khi dùng --employee-id).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        user_model = get_user_model()
        username = options["username"]
        try:
            user = user_model.objects.get(username=username)
        except user_model.DoesNotExist as exc:
            raise CommandError(f"Không có người dùng {username!r}.") from exc

        employee_id_arg = options.get("employee_id", "").strip()
        actor_username = options.get("actor", "").strip()
        reason_arg = options.get("reason", "").strip()

        # 1. KIỂM TRA ĐẦU VÀO TRƯỚC MỌI MUTATION
        actor: Any = None
        if employee_id_arg:
            if not actor_username:
                raise CommandError(
                    "--actor là bắt buộc khi sử dụng --employee-id. "
                    "Actor phải có SUPER_ADMIN hoặc QC_ADMIN role."
                )
            if not reason_arg:
                raise CommandError(
                    "--reason là bắt buộc khi sử dụng --employee-id. "
                    "Mô tả căn cứ cấp định danh nhân sự."
                )

            try:
                actor = user_model.objects.get(username=actor_username)
            except user_model.DoesNotExist as exc:
                raise CommandError(f"Không tìm thấy actor {actor_username!r}.") from exc

            from accounts.services import can_manage_employee_identities

            if not can_manage_employee_identities(actor):
                raise CommandError(
                    f"Actor {actor_username!r} không có quyền SUPER_ADMIN hoặc QC_ADMIN"
                    " qua RoleAssignment."
                )

            if actor.pk == user.pk:
                raise CommandError(
                    "Actor không được phép tự gán hoặc tự thay đổi EmployeeIdentity của chính mình."
                )

        # 2. BỌC TOÀN BỘ CẬP NHẬT TRONG MỘT OUTER TRANSACTION.ATOMIC()
        from accounts.services import assign_employee_identity

        cvat_user_id = options["cvat_user_id"]
        cvat_username = options.get("cvat_username", "")
        emp = None

        try:
            with transaction.atomic():
                # Cập nhật hoặc tạo CvatIdentity
                CvatIdentity.objects.update_or_create(
                    user=user,
                    defaults={
                        "cvat_user_id": cvat_user_id,
                        "cvat_username": cvat_username,
                    },
                )

                # Nếu có employee_id, gọi service (gán EmployeeIdentity + ghi audit)
                if employee_id_arg and actor is not None:
                    emp, _ = assign_employee_identity(
                        actor=actor,
                        user=user,
                        employee_id=employee_id_arg,
                        reason=reason_arg,
                    )
        except IntegrityError as exc:
            raise CommandError(
                f"CVAT user #{cvat_user_id} đã gắn với tài khoản LabelX khác."
            ) from exc
        except ApiError as exc:
            raise CommandError(
                f"Không thể gán EmployeeIdentity: [{exc.error_code}] {exc.detail}"
            ) from exc
        except Exception as exc:
            raise CommandError(f"Lỗi khi thực thi gán identity: {exc}") from exc

        self.stdout.write(f"Đã gắn {user.get_username()} ↔ CVAT #{cvat_user_id}")
        if employee_id_arg and emp is not None:
            self.stdout.write(
                f"Đã gán EmployeeIdentity {emp.employee_id!r} cho {user.get_username()}"
                f" (verified={emp.is_verified})"
            )
