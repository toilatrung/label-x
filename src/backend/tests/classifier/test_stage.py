"""M04B-03: stage classifier theo candidate (runner giả; KHÔNG phải runtime pass thật)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from classifier.config import CLASS_MAP_VERSION
from classifier.errors import ClassifierReason, ClassifierRunError
from classifier.runner import BatchResult, ItemResult
from engines.interface import (
    Anchor,
    Candidate,
    EngineInput,
    EngineOutput,
    EngineUnitResult,
    ObjectRef,
)
from orchestration.classifier_stage import (
    _annotated_class_id,
    classifier_units_open,
    compute_classifier_idempotency_key,
    execute_classifier_units,
    start_classifier_stage,
)
from orchestration.dispatch import redispatch_pending, run_work_unit
from orchestration.models import CandidateRecord, ClassifierUnit
from orchestration.registry import registry
from runs.models import ConfigVersion, QCRun
from runs.serializers import CandidateSerializer
from runs.services import cancel_qc_run, create_qc_run
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot
from tests.classifier.test_config import SHA, make_artifact
from tests.vlm.test_contract import PNG
from vlm.contract import CropInput
from vlm.errors import VlmInvalidCropError

pytestmark = pytest.mark.django_db(transaction=True)
ENGINE = "duplicate_overlap"
TAXONOMY = {
    "version": "t",
    "labels": [{"label_id": 1, "name": "car"}, {"label_id": 2, "name": "person"}],
}
CHECKPOINT = {
    "version": "smoke-1",
    "sha256": SHA,
    "status": "smoke_only",
    "class_map_version": CLASS_MAP_VERSION,
}


def prediction(score: float = 0.7, margin: float = 0.5) -> dict[str, Any]:
    return {
        "top3": [
            {"class_id": 2, "class_name": "car", "score": score},
            {"class_id": 3, "class_name": "truck", "score": score - margin},
            {"class_id": 4, "class_name": "bus", "score": 0.05},
        ],
        "score": score,
        "margin": margin,
        "calibrated": False,
    }


class FixtureCrops:
    def identity(self, candidate: Any) -> str:
        return f"fixture-{candidate.pk}"

    def load(self, candidate: Any) -> CropInput:
        return CropInput(PNG, "image/png")


class BrokenCrops(FixtureCrops):
    def load(self, candidate: Any) -> CropInput:
        raise VlmInvalidCropError("hỏng")


class FakeRunner:
    def __init__(self, behaviour: Any = None) -> None:
        self.calls: list[list[str]] = []
        self.behaviour = behaviour

    def run(self, *, artifact_key: str, expected_sha256: str, crops: Any) -> BatchResult:
        self.calls.append([c.item_id for c in crops])
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        items = {}
        for crop in crops:
            if callable(self.behaviour):
                items[crop.item_id] = self.behaviour(crop.item_id)
            else:
                items[crop.item_id] = ItemResult(crop.item_id, True, prediction=prediction())
        return BatchResult(checkpoint=dict(CHECKPOINT), items=items)


def make_run(*, artifact_ok: bool = True) -> QCRun:
    user, _ = User.objects.get_or_create(username="qa")
    frames = tuple(
        FrameExport(
            frame_index=i,
            source_frame_id=1000 + i,
            file_name=f"{i}.jpg",
            width=10,
            height=10,
            media_bytes=f"frame-{i}".encode(),
            media_storage_key=f"snapshots/clf/{i}.jpg",
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
        dataset_id=1, created_by=user, jobs=[job], taxonomy_version="t", guideline_version="g"
    )
    artifact = make_artifact(**({} if artifact_ok else {"checksum": "bad"}))
    cfg = ConfigVersion.objects.create(
        name="c",
        status=ConfigVersion.Status.PUBLISHED,
        payload={"shard_size": 2},
        engines={
            ENGINE: {"enabled": True},
            "classifier": {"enabled": True},
            "schema": {"enabled": False, "params": {"taxonomy": TAXONOMY}},
        },
        models={"classifier": {"model_artifact_id": artifact.pk}},
        created_by=user,
        published_by=user,
        published_at=timezone.now(),
    )
    run, _ = create_qc_run(snapshot_id=snap.pk, config_version_id=cfg.pk, seed=1, created_by=user)
    return run


@pytest.fixture(autouse=True)
def _env(settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    settings.VLM_CROP_PROVIDER = "tests.classifier.test_stage.FixtureCrops"
    settings.ORCHESTRATION_AUTO_DISPATCH = False

    def runner(inp: EngineInput) -> EngineOutput:
        candidates = tuple(
            Candidate(
                engine=inp.engine,
                engine_version=inp.engine_version,
                family="E1",
                frame=u.frame,
                anchor=Anchor(
                    "annotation", (ObjectRef("cvat", f"{u.frame.frame_number}"),), "p", "r"
                ),
                evidence={"frame": u.frame.frame_number, "confidence": 0.9},
            )
            for u in inp.units
        )
        return EngineOutput(
            inp.idempotency_key,
            inp.engine,
            inp.engine_version,
            candidates,
            tuple(EngineUnitResult(u, "completed", 1) for u in inp.units),
        )

    monkeypatch.setattr(registry, "runner", lambda name, version: runner)
    from orchestration import classifier_stage

    monkeypatch.setattr(classifier_stage.run_classifier_units_task, "delay", lambda *a, **k: None)


def run_shards(run: QCRun, only: int | None = None) -> None:
    units = list(run.work_units.order_by("shard_index"))
    for unit in units[: only if only is not None else len(units)]:
        run_work_unit.apply(args=[unit.pk]).get()


def result(run: QCRun) -> Any:
    return run.engine_results.get(engine="classifier")


def test_units_only_after_all_candidate_shards_finish() -> None:
    run = make_run()
    assert not ClassifierUnit.objects.exists()
    run_shards(run, only=1)
    assert not ClassifierUnit.objects.exists()
    run_shards(run)
    assert ClassifierUnit.objects.filter(run_id=run.pk).count() == 3
    run.refresh_from_db()
    assert run.status == QCRun.Status.RUNNING  # classifier chưa chạy: run chưa chốt
    assert classifier_units_open(run.pk)


def test_full_flow_persists_proposal_and_completes_run() -> None:
    run = make_run()
    run_shards(run)
    runner = FakeRunner()
    assert execute_classifier_units(run.pk, runner=runner) == 3
    run.refresh_from_db()
    assert run.status == QCRun.Status.COMPLETED
    assert (result(run).status, result(run).eligible_units, result(run).completed_units) == (
        "checked",
        3,
        3,
    )
    unit = ClassifierUnit.objects.filter(run_id=run.pk).first()
    assert unit.status == "completed" and unit.crop_valid and unit.reason_code == ""
    assert (unit.predicted_class_id, unit.predicted_class_name) == (2, "car")
    assert unit.score == pytest.approx(0.7) and unit.margin == pytest.approx(0.5)
    assert [e["class_name"] for e in unit.top3] == ["car", "truck", "bus"]
    assert unit.classifier_unknown is False  # abstention thuộc policy, không phải classifier
    assert (unit.checkpoint_version, unit.checkpoint_sha256, unit.class_map_version) == (
        "smoke-1",
        SHA,
        CLASS_MAP_VERSION,
    )
    assert unit.checkpoint_status == "smoke_only" and len(unit.crop_sha256) == 64
    assert len(runner.calls) == 1  # một batch cho cả run


def test_idempotent_no_recompute_and_no_duplicate_units() -> None:
    run = make_run()
    run_shards(run)
    runner = FakeRunner()
    execute_classifier_units(run.pk, runner=runner)
    assert execute_classifier_units(run.pk, runner=runner) == 0
    assert len(runner.calls) == 1
    run_id = run.pk
    from django.db import transaction

    with transaction.atomic():
        QCRun.objects.select_for_update().get(pk=run_id)
        assert start_classifier_stage(run_id) == 0
    assert ClassifierUnit.objects.filter(run_id=run_id).count() == 3


def test_idempotency_key_depends_on_checkpoint_and_crop() -> None:
    base = dict(
        candidate_dedup_key="d",
        crop_identity="c",
        snapshot_revision="r",
        checkpoint_sha256="s",
        class_map_version="m",
    )
    key = compute_classifier_idempotency_key(**base)
    for field in base:
        assert compute_classifier_idempotency_key(**{**base, field: "other"}) != key


def test_invalid_crop_is_a_clear_reason_and_does_not_fail_run(settings: Any) -> None:
    settings.VLM_CROP_PROVIDER = "tests.classifier.test_stage.BrokenCrops"
    run = make_run()
    run_shards(run)
    runner = FakeRunner()
    execute_classifier_units(run.pk, runner=runner)
    assert runner.calls == []  # không có crop hợp lệ thì không gọi worker
    unit = ClassifierUnit.objects.filter(run_id=run.pk).first()
    assert (unit.status, unit.reason_code, unit.crop_valid) == ("failed", "invalid_crop", False)
    run.refresh_from_db()
    assert run.status == QCRun.Status.COMPLETED  # engine classifier không bắt buộc
    assert result(run).failed_units == 3


def test_per_item_failure_does_not_fail_the_others() -> None:
    run = make_run()
    run_shards(run)
    first = ClassifierUnit.objects.filter(run_id=run.pk).order_by("pk").first()

    def behaviour(item_id: str) -> ItemResult:
        if item_id == str(first.pk):
            return ItemResult(item_id, False, reason="box_too_small")
        return ItemResult(item_id, True, prediction=prediction())

    execute_classifier_units(run.pk, runner=FakeRunner(behaviour))
    first.refresh_from_db()
    assert (first.status, first.reason_code, first.crop_valid) == ("failed", "box_too_small", False)
    assert ClassifierUnit.objects.filter(run_id=run.pk, status="completed").count() == 2


@pytest.mark.parametrize(
    "reason",
    [ClassifierReason.CHECKSUM_MISMATCH, ClassifierReason.TIMEOUT, ClassifierReason.NOT_CONFIGURED],
)
def test_batch_failure_gives_stable_reason_for_every_unit(reason: ClassifierReason) -> None:
    run = make_run()
    run_shards(run)
    execute_classifier_units(run.pk, runner=FakeRunner(ClassifierRunError(reason)))
    codes = set(ClassifierUnit.objects.filter(run_id=run.pk).values_list("reason_code", flat=True))
    assert codes == {reason.value}
    run.refresh_from_db()
    assert run.status == QCRun.Status.COMPLETED


def test_runner_crash_is_contained() -> None:
    run = make_run()
    run_shards(run)
    execute_classifier_units(run.pk, runner=FakeRunner(RuntimeError("boom /secret/path")))
    unit = ClassifierUnit.objects.filter(run_id=run.pk).first()
    assert unit.reason_code == "inference_error"
    assert "secret" not in str(unit.__dict__)


def test_non_finite_scores_are_inference_error() -> None:
    run = make_run()
    run_shards(run)
    bad = prediction()
    bad["score"] = float("nan")
    execute_classifier_units(
        run.pk, runner=FakeRunner(lambda i: ItemResult(i, True, prediction=bad))
    )
    assert set(ClassifierUnit.objects.values_list("reason_code", flat=True)) == {"inference_error"}


def test_unready_artifact_means_engine_not_run() -> None:
    run = make_run(artifact_ok=False)
    assert "classifier" not in (run.engine_versions or {})
    assert result(run).status == "not_checked" and result(run).reason == "no_model"
    run_shards(run)
    assert not ClassifierUnit.objects.exists()
    run.refresh_from_db()
    assert run.status == QCRun.Status.COMPLETED


def test_cancelled_run_is_not_processed() -> None:
    run = make_run()
    run_shards(run)
    user = User.objects.get(username="qa")
    cancel_qc_run(run_id=run.pk, actor=user)
    runner = FakeRunner()
    execute_classifier_units(run.pk, runner=runner)
    assert runner.calls == []


def test_sweeper_recovers_stale_running_units() -> None:
    run = make_run()
    run_shards(run)
    old = timezone.now() - timedelta(hours=2)
    ClassifierUnit.objects.filter(run_id=run.pk).update(status="running", started_at=old)
    redispatch_pending(older_than_seconds=0, running_stale_seconds=60)
    assert set(ClassifierUnit.objects.values_list("status", flat=True)) == {"pending"}


def test_candidate_api_exposes_classifier_without_calibration_claims() -> None:
    run = make_run()
    run_shards(run)
    execute_classifier_units(run.pk, runner=FakeRunner())
    candidate = CandidateRecord.objects.filter(run_id=run.pk).first()
    data = CandidateSerializer(candidate).data["classifier"]
    assert data["status"] == "completed" and data["predicted_class_name"] == "car"
    assert (
        data["class_map_version"] == CLASS_MAP_VERSION and data["checkpoint_version"] == "smoke-1"
    )
    assert data["classifier_unknown"] is False and len(data["top3"]) == 3
    assert "probability" not in data and "calibrated" not in data
    other = CandidateRecord.objects.filter(run_id=run.pk).exclude(pk=candidate.pk).first()
    ClassifierUnit.objects.filter(candidate=other).delete()
    assert CandidateSerializer(other).data["classifier"] is None


def test_annotated_class_from_snapshot_label() -> None:
    candidate = CandidateRecord(
        cvat_task_id=9, frame_number=0, anchor={"objects": [{"namespace": "cvat", "id": "7"}]}
    )
    index = {(9, 0, "7"): 1}
    assert _annotated_class_id(candidate, index, {1: "Car"}) == 2
    assert _annotated_class_id(candidate, index, {1: "person"}) is None  # ngoài class map
    assert _annotated_class_id(candidate, {}, {1: "car"}) is None  # không truy ra annotation
