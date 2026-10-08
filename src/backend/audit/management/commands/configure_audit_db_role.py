"""Restrict a PostgreSQL runtime role to append/read access on the audit table."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import connection, transaction


class Command(BaseCommand):
    help = "Cấp duy nhất SELECT/INSERT trên audit log cho PostgreSQL runtime role"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("role", help="PostgreSQL role dùng bởi ứng dụng lúc runtime")

    def handle(self, *args: Any, **options: Any) -> None:
        if connection.vendor != "postgresql":
            raise CommandError("Audit database grants require PostgreSQL.")

        role = str(options["role"])
        quoted_role = connection.ops.quote_name(role)
        quoted_table = connection.ops.quote_name("audit_auditevent")
        quoted_sequence = connection.ops.quote_name("audit_auditevent_id_seq")

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT current_user, tableowner
                FROM pg_tables
                WHERE schemaname = current_schema() AND tablename = 'audit_auditevent'
                """
            )
            ownership = cursor.fetchone()
            if ownership is None:
                raise CommandError("Table audit_auditevent does not exist; run migrations first.")
            migration_role, table_owner = ownership

            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
            if cursor.fetchone() is None:
                raise CommandError(f"PostgreSQL role {role!r} does not exist.")
            if role in {migration_role, table_owner}:
                raise CommandError(
                    "Runtime role must differ from the migration/table-owner role; "
                    "PostgreSQL owners have implicit mutation privileges."
                )

        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {quoted_role}")
            cursor.execute(f"REVOKE ALL PRIVILEGES ON TABLE {quoted_table} FROM {quoted_role}")
            cursor.execute(f"GRANT SELECT, INSERT ON TABLE {quoted_table} TO {quoted_role}")
            cursor.execute(
                f"REVOKE ALL PRIVILEGES ON SEQUENCE {quoted_sequence} FROM {quoted_role}"
            )
            cursor.execute(f"GRANT USAGE, SELECT ON SEQUENCE {quoted_sequence} TO {quoted_role}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Configured {role}: SELECT/INSERT only on audit_auditevent; "
                "UPDATE/DELETE/TRUNCATE revoked."
            )
        )
