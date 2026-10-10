"""Dữ liệu dựng sẵn cho test orchestration."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.utils import timezone

from runs.models import ConfigVersion
from runs.services import create_qc_run
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot


def make_run(engine: str = "fake", *, shapes: list | None = None, seed: int = 1):
    """QCRun thật (3 frame, shard_size=2) trên snapshot khoá thật."""
    user, _ = User.objects.get_or_create(username="qa")
    frames = tuple(
        FrameExport(
            frame_index=i,
            source_frame_id=1000 + i,
            file_name=f"{i}.jpg",
            width=10,
            height=10,
            media_bytes=f"frame-{i}".encode(),
            media_storage_key=f"snapshots/orch/{i}.jpg",
        )
        for i in range(3)
    )
    job = JobExport(
        cvat_job_id=5,
        cvat_task_id=9,
        source_updated_at="2026-10-09T07:05:45Z",
        annotations={"shapes": shapes or [], "tracks": []},
        frames=frames,
        assignee_cvat_user_id=None,
    )
    snap = create_locked_snapshot(
        dataset_id=1,
        created_by=user,
        jobs=[job],
        taxonomy_version="t",
        guideline_version="g",
    )
    cfg = ConfigVersion.objects.create(
        name="c",
        status=ConfigVersion.Status.PUBLISHED,
        payload={"shard_size": 2, "engines": {engine: {"enabled": True}}},
        engines={engine: {"enabled": True}},
        created_by=user,
        published_by=user,
        published_at=timezone.now(),
    )
    run, _ = create_qc_run(
        snapshot_id=snap.pk, config_version_id=cfg.pk, seed=seed, created_by=user
    )
    return run
