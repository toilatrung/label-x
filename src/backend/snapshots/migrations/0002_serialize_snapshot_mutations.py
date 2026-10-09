"""Serialize child writes with finalization, including existing installations."""

from importlib import import_module

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

LOCKING_SQL = """
CREATE OR REPLACE FUNCTION snapshots_lock_mutable_parents(parent_ids bigint[])
RETURNS void LANGUAGE plpgsql AS $$
DECLARE parent record;
BEGIN
    -- Check status AFTER obtaining the row lock; never filter out mutable rows
    -- before waiting. NO KEY UPDATE permits ordinary FK KEY SHARE checks.
    FOR parent IN
        SELECT id, status FROM snapshots_snapshot
        WHERE id = ANY(parent_ids) ORDER BY id FOR NO KEY UPDATE
    LOOP
        IF parent.status = 'locked' THEN
            RAISE EXCEPTION 'children of a locked snapshot are immutable'
                USING ERRCODE = '55000';
        END IF;
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION snapshots_reject_locked_job_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_ids bigint[] := ARRAY[]::bigint[];
BEGIN
    IF TG_OP <> 'INSERT' THEN
        parent_ids := array_append(parent_ids, OLD.snapshot_id);
    END IF;
    IF TG_OP <> 'DELETE' THEN
        parent_ids := array_append(parent_ids, NEW.snapshot_id);
    END IF;
    PERFORM snapshots_lock_mutable_parents(parent_ids);
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE OR REPLACE FUNCTION snapshots_reject_locked_frame_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    job_ids bigint[] := ARRAY[]::bigint[];
    parent_ids bigint[] := ARRAY[]::bigint[];
    job record;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        job_ids := array_append(job_ids, OLD.snapshot_job_id);
    END IF;
    IF TG_OP <> 'DELETE' THEN
        job_ids := array_append(job_ids, NEW.snapshot_job_id);
    END IF;
    -- Keep the mapping stable while obtaining the parent locks. A concurrent
    -- job reassignment must finish before we read it, or wait for our commit.
    FOR job IN
        SELECT id, snapshot_id FROM snapshots_snapshotjob
        WHERE id = ANY(job_ids) ORDER BY id FOR SHARE
    LOOP
        parent_ids := array_append(parent_ids, job.snapshot_id);
    END LOOP;
    PERFORM snapshots_lock_mutable_parents(parent_ids);
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE OR REPLACE FUNCTION snapshots_reject_locked_snapshot_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    job record;
    frames_json jsonb;
    job_json jsonb;
    jobs_json jsonb := '[]'::jsonb;
    skipped_json jsonb;
    rectangle_total bigint;
BEGIN
    IF TG_OP <> 'INSERT' AND OLD.status = 'locked' THEN
        RAISE EXCEPTION 'locked snapshot is immutable' USING ERRCODE = '55000';
    END IF;
    IF TG_OP <> 'DELETE' AND NEW.status = 'locked' THEN
        -- UPDATE has already locked this parent row. Child triggers take the
        -- same lock, so these reads see a stable committed aggregate. Reject a
        -- stale caller-supplied aggregate instead of freezing it after a wait.
        FOR job IN
            SELECT * FROM snapshots_snapshotjob
            WHERE snapshot_id = NEW.id ORDER BY cvat_job_id
        LOOP
            IF EXISTS (
                SELECT 1 FROM snapshots_snapshotframe
                WHERE snapshot_job_id = job.id
                AND rectangle_count <> jsonb_array_length(shapes)
            ) THEN
                RAISE EXCEPTION 'snapshot frame counts must match shapes before locking'
                    USING ERRCODE = '55000';
            END IF;
            SELECT COALESCE(jsonb_agg(jsonb_build_object(
                'file_name', file_name, 'frame_index', frame_index,
                'height', height, 'width', width,
                'source_frame_id', source_frame_id, 'shapes', shapes,
                'media', jsonb_build_object(
                    'mime_type', media_mime_type, 'sha256', media_sha256,
                    'size_bytes', media_size_bytes, 'storage_key', media_storage_key
                )
            ) ORDER BY frame_index), '[]'::jsonb),
            COALESCE(sum(jsonb_array_length(shapes)), 0)
            INTO frames_json, rectangle_total
            FROM snapshots_snapshotframe WHERE snapshot_job_id = job.id;
            job_json := jsonb_build_object(
                'assignee_cvat_user_id', job.assignee_cvat_user_id,
                'assignee_user_id', job.assignee_user_id,
                'cvat_job_id', job.cvat_job_id, 'cvat_task_id', job.cvat_task_id,
                'frames', frames_json, 'schema_version', NEW.schema_version,
                'skipped_shapes', job.skipped_shape_counts,
                'source_updated_at', job.source_updated_at
            );
            IF frames_json = '[]'::jsonb OR job.rectangle_count <> rectangle_total
                OR job.normalized_json IS DISTINCT FROM job_json THEN
                RAISE EXCEPTION 'snapshot jobs must match persisted frames before locking'
                    USING ERRCODE = '55000';
            END IF;
            jobs_json := jobs_json || jsonb_build_array(job_json);
        END LOOP;
        SELECT COALESCE(jsonb_object_agg(key, total), '{}'::jsonb)
        INTO skipped_json FROM (
            SELECT counts.key, sum(counts.value::bigint) AS total
            FROM snapshots_snapshotjob stored_job,
                jsonb_each_text(stored_job.skipped_shape_counts) counts
            WHERE stored_job.snapshot_id = NEW.id GROUP BY counts.key
        ) counts;
        IF jobs_json = '[]'::jsonb OR NEW.normalized_json IS DISTINCT FROM
            jsonb_build_object(
                'dataset_id', NEW.dataset_id, 'guideline_version', NEW.guideline_version,
                'jobs', jobs_json, 'schema_version', NEW.schema_version,
                'taxonomy_version', NEW.taxonomy_version
            ) OR NEW.skipped_shape_counts IS DISTINCT FROM skipped_json THEN
            RAISE EXCEPTION 'snapshot aggregate must match persisted jobs before locking'
                USING ERRCODE = '55000';
        END IF;
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

DROP TRIGGER snapshots_snapshot_no_locked_update_delete ON snapshots_snapshot;
CREATE TRIGGER snapshots_snapshot_no_locked_update_delete
BEFORE INSERT OR UPDATE OR DELETE ON snapshots_snapshot
FOR EACH ROW EXECUTE FUNCTION snapshots_reject_locked_snapshot_mutation();
"""


def install(_apps: object, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(LOCKING_SQL)


def uninstall(_apps: object, schema_editor: BaseDatabaseSchemaEditor) -> None:
    if schema_editor.connection.vendor == "postgresql":
        original = import_module("snapshots.migrations.0001_initial")
        schema_editor.execute(original.REVERSE_IMMUTABILITY_SQL)
        schema_editor.execute("DROP FUNCTION snapshots_lock_mutable_parents(bigint[])")
        schema_editor.execute(original.IMMUTABILITY_SQL)


class Migration(migrations.Migration):
    dependencies = [("snapshots", "0001_initial")]
    operations = [migrations.RunPython(install, uninstall)]
