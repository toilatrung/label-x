# Generated for LabelX T-013: append-only audit trail.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

APPEND_ONLY_SQL = """
CREATE OR REPLACE FUNCTION audit_reject_auditevent_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit_auditevent is append-only; % is forbidden', TG_OP
        USING ERRCODE = '42501';
END;
$$;

CREATE TRIGGER audit_auditevent_no_update_delete
BEFORE UPDATE OR DELETE ON audit_auditevent
FOR EACH ROW EXECUTE FUNCTION audit_reject_auditevent_mutation();

REVOKE UPDATE, DELETE, TRUNCATE ON TABLE audit_auditevent FROM PUBLIC;
"""

REVERSE_APPEND_ONLY_SQL = """
DROP TRIGGER IF EXISTS audit_auditevent_no_update_delete ON audit_auditevent;
DROP FUNCTION IF EXISTS audit_reject_auditevent_mutation();
"""


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("action", models.CharField(max_length=100)),
                ("object_type", models.CharField(max_length=100)),
                ("object_id", models.CharField(max_length=255)),
                ("before", models.JSONField(blank=True, null=True)),
                ("after", models.JSONField(blank=True, null=True)),
                ("revision", models.CharField(max_length=255)),
                ("reason", models.TextField(blank=True)),
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="audit_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
                "indexes": [
                    models.Index(fields=["object_type", "object_id"], name="audit_object_idx"),
                    models.Index(fields=["occurred_at"], name="audit_occurred_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=~models.Q(action=""), name="audit_action_not_empty"
                    ),
                    models.CheckConstraint(
                        condition=~models.Q(object_type=""), name="audit_object_type_not_empty"
                    ),
                    models.CheckConstraint(
                        condition=~models.Q(object_id=""), name="audit_object_id_not_empty"
                    ),
                    models.CheckConstraint(
                        condition=~models.Q(revision=""), name="audit_revision_not_empty"
                    ),
                ],
            },
        ),
        migrations.RunSQL(APPEND_ONLY_SQL, REVERSE_APPEND_ONLY_SQL),
    ]
