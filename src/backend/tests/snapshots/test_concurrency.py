"""Real PostgreSQL interleavings; events and pg_blocking_pids replace timing guesses."""

from __future__ import annotations

import copy
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from typing import Any

import psycopg
import pytest
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from psycopg.types.json import Jsonb

from snapshots.models import Snapshot, SnapshotJob
from snapshots.normalization import (
    SCHEMA_VERSION,
    FrameExport,
    JobExport,
    normalize_job,
    sha256_json,
)
from snapshots.services import _persist_job, lock_snapshot

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def postgres_only() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("concurrent row-lock guarantees require PostgreSQL")


def mutable_snapshot(name: str) -> Snapshot:
    snapshot = Snapshot.objects.create(
        dataset_id=42,
        status=Snapshot.Status.EXPORTING,
        taxonomy_version="bdd100k-10-v1",
        guideline_version="v1",
        schema_version=SCHEMA_VERSION,
        created_by=get_user_model().objects.create(username=name),
    )
    export = JobExport(
        cvat_job_id=17,
        cvat_task_id=9,
        source_updated_at="initial",
        annotations={
            "shapes": [
                {
                    "id": 1,
                    "frame": 0,
                    "type": "rectangle",
                    "label_id": 4,
                    "points": [2.0, 2.0, 10.0, 5.0],
                }
            ],
            "tracks": [],
        },
        frames=[FrameExport(0, "frame.jpg", 20, 10, b"fixture", "fixture/frame.jpg")],
    )
    _persist_job(snapshot, export, normalize_job(export))
    return snapshot


def wait_for_blocked(pid: int, blocker: int) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_blocking_pids(%s)", [pid])
            if blocker in cursor.fetchone()[0]:
                return
        time.sleep(0.01)
    pytest.fail(f"backend {pid} never waited for transaction {blocker}")


def sql_writer(params: dict[str, Any], sql: str, args: list[Any], started: Queue[int]) -> None:
    with psycopg.connect(**params) as writer:
        writer.execute("SET lock_timeout = '5s'")
        writer.execute("SET statement_timeout = '8s'")
        started.put(writer.info.backend_pid)
        writer.execute(sql, args)


def finalizer(snapshot: Snapshot, started: Queue[int]) -> Snapshot:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '5s'")
            cursor.execute("SELECT pg_backend_pid()")
            started.put(cursor.fetchone()[0])
        return lock_snapshot(snapshot)
    finally:
        connections["default"].close()


@pytest.mark.parametrize("kind", ["job", "frame"])
def test_writer_first_finalizer_waits_and_hashes_committed_data(kind: str) -> None:
    snapshot = mutable_snapshot("writer-first")
    job, original = snapshot.jobs.get(), lock_snapshot_hash_preview(snapshot)
    payload = copy.deepcopy(job.normalized_json)
    with ThreadPoolExecutor(max_workers=1) as executor:
        with psycopg.connect(**connection.get_connection_params()) as writer:
            if kind == "frame":
                frame = job.frames.get()
                payload["frames"][0]["shapes"][0]["points"][0] = 3.0
                writer.execute(
                    "UPDATE snapshots_snapshotframe SET shapes=%s WHERE id=%s",
                    [Jsonb(payload["frames"][0]["shapes"]), frame.pk],
                )
            else:
                payload["source_updated_at"] = "committed-writer"
            digest = sha256_json(payload)
            writer.execute(
                "UPDATE snapshots_snapshotjob SET source_updated_at=%s, normalized_json=%s, "
                "sha256=%s WHERE id=%s",
                [payload["source_updated_at"], Jsonb(payload), digest, job.pk],
            )
            started: Queue[int] = Queue()
            future = executor.submit(finalizer, snapshot, started)
            wait_for_blocked(started.get(timeout=5), writer.info.backend_pid)
            writer.commit()
        locked = future.result(timeout=8)
    assert locked.status == "locked"
    assert locked.normalized_json["jobs"] == [payload]
    assert locked.revision_sha256 == sha256_json(locked.normalized_json) != original
    assert locked.jobs.get().sha256 == digest


def lock_snapshot_hash_preview(snapshot: Snapshot) -> str:
    return sha256_json(
        {
            "dataset_id": snapshot.dataset_id,
            "guideline_version": snapshot.guideline_version,
            "jobs": [snapshot.jobs.get().normalized_json],
            "schema_version": snapshot.schema_version,
            "taxonomy_version": snapshot.taxonomy_version,
        }
    )


def test_waiting_raw_finalizer_cannot_freeze_aggregate_read_before_wait() -> None:
    snapshot = mutable_snapshot("stale-finalizer")
    job = snapshot.jobs.get()
    old_payload = {
        "dataset_id": snapshot.dataset_id,
        "guideline_version": snapshot.guideline_version,
        "jobs": [job.normalized_json],
        "schema_version": snapshot.schema_version,
        "taxonomy_version": snapshot.taxonomy_version,
    }
    changed = copy.deepcopy(job.normalized_json)
    changed["source_updated_at"] = "committed-writer"
    with ThreadPoolExecutor(max_workers=1) as executor:
        with psycopg.connect(**connection.get_connection_params()) as writer:
            writer.execute(
                "UPDATE snapshots_snapshotjob SET source_updated_at=%s, "
                "normalized_json=%s, sha256=%s WHERE id=%s",
                [changed["source_updated_at"], Jsonb(changed), sha256_json(changed), job.pk],
            )
            started: Queue[int] = Queue()
            future = executor.submit(
                sql_writer,
                connection.get_connection_params(),
                "UPDATE snapshots_snapshot SET status='locked', locked_at=now(), "
                "normalized_json=%s, revision_sha256=%s WHERE id=%s",
                [Jsonb(old_payload), sha256_json(old_payload), snapshot.pk],
                started,
            )
            wait_for_blocked(started.get(timeout=5), writer.info.backend_pid)
            writer.commit()
        with pytest.raises(psycopg.Error, match="aggregate must match.*before locking"):
            future.result(timeout=8)
    snapshot.refresh_from_db()
    assert snapshot.status == "exporting"
    assert lock_snapshot(snapshot).normalized_json["jobs"] == [changed]


def mutation(kind: str, operation: str, job: SnapshotJob) -> tuple[str, list[Any]]:
    row_id = job.pk if kind == "job" else job.frames.get().pk
    table = "snapshots_snapshotjob" if kind == "job" else "snapshots_snapshotframe"
    if operation == "update":
        return f"UPDATE {table} SET rectangle_count=99 WHERE id=%s", [row_id]
    if operation == "delete":
        return f"DELETE FROM {table} WHERE id=%s", [row_id]
    if kind == "job":
        return (
            "INSERT INTO snapshots_snapshotjob (snapshot_id,cvat_job_id,cvat_task_id,"
            "assignee_cvat_user_id,assignee_user_id,source_updated_at,sha256,normalized_json,"
            "rectangle_count,skipped_shape_counts) SELECT snapshot_id,cvat_job_id+100,"
            "cvat_task_id,assignee_cvat_user_id,assignee_user_id,source_updated_at,sha256,"
            "normalized_json,rectangle_count,skipped_shape_counts "
            "FROM snapshots_snapshotjob WHERE id=%s",
            [row_id],
        )
    return (
        "INSERT INTO snapshots_snapshotframe (snapshot_job_id,frame_index,source_frame_id,"
        "file_name,width,height,media_storage_key,media_sha256,media_size_bytes,"
        "media_mime_type,shapes,rectangle_count) SELECT snapshot_job_id,frame_index+100,"
        "source_frame_id,file_name,width,height,media_storage_key,media_sha256,"
        "media_size_bytes,media_mime_type,shapes,rectangle_count "
        "FROM snapshots_snapshotframe WHERE id=%s",
        [row_id],
    )


@pytest.mark.parametrize("kind", ["job", "frame"])
@pytest.mark.parametrize("operation", ["insert", "update", "delete"])
def test_finalizer_first_waiting_writer_rechecks_locked_parent(kind: str, operation: str) -> None:
    snapshot = mutable_snapshot("lock-first")
    sql, args = mutation(kind, operation, snapshot.jobs.get())
    params = connection.get_connection_params()
    with ThreadPoolExecutor(max_workers=1) as executor:
        with transaction.atomic():
            locked = lock_snapshot(snapshot)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                blocker = cursor.fetchone()[0]
            started: Queue[int] = Queue()
            future = executor.submit(sql_writer, params, sql, args, started)
            wait_for_blocked(started.get(timeout=5), blocker)
        with pytest.raises(psycopg.Error, match="immutable"):
            future.result(timeout=8)
    assert locked.jobs.count() == locked.jobs.get().frames.count() == 1
    assert locked.jobs.get().rectangle_count == locked.jobs.get().frames.get().rectangle_count == 1
    assert locked.revision_sha256 == sha256_json(locked.normalized_json)


@pytest.mark.parametrize("kind", ["job", "frame"])
@pytest.mark.parametrize("operation", ["insert", "update", "delete"])
def test_writes_started_after_lock_are_rejected(kind: str, operation: str) -> None:
    snapshot = lock_snapshot(mutable_snapshot("after-lock"))
    sql, args = mutation(kind, operation, snapshot.jobs.get())
    with pytest.raises(psycopg.Error, match="immutable"):
        sql_writer(connection.get_connection_params(), sql, args, Queue())


@pytest.mark.parametrize("kind", ["job", "frame"])
@pytest.mark.parametrize("locked_endpoint", ["source", "destination"])
def test_reassignment_checks_both_parents(kind: str, locked_endpoint: str) -> None:
    source, destination = mutable_snapshot("source"), mutable_snapshot("destination")
    lock_snapshot(source if locked_endpoint == "source" else destination)
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        if kind == "job":
            source.jobs.update(snapshot=destination)
        else:
            source.jobs.get().frames.update(snapshot_job=destination.jobs.get())


def test_frame_writer_holds_job_mapping_against_reassignment() -> None:
    source, destination = mutable_snapshot("source"), mutable_snapshot("destination")
    destination.jobs.all().delete()
    job = source.jobs.get()
    frame = job.frames.get()
    with ThreadPoolExecutor(max_workers=1) as executor:
        with psycopg.connect(**connection.get_connection_params()) as writer:
            writer.execute(
                "UPDATE snapshots_snapshotframe SET file_name='changed.jpg' WHERE id=%s", [frame.pk]
            )
            started: Queue[int] = Queue()
            future = executor.submit(
                sql_writer,
                connection.get_connection_params(),
                "UPDATE snapshots_snapshotjob SET snapshot_id=%s WHERE id=%s",
                [destination.pk, job.pk],
                started,
            )
            wait_for_blocked(started.get(timeout=5), writer.info.backend_pid)
            writer.commit()
        future.result(timeout=8)
    assert SnapshotJob.objects.get(pk=job.pk).snapshot_id == destination.pk


@pytest.mark.parametrize("kind", ["job", "frame"])
def test_inconsistent_child_cache_cannot_be_frozen(kind: str) -> None:
    snapshot = mutable_snapshot("stale-cache")
    job = snapshot.jobs.get()
    if kind == "job":
        snapshot.jobs.update(rectangle_count=99)
    else:
        job.frames.update(file_name="changed.jpg")
    with pytest.raises(DatabaseError, match="before locking"):
        lock_snapshot(snapshot)
    snapshot.refresh_from_db()
    assert snapshot.status == "exporting"


def test_service_rejects_stale_job_hash() -> None:
    snapshot = mutable_snapshot("stale-hash")
    snapshot.jobs.update(sha256="0" * 64)
    with pytest.raises(ValueError, match="job hash"):
        lock_snapshot(snapshot)
    snapshot.refresh_from_db()
    assert snapshot.status == "exporting"


def test_migration_upgrades_existing_snapshot_data() -> None:
    executor = MigrationExecutor(connection)
    executor.migrate([("snapshots", "0001_initial")])
    try:
        snapshot = lock_snapshot(mutable_snapshot("before-upgrade"))
        original_hash = snapshot.revision_sha256
    finally:
        MigrationExecutor(connection).migrate([("snapshots", "0002_serialize_snapshot_mutations")])
    snapshot.refresh_from_db()
    assert snapshot.revision_sha256 == original_hash
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        snapshot.jobs.update(rectangle_count=99)
