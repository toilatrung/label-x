from __future__ import annotations

import uuid

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from django.urls import get_resolver

from accounts.models import RoleAssignment
from audit.models import AuditEvent, AuditImmutableError
from audit.services import AuditTransactionRequired, append_audit_event

pytestmark = pytest.mark.django_db(transaction=True)


def _actor(username: str = "audit-actor"):
    return get_user_model().objects.create_user(username=username, password="safe-test-password")


def _append(actor, **overrides):
    values = {
        "actor": actor,
        "action": "role.assigned",
        "object_type": "role_assignment",
        "object_id": "7",
        "before": None,
        "after": {"role": "reviewer", "dataset_id": 12},
        "revision": "rev-1",
        "reason": "Approved by the data owner",
    }
    values.update(overrides)
    return append_audit_event(**values)


def test_service_requires_the_callers_atomic_transaction():
    actor = _actor()

    with pytest.raises(AuditTransactionRequired, match="transaction.atomic"):
        _append(actor)

    assert not AuditEvent.objects.exists()


def test_operation_and_audit_commit_together():
    actor = _actor()

    with transaction.atomic():
        assignment = RoleAssignment.objects.create(
            user=actor,
            role="reviewer",
            dataset_id=12,
        )
        event = _append(actor, object_id=assignment.pk)

    event.refresh_from_db()
    assert event.actor == actor
    assert event.object_id == str(assignment.pk)
    assert event.before is None
    assert event.after == {"role": "reviewer", "dataset_id": 12}


def test_operation_rollback_removes_the_audit_event():
    actor = _actor()

    with pytest.raises(RuntimeError, match="force rollback"):
        with transaction.atomic():
            assignment = RoleAssignment.objects.create(
                user=actor,
                role="reviewer",
                dataset_id=12,
            )
            _append(actor, object_id=assignment.pk)
            raise RuntimeError("force rollback")

    assert not RoleAssignment.objects.exists()
    assert not AuditEvent.objects.exists()


def test_snapshots_and_reason_are_redacted_before_storage():
    actor = _actor()
    fake_password = "fake-password-t013"
    fake_token = "fake-token-t013"

    with transaction.atomic():
        event = _append(
            actor,
            before={"username": "an", "password": fake_password},
            after={
                "safe": "kept",
                "nested": {"api_key": fake_token},
                "header": f"Authorization: Bearer {fake_token}",
            },
            reason=f"token={fake_token}",
        )

    event.refresh_from_db()
    stored = f"{event.before!r} {event.after!r} {event.reason}"
    assert fake_password not in stored
    assert fake_token not in stored
    assert event.before == {"username": "an", "password": "[REDACTED]"}
    assert event.after == {
        "safe": "kept",
        "nested": {"api_key": "[REDACTED]"},
        "header": "Authorization: [REDACTED]",
    }
    assert event.reason == "token=[REDACTED]"


def test_key_material_and_connection_url_password_are_redacted_before_storage():
    actor = _actor()
    fake_private_key = "fake-private-key-t013"
    fake_session_key = "fake-session-key-t013"
    fake_database_password = "fake-database-password-t013"

    with transaction.atomic():
        event = _append(
            actor,
            after={
                "private_key": fake_private_key,
                "session-key": fake_session_key,
                "connection": (
                    f"postgres://labelx:{fake_database_password}@postgres.internal:5432/labelx"
                ),
            },
        )

    event.refresh_from_db()
    stored = repr(event.after)
    assert fake_private_key not in stored
    assert fake_session_key not in stored
    assert fake_database_password not in stored
    assert event.after == {
        "private_key": "[REDACTED]",
        "session-key": "[REDACTED]",
        "connection": "postgres://labelx:[REDACTED]@postgres.internal:5432/labelx",
    }


def test_model_and_database_reject_update_and_delete():
    actor = _actor()
    with transaction.atomic():
        event = _append(actor)

    event.action = "tampered"
    with pytest.raises(AuditImmutableError, match="cannot be updated"):
        event.save()
    with pytest.raises(AuditImmutableError, match="cannot be deleted"):
        event.delete()

    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        AuditEvent.objects.filter(pk=event.pk).update(action="tampered")
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        AuditEvent.objects.filter(pk=event.pk).delete()

    event.refresh_from_db()
    assert event.action == "role.assigned"


def test_runtime_database_role_has_only_insert_and_select(capsys):
    actor = _actor()
    role = f"labelx_audit_test_{uuid.uuid4().hex[:12]}"
    quoted_role = connection.ops.quote_name(role)

    with connection.cursor() as cursor:
        cursor.execute(f"CREATE ROLE {quoted_role} NOLOGIN")

    try:
        call_command("configure_audit_db_role", role)
        assert "SELECT/INSERT only" in capsys.readouterr().out

        with connection.cursor() as cursor:
            cursor.execute(f"SET ROLE {quoted_role}")
            try:
                cursor.execute(
                    """
                    SELECT
                        has_table_privilege(current_user, 'audit_auditevent', 'SELECT'),
                        has_table_privilege(current_user, 'audit_auditevent', 'INSERT'),
                        has_table_privilege(current_user, 'audit_auditevent', 'UPDATE'),
                        has_table_privilege(current_user, 'audit_auditevent', 'DELETE'),
                        has_table_privilege(current_user, 'audit_auditevent', 'TRUNCATE')
                    """
                )
                assert cursor.fetchone() == (True, True, False, False, False)

                cursor.execute(
                    """
                    INSERT INTO audit_auditevent
                        (actor_id, action, object_type, object_id, before, after,
                         revision, reason, occurred_at)
                    VALUES (%s, 'test.insert', 'test_object', '1', NULL, '{}'::jsonb,
                            'rev-db-role', '', NOW())
                    RETURNING id
                    """,
                    [actor.pk],
                )
                event_id = cursor.fetchone()[0]

                with pytest.raises(DatabaseError, match="permission denied"):
                    cursor.execute(
                        "UPDATE audit_auditevent SET action = 'tampered' WHERE id = %s",
                        [event_id],
                    )
                with pytest.raises(DatabaseError, match="permission denied"):
                    cursor.execute("DELETE FROM audit_auditevent WHERE id = %s", [event_id])
            finally:
                cursor.execute("RESET ROLE")
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP OWNED BY {quoted_role}")
            cursor.execute(f"DROP ROLE IF EXISTS {quoted_role}")


def test_audit_has_no_admin_or_api_mutation_surface():
    assert not admin.site.is_registered(AuditEvent)

    top_level_routes = {str(pattern.pattern) for pattern in get_resolver().url_patterns}
    assert not any("audit" in route for route in top_level_routes)


def test_deploy_check_reports_owner_role_and_accepts_the_runtime_role(capsys):
    from audit.checks import audit_runtime_role_is_restricted

    role = f"labelx_runtime_test_{uuid.uuid4().hex[:12]}"
    quoted_role = connection.ops.quote_name(role)

    # The test connection is the table owner/superuser: the check must reject it.
    errors = audit_runtime_role_is_restricted()
    assert [error.id for error in errors] == ["audit.E001"]
    assert "TRUNCATE" in errors[0].msg

    try:
        call_command("provision_runtime_db_role", role)
        assert "provisioned" in capsys.readouterr().out
        with connection.cursor() as cursor:
            cursor.execute(f"SET ROLE {quoted_role}")
            try:
                assert audit_runtime_role_is_restricted() == []
                cursor.execute("SELECT has_table_privilege(current_user, 'auth_user', 'UPDATE')")
                assert cursor.fetchone() == (True,)  # still able to run the application
            finally:
                cursor.execute("RESET ROLE")
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP OWNED BY {quoted_role}")
            cursor.execute(f"DROP ROLE IF EXISTS {quoted_role}")
