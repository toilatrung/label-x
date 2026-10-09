"""Create/update the PostgreSQL role the application runs as (least privilege)."""

from __future__ import annotations

import os
from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import connection, transaction


class Command(BaseCommand):
    help = (
        "Tạo role runtime không phải superuser/owner: CRUD trên bảng ứng dụng, "
        "chỉ SELECT/INSERT trên audit log. Chạy bằng role migration sau mỗi lần migrate."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("role", help="Tên role runtime")
        parser.add_argument(
            "--password-env",
            default="",
            help="Tên biến môi trường chứa mật khẩu; bỏ trống thì tạo role NOLOGIN (dùng SET ROLE)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if connection.vendor != "postgresql":
            raise CommandError("Provisioning a runtime role requires PostgreSQL.")
        role = str(options["role"])
        password_env = str(options["password_env"])
        password = os.environ.get(password_env, "") if password_env else ""
        if password_env and not password:
            raise CommandError(f"Environment variable {password_env} is empty or not set.")

        quote = connection.ops.quote_name
        quoted = quote(role)
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
            exists = cursor.fetchone() is not None

        with transaction.atomic(), connection.cursor() as cursor:
            if not exists:
                cursor.execute(f"CREATE ROLE {quoted} NOSUPERUSER NOCREATEDB NOCREATEROLE NOLOGIN")
            if password:
                cursor.execute(f"ALTER ROLE {quoted} LOGIN PASSWORD %s", [password])
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {quoted}")
            cursor.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {quoted}"
            )
            cursor.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {quoted}")
            cursor.execute(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {quoted}"
            )
            cursor.execute(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                f"GRANT USAGE, SELECT ON SEQUENCES TO {quoted}"
            )
        # Audit is the one table the runtime role may only read and append to.
        call_command("configure_audit_db_role", role, stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS(f"Runtime role {role} is provisioned."))
