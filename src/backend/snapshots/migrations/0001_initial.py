# Generated for LabelX T-020: immutable normalized snapshots.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

IMMUTABILITY_SQL = """
CREATE OR REPLACE FUNCTION snapshots_reject_locked_snapshot_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status = 'locked' THEN
        RAISE EXCEPTION 'locked snapshot is immutable'
            USING ERRCODE = '55000';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE OR REPLACE FUNCTION snapshots_reject_locked_job_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF (TG_OP <> 'INSERT' AND EXISTS (
        SELECT 1 FROM snapshots_snapshot
        WHERE id = OLD.snapshot_id AND status = 'locked'
    )) OR (TG_OP <> 'DELETE' AND EXISTS (
        SELECT 1 FROM snapshots_snapshot
        WHERE id = NEW.snapshot_id AND status = 'locked'
    )) THEN
        RAISE EXCEPTION 'jobs of a locked snapshot are immutable'
            USING ERRCODE = '55000';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE OR REPLACE FUNCTION snapshots_reject_locked_frame_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF (TG_OP <> 'INSERT' AND EXISTS (
        SELECT 1
        FROM snapshots_snapshotjob job
        JOIN snapshots_snapshot snapshot ON snapshot.id = job.snapshot_id
        WHERE job.id = OLD.snapshot_job_id AND snapshot.status = 'locked'
    )) OR (TG_OP <> 'DELETE' AND EXISTS (
        SELECT 1
        FROM snapshots_snapshotjob job
        JOIN snapshots_snapshot snapshot ON snapshot.id = job.snapshot_id
        WHERE job.id = NEW.snapshot_job_id AND snapshot.status = 'locked'
    )) THEN
        RAISE EXCEPTION 'frames of a locked snapshot are immutable'
            USING ERRCODE = '55000';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER snapshots_snapshot_no_locked_update_delete
BEFORE UPDATE OR DELETE ON snapshots_snapshot
FOR EACH ROW EXECUTE FUNCTION snapshots_reject_locked_snapshot_mutation();

CREATE TRIGGER snapshots_job_no_locked_mutation
BEFORE INSERT OR UPDATE OR DELETE ON snapshots_snapshotjob
FOR EACH ROW EXECUTE FUNCTION snapshots_reject_locked_job_mutation();

CREATE TRIGGER snapshots_frame_no_locked_mutation
BEFORE INSERT OR UPDATE OR DELETE ON snapshots_snapshotframe
FOR EACH ROW EXECUTE FUNCTION snapshots_reject_locked_frame_mutation();

"""

REVERSE_IMMUTABILITY_SQL = """
DROP TRIGGER IF EXISTS snapshots_frame_no_locked_mutation ON snapshots_snapshotframe;
DROP TRIGGER IF EXISTS snapshots_job_no_locked_mutation ON snapshots_snapshotjob;
DROP TRIGGER IF EXISTS snapshots_snapshot_no_locked_update_delete ON snapshots_snapshot;
DROP FUNCTION IF EXISTS snapshots_reject_locked_frame_mutation();
DROP FUNCTION IF EXISTS snapshots_reject_locked_job_mutation();
DROP FUNCTION IF EXISTS snapshots_reject_locked_snapshot_mutation();
"""


def create_immutability_triggers(_apps: object, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(IMMUTABILITY_SQL)


def drop_immutability_triggers(_apps: object, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(REVERSE_IMMUTABILITY_SQL)


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Snapshot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("dataset_id", models.PositiveBigIntegerField(db_index=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("exporting", "Exporting"),
                            ("locked", "Locked"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("failure_reason", models.CharField(blank=True, max_length=64)),
                ("taxonomy_version", models.CharField(max_length=128)),
                ("guideline_version", models.CharField(max_length=128)),
                ("schema_version", models.CharField(max_length=64)),
                ("revision_sha256", models.CharField(blank=True, db_index=True, max_length=64)),
                ("normalized_json", models.JSONField(default=dict)),
                ("provenance", models.JSONField(default=dict)),
                ("skipped_shape_counts", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_snapshots",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "parent_snapshot",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="child_snapshots",
                        to="snapshots.snapshot",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["dataset_id", "status"], name="snapshot_dataset_status_idx"
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=(
                            ~models.Q(status="locked")
                            | (models.Q(locked_at__isnull=False) & ~models.Q(revision_sha256=""))
                        ),
                        name="snapshot_locked_has_hash_and_time",
                    ),
                    models.CheckConstraint(
                        condition=~models.Q(id=models.F("parent_snapshot_id")),
                        name="snapshot_parent_not_self",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="SnapshotJob",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("cvat_job_id", models.PositiveBigIntegerField()),
                ("cvat_task_id", models.PositiveBigIntegerField()),
                ("assignee_cvat_user_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("source_updated_at", models.CharField(max_length=64)),
                ("sha256", models.CharField(max_length=64)),
                ("normalized_json", models.JSONField()),
                ("rectangle_count", models.PositiveIntegerField(default=0)),
                ("skipped_shape_counts", models.JSONField(default=dict)),
                (
                    "assignee_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="snapshot_job_assignments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "snapshot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="jobs",
                        to="snapshots.snapshot",
                    ),
                ),
            ],
            options={
                "ordering": ["cvat_job_id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("snapshot", "cvat_job_id"),
                        name="snapshot_job_unique_cvat_job",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="SnapshotFrame",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("frame_index", models.PositiveIntegerField()),
                ("source_frame_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("file_name", models.CharField(max_length=512)),
                ("width", models.PositiveIntegerField()),
                ("height", models.PositiveIntegerField()),
                ("media_storage_key", models.CharField(max_length=1024)),
                ("media_sha256", models.CharField(max_length=64)),
                ("media_size_bytes", models.PositiveBigIntegerField()),
                ("media_mime_type", models.CharField(max_length=128)),
                ("shapes", models.JSONField(default=list)),
                ("rectangle_count", models.PositiveIntegerField(default=0)),
                (
                    "snapshot_job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="frames",
                        to="snapshots.snapshotjob",
                    ),
                ),
            ],
            options={
                "ordering": ["frame_index"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("snapshot_job", "frame_index"),
                        name="snapshot_frame_unique_index",
                    )
                ],
            },
        ),
        migrations.RunPython(create_immutability_triggers, drop_immutability_triggers),
    ]
