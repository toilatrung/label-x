"""Deployment check: the runtime database role must not rewrite audit (FR-SEC-05, NFR-08).

The append-only trigger stops UPDATE/DELETE, but a superuser or table owner can still TRUNCATE the
table or disable the trigger. `manage.py check --deploy` therefore verifies the privileges of the
role the application is connected as. Provision such a role with
`manage.py provision_runtime_db_role` (see docs/07-development/workflow.html).
"""

from __future__ import annotations

from typing import Any

from django.core.checks import CheckMessage, Error, Tags, register
from django.db import connection

FORBIDDEN_PRIVILEGES = ("UPDATE", "DELETE", "TRUNCATE")


def forbidden_audit_privileges() -> list[str]:
    """Privileges on audit_auditevent that the current database role holds but must not."""
    held: list[str] = []
    with connection.cursor() as cursor:
        for privilege in FORBIDDEN_PRIVILEGES:
            cursor.execute(
                "SELECT has_table_privilege(current_user, 'audit_auditevent', %s)", [privilege]
            )
            row = cursor.fetchone()
            if row and row[0]:
                held.append(privilege)
    return held


@register(Tags.database, deploy=True)
def audit_runtime_role_is_restricted(
    app_configs: Any = None, databases: Any = None, **kwargs: Any
) -> list[CheckMessage]:
    if connection.vendor != "postgresql":
        return []
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('audit_auditevent') IS NOT NULL")
        row = cursor.fetchone()
        if not (row and row[0]):
            return []  # migrations not applied yet; nothing to protect
        cursor.execute("SELECT current_user")
        role_row = cursor.fetchone()
    role = role_row[0] if role_row else "unknown"
    held = forbidden_audit_privileges()
    if not held:
        return []
    return [
        Error(
            f"Database role {role!r} holds {', '.join(held)} on audit_auditevent.",
            hint=(
                "Run the application as a non-owner, non-superuser role: "
                "manage.py provision_runtime_db_role <role> (migrations keep using the owner role)."
            ),
            id="audit.E001",
        )
    ]
