"""BLOCKER-033: metric matching and real task/ledger execution against PostgreSQL."""

import hashlib
import io
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage
from django.core.management import call_command
from django.utils import timezone

from engines import metric
from engines.interface import EngineConfig, EngineInput, EngineUnitRef, FrameKey
from engines.matching import BoundingBox
from orchestration.dispatch import run_work_unit
from orchestration.models import LedgerUnit, ShardCommit
from orchestration.services import ledger_counts
from runs.models import ModelArtifact, Reference
from runs.services import create_qc_run
from tests.orchestration.helpers import make_run


def box(key, label="car", x=0, ignored=False):
    return BoundingBox(key, label, x, 0, x + 10, 10, ignored=ignored)


def test_precision_recall_counts_wrong_class_duplicate_and_missing():
    truth = [box("a"), box("b", "bus", 30), box("c", "car", 60)]
    pred = [box("p"), box("dup"), box("wrong", "truck", 30)]
    result = metric.count_detections(truth, pred, tau_m=0.5)
    assert result["car"] == {"tp": 1, "fp": 1, "fn": 1, "precision": 0.5, "recall": 0.5}
    assert result["bus"]["fn"] == 1 and result["truck"]["fp"] == 1
    assert result == metric.count_detections(truth[::-1], pred[::-1], tau_m=0.5)


def test_empty_and_ignored_gt_are_not_perfect_scores():
    assert metric.count_detections([], [], tau_m=0.5) == {}
    result = metric.count_detections([box("ignore", ignored=True)], [box("p")], tau_m=0.5)
    assert result["car"] == {"tp": 0, "fp": 1, "fn": 0, "precision": 0, "recall": None}


def test_aggregate_uses_pooled_counts_and_slice_membership():
    details = [
        {"classes": {"car": {"tp": 1, "fp": 0, "fn": 0}}, "slices": ["day"]},
        {"classes": {"car": {"tp": 1, "fp": 8, "fn": 2}}, "slices": ["night"]},
    ]
    result = metric.summarize_metric_details(details)
    assert result["classes"]["car"]["precision"] == 0.2
    assert result["slices"]["day"]["car"]["precision"] == 1


@pytest.fixture
def setup_metric(db, monkeypatch):
    original = make_run(engine="duplicate")
    ref = Reference.objects.create(
        snapshot=original.snapshot,
        gt_source="gt/metric.json",
        gt_checksum="a" * 64,
        mapping_version="bdd100k-det-10-v1",
        algorithm_version="1.0.0",
        status="locked",
        locked_at=timezone.now(),
        created_by=original.created_by,
        locked_by=original.created_by,
    )
    cfg = original.config_version
    cfg.engines = {"metric": {"enabled": True, "params": {"reference_id": ref.pk}}}
    cfg.save()
    artifact = ModelArtifact.objects.create(name="metric-det", version="v1", checksum="b" * 64)
    cfg.models = {"name": artifact.name, "version": artifact.version}
    cfg.save()
    run, _ = create_qc_run(
        snapshot_id=original.snapshot_id,
        config_version_id=cfg.pk,
        seed=42,
        created_by=original.created_by,
    )
    payload = {
        "schema_version": "labelx.metric.gt.v1",
        "snapshot_id": original.snapshot_id,
        "mapping_version": ref.mapping_version,
        "frames": [
            {
                "cvat_task_id": 9,
                "frame_number": i,
                "slices": ["day"],
                "boxes": [{"id": "gt", "label": "car", "bbox_xyxy": [0, 0, 10, 10]}],
            }
            for i in range(3)
        ],
    }
    storage = InMemoryStorage()
    monkeypatch.setattr(metric, "storages", {"snapshots": storage})

    def save_payload():
        raw = json.dumps(payload).encode()
        storage.delete(ref.gt_source)
        storage.save(ref.gt_source, ContentFile(raw))
        ref.gt_checksum = hashlib.sha256(raw).hexdigest()
        ref.save()

    save_payload()

    def predict(inp):
        return (
            {
                u.frame: (
                    SimpleNamespace(
                        snapshot_job=SimpleNamespace(cvat_task_id=9),
                        frame_index=u.frame.frame_number,
                    ),
                    [
                        {
                            "bbox_xyxy": [0, 0, 10, 10],
                            "class_id": 2,
                            "class_name": "car",
                            "confidence": 0.9,
                        }
                    ],
                )
                for u in inp.units
            },
            {"sha256": artifact.checksum, "class_mapping_version": ref.mapping_version},
        )

    predictor = Mock(side_effect=predict)
    monkeypatch.setattr(metric, "predict_frames", predictor)
    inp = EngineInput(
        "metric-shard",
        run.pk,
        run.snapshot_id,
        "metric",
        "1.0.0",
        EngineConfig("metric", str(cfg.pk), True, {"reference_id": ref.pk}),
        42,
        0,
        (EngineUnitRef("frame", FrameKey(9, 0)),),
    )
    return run, ref, payload, save_payload, predictor, inp


@pytest.mark.django_db
def test_metric_celery_runtime_persists_counts_and_replays_without_inference(setup_metric):
    run, ref, _, _, predictor, _ = setup_metric
    for unit in run.work_units.order_by("shard_index"):
        run_work_unit.apply(args=[unit.pk]).get()
    counts = ledger_counts(run.pk, "metric")
    assert (counts.completed, counts.failed, counts.total) == (3, 0, 3)
    assert ShardCommit.objects.filter(run=run).count() == 2
    assert predictor.call_count == 2
    for unit in run.work_units.all():
        run_work_unit.apply(args=[unit.pk]).get()
    assert predictor.call_count == 2
    row = LedgerUnit.objects.filter(run=run).first()
    assert row.details["provenance"]["reference_id"] == ref.pk
    output = io.StringIO()
    call_command("metric_report", run.pk, stdout=output)
    report = json.loads(output.getvalue())
    assert report["metrics"]["classes"]["car"]["tp"] == 3
    assert report["metrics"]["slices"]["day"]["car"]["recall"] == 1
    run.refresh_from_db()
    assert run.status == "completed"


@pytest.mark.parametrize("state", ["missing", "draft", "wrong_snapshot", "missing_frame"])
@pytest.mark.django_db
def test_missing_or_unlocked_gt_is_not_checked(setup_metric, state):
    _, ref, payload, save, predictor, inp = setup_metric
    if state == "missing":
        inp = replace(inp, config=replace(inp.config, params={}))
    elif state == "draft":
        ref.status = "draft"
        ref.save()
    elif state == "wrong_snapshot":
        inp = replace(inp, snapshot_id=inp.snapshot_id + 999)
    else:
        payload["frames"] = []
        save()
    output = metric.run_metric_engine(inp)
    assert output.unit_results[0].outcome == "not_checked"
    assert output.unit_results[0].not_checked_reason == "no_reference"
    predictor.assert_not_called()


@pytest.mark.parametrize("defect", ["checksum", "mapping", "duplicate", "box", "algorithm"])
@pytest.mark.django_db
def test_invalid_gt_fails_instead_of_computing_success(setup_metric, defect):
    _, ref, payload, save, predictor, inp = setup_metric
    if defect == "checksum":
        ref.gt_checksum = "f" * 64
        ref.save()
    elif defect == "algorithm":
        ref.algorithm_version = "unsupported"
        ref.save()
    else:
        if defect == "mapping":
            payload["mapping_version"] = "wrong"
        elif defect == "duplicate":
            payload["frames"].append(payload["frames"][0])
        else:
            payload["frames"][0]["boxes"][0]["bbox_xyxy"] = [1, 2, 0, 3]
        save()
    with pytest.raises(ValueError):
        metric.run_metric_engine(inp)
    predictor.assert_not_called()


@pytest.mark.django_db
def test_explicit_empty_gt_counts_predictions_as_false_positives(setup_metric):
    _, _, payload, save, _, inp = setup_metric
    payload["frames"][0]["boxes"] = []
    save()
    output = metric.run_metric_engine(inp)
    assert output.unit_results[0].details["classes"]["car"]["fp"] == 1


@pytest.mark.django_db
def test_partial_gt_records_missing_frame_without_dropping_denominator(setup_metric):
    _, _, payload, save, predictor, inp = setup_metric
    payload["frames"] = payload["frames"][:1]
    save()
    inp = replace(inp, units=(*inp.units, EngineUnitRef("frame", FrameKey(9, 1))))
    output = metric.run_metric_engine(inp)
    assert [r.outcome for r in output.unit_results] == ["completed", "not_checked"]
    assert output.unit_results[1].not_checked_reason == "no_reference"
    assert len(predictor.call_args.args[0].units) == 1


@pytest.mark.django_db
def test_missing_storage_object_is_no_reference(setup_metric, monkeypatch):
    _, _, _, _, predictor, inp = setup_metric
    monkeypatch.setattr(metric, "_gt_frames", Mock(side_effect=FileNotFoundError))
    assert metric.run_metric_engine(inp).unit_results[0].not_checked_reason == "no_reference"
    predictor.assert_not_called()
