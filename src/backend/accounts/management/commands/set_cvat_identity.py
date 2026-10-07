"""Lưu identity mapping LabelX ↔ CVAT cho kiểm self-review (FR-SEC-02, T-011)."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import IntegrityError, transaction

from accounts.models import CvatIdentity


class Command(BaseCommand):
    help = "Gắn tài khoản LabelX với user CVAT: set_cvat_identity <username> <cvat_user_id>"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("username")
        parser.add_argument("cvat_user_id", type=int)
        parser.add_argument("--cvat-username", default="")

    def handle(self, *args: Any, **options: Any) -> None:
        user_model = get_user_model()
        try:
            user = user_model.objects.get(username=options["username"])
        except user_model.DoesNotExist as exc:
            raise CommandError(f"Không có người dùng {options['username']!r}.") from exc
        try:
            with transaction.atomic():
                CvatIdentity.objects.update_or_create(
                    user=user,
                    defaults={
                        "cvat_user_id": options["cvat_user_id"],
                        "cvat_username": options["cvat_username"],
                    },
                )
        except IntegrityError as exc:
            # cvat_user_id là unique: một user CVAT chỉ gắn với một tài khoản LabelX.
            raise CommandError(
                f"CVAT user #{options['cvat_user_id']} đã gắn với tài khoản LabelX khác."
            ) from exc
        self.stdout.write(f"Đã gắn {user.get_username()} ↔ CVAT #{options['cvat_user_id']}")
