"""Tích hợp orchestrator với QCRun/WorkUnit của T-024."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from engines.interface import EngineInput, EngineOutput, EngineUnitResult
from orchestration.dispatch import build_engine_input, dispatch_run, run_work_unit
from orchestration.models import CandidateRecord, ShardCommit
from orchestration.registry import registry
from orchestration.services import ledger_counts
from runs.models import ConfigVersion, QCRun, WorkUnit
from runs.services import create_qc_run
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot

pytestmark = pytest.mark.django_db(transaction=True)

ENGINE = "duplicate_overlap"


@pytest.fixture
def run_setup(db: None):
    user = User.objects.create_user("qa", password="safe-test-password")
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
        annotations={"shapes": [], "tracks": []},
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
        payload={"shard_size": 2, "engines": {ENGINE: {"enabled": True}}},
        engines={ENGINE: {"enabled": True}},
        created_by=user,
        published_by=user,
        published_at=timezone.now(),
    )
    run, _ = create_qc_run(snapshot_id=snap.pk, config_version_id=cfg.pk, seed=1, created_by=user)
    return run


@pytest.fixture
def fake_engine(monkeypatch):
    calls: list[int] = []

    def runner(inp: EngineInput) -> EngineOutput:
        calls.append(inp.shard_index)
        return EngineOutput(
            inp.idempotency_key,
            inp.engine,
            inp.engine_version,
            (),
            tuple(EngineUnitResult(u, "completed", 1) for u in inp.units),
        )

    monkeypatch.setattr(registry, "runner", lambda name, version: runner)
    return calls


def test_engine_input_units_follow_shard_key(run_setup: QCRun):
    sizes = sorted(len(build_engine_input(u).units) for u in run_setup.work_units.all())
    assert sizes == [1, 2]


def test_run_work_units_commit_and_are_idempotent(run_setup: QCRun, fake_engine):
    for unit in run_setup.work_units.all():
        run_work_unit.apply(args=[unit.pk]).get()
    assert set(run_setup.work_units.values_list("status", flat=True)) == {"completed"}
    assert ShardCommit.objects.filter(run_id=run_setup.pk).count() == 2
    counts = ledger_counts(run_setup.pk, ENGINE)
    assert (counts.total, counts.completed, counts.pending) == (3, 3, 0)
    # chạy lại: unit đã completed -> không gọi engine, không đổi dữ liệu
    called = len(fake_engine)
    for unit in run_setup.work_units.all():
        run_work_unit.apply(args=[unit.pk]).get()
    assert len(fake_engine) == called
    assert CandidateRecord.objects.count() == 0


def test_failed_unit_retried_after_retry_failed_keeps_ledger_total(run_setup: QCRun, monkeypatch):
    def boom(name: str, version: str):
        raise LookupError("engine chưa đăng ký")

    monkeypatch.setattr(registry, "runner", boom)
    unit = run_setup.work_units.order_by("shard_index").first()
    with pytest.raises(LookupError):
        run_work_unit.apply(args=[unit.pk]).get()
    unit.refresh_from_db()
    assert unit.status == WorkUnit.Status.FAILED and "chưa đăng ký" in unit.last_error
    counts = ledger_counts(run_setup.pk, ENGINE)
    assert counts.failed == len(build_engine_input(unit).units)
    assert counts.total == counts.eligible


def test_cancelled_run_skips_units(run_setup: QCRun, fake_engine):
    QCRun.objects.filter(pk=run_setup.pk).update(cancel_requested_at=timezone.now())
    unit = run_setup.work_units.first()
    run_work_unit.apply(args=[unit.pk]).get()
    assert fake_engine == []


def test_two_runs_same_input_commit_independently(run_setup: QCRun, fake_engine):
    other, _ = create_qc_run(
        snapshot_id=run_setup.snapshot_id,
        config_version_id=run_setup.config_version_id,
        seed=2,
        created_by=run_setup.created_by,
    )
    for run in (run_setup, other):
        for unit in run.work_units.all():
            run_work_unit.apply(args=[unit.pk]).get()
    assert ShardCommit.objects.count() == 4
    assert dispatch_run(run_setup.pk) == 0  # không còn unit pending
