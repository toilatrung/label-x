"""Gán vai trò theo scope dataset cho người dùng (T-011; màn quản trị user nằm ngoài phạm vi)."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import IntegrityError, transaction

from accounts.models import SYSTEM_WIDE_ROLES, Role, RoleAssignment


class Command(BaseCommand):
    help = "Gán vai trò cho người dùng: assign_role <username> <role> [--dataset-id N]"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("username")
        parser.add_argument("role", choices=Role.values)
        parser.add_argument(
            "--dataset-id",
            type=int,
            default=None,
            help="Dataset được gán; bỏ trống = toàn hệ thống (chỉ super_admin, qc_admin)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        user_model = get_user_model()
        try:
            user = user_model.objects.get(username=options["username"])
        except user_model.DoesNotExist as exc:
            raise CommandError(f"Không có người dùng {options['username']!r}.") from exc
        role, dataset_id = options["role"], options["dataset_id"]
        if dataset_id is None and role not in SYSTEM_WIDE_ROLES:
            raise CommandError(f"Vai trò {role} phải gắn với --dataset-id.")
        try:
            with transaction.atomic():
                _, created = RoleAssignment.objects.get_or_create(
                    user=user, role=role, dataset_id=dataset_id
                )
        except IntegrityError as exc:
            raise CommandError(f"Không gán được vai trò: {exc}") from exc
        state = "Đã gán" if created else "Đã có sẵn"
        self.stdout.write(f"{state}: {user.get_username()} — {role} (dataset {dataset_id})")
