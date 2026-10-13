from typing import Any

import pytest

from engines.interface import EngineConfig, EngineInput, EngineUnitRef, FrameKey
from orchestration.detector_engine import CLASSES, FROZEN_SHA256, MAPPING_VERSION, run_detector
from orchestration.models import CandidateRecord, VlmBudget, VlmUnit
from orchestration.registry import EngineRegistry
from orchestration.services import commit_shard_output, seed_ledger
from orchestration.vlm_crops import SnapshotCropProvider, candidate_context
from orchestration.vlm_stage import select_candidates_for_vlm, start_vlm_stage
from runs.models import ConfigVersion, ModelArtifact, QCRun
from runs.serializers import CandidateDetectorSerializer, CandidateSerializer
from snapshots.models import SnapshotFrame
from tests.engines.test_detector import detection
from tests.orchestration.test_vlm_crops import FakeStorage, _frame_png
from tests.orchestration.test_vlm_stage import _env, _make_run, _run_shards  # noqa: F401
from vlm.contract import TaxonomyLabel, build_prompt

pytestmark = pytest.mark.django_db(transaction=True)


def setup_run() -> tuple[QCRun, EngineInput, FakeStorage]:
    raw = _frame_png()
    run = _make_run(
        frame_media={0: raw},
        frame_size=(200, 120),
        raw_shapes=[
            {"id": 7, "type": "rectangle", "frame": 0, "label_id": 103, "points": [10, 10, 50, 50]}
        ],
    )
    engines = {
        **run.config_version.engines,
        "detector": {"enabled": True},
        "schema": {
            "enabled": False,
            "params": {
                "taxonomy": {
                    "version": "t",
                    "labels": [
                        {"label_id": i + 100, "name": name} for i, name in enumerate(CLASSES)
                    ],
                }
            },
        },
    }
    cfg = ConfigVersion.objects.create(
        name="detector-test",
        status="published",
        engines=engines,
        models=run.config_version.models,
        created_by=run.created_by,
    )
    model = ModelArtifact.objects.create(
        name="frozen-detector",
        version="v1",
        checksum=FROZEN_SHA256,
        class_mapping_version=MAPPING_VERSION,
        class_mapping={"classes": list(CLASSES)},
    )
    QCRun.objects.filter(pk=run.pk).update(config_version=cfg, model_artifact=model)
    run.refresh_from_db()
    inp = EngineInput(
        "detector-test-key",
        run.pk,
        run.snapshot_id,
        "detector",
        "1.0.0",
        EngineConfig("detector", str(cfg.pk), True, {}),
        42,
        0,
        (EngineUnitRef("frame", FrameKey(9, 0)),),
    )
    frame = SnapshotFrame.objects.get(snapshot_job__snapshot_id=run.snapshot_id, frame_index=0)
    seed_ledger(run.pk, "detector", inp.units)
    return run, inp, FakeStorage({frame.media_storage_key: raw})


class FakeDetector:
    def __init__(self, detections=None):
        self.detections = [detection()] if detections is None else detections
        self.calls = 0

    def predict(self, frame, raw):
        self.calls += 1
        return {
            "schema_version": "labelx.detector.frame.v1",
            "frame": frame,
            "model_sha256": FROZEN_SHA256,
            "class_mapping_version": MAPPING_VERSION,
            "classes": list(CLASSES),
            "detections": self.detections,
        }


def test_registry_registration_idempotent():
    from orchestration.detector_engine import register_detector_engine

    target = EngineRegistry()
    register_detector_engine(target)
    register_detector_engine(target)
    assert target.runner("detector", "1.0.0") is run_detector


def test_snapshot_adapter_commit_and_context():
    run, inp, storage = setup_run()
    output = run_detector(inp, backend=FakeDetector(), storage=storage)
    assert output.unit_results[0].outcome == "completed"
    assert commit_shard_output(inp, output)
    assert not commit_shard_output(inp, output)
    candidate = CandidateRecord.objects.get(run_id=run.pk, engine="detector")
    assert candidate.evidence["source"] == "detector"
    context = candidate_context(candidate, run.snapshot.revision_sha256)
    assert context.current_label == "103" and context.proposed_label == "102"
    prompt = build_prompt(
        "vlm-prompt-v1",
        tuple(TaxonomyLabel(str(i + 100), c) for i, c in enumerate(CLASSES)),
        context,
    )
    assert "103" in prompt and "102" in prompt
    assert SnapshotCropProvider(storage).load(candidate).origin["objects"] == ["shape:7"]
    from tests.orchestration.test_vlm_evidence_api import _candidates

    rows = _candidates(run)
    detector = rows[0]["detector"]
    assert detector["source"] == "detector" and len(detector["top3"]) == 3
    assert detector["top3"][0]["class_id"] == "102"
    serializer = CandidateDetectorSerializer(data=detector)
    assert serializer.is_valid(), serializer.errors


def test_missing_object_crop_and_integrity_fail_closed():
    run, inp, storage = setup_run()
    output = run_detector(
        inp, backend=FakeDetector([detection((80, 10, 120, 50))]), storage=storage
    )
    commit_shard_output(inp, output)
    missing = CandidateRecord.objects.get(run_id=run.pk, anchor__kind="detector_box")
    provider = SnapshotCropProvider(storage)
    assert provider.identity(missing)
    crop = provider.load(missing)
    assert crop.origin["box"] == [80, 10, 120, 50]
    missing.evidence["frame"]["media_sha256"] = "0" * 64
    assert provider.identity(missing) == ""
    no_match = CandidateRecord.objects.get(
        run_id=run.pk, evidence__trigger_reason="detector_no_match"
    )
    assert no_match.pk not in {c.pk for c in select_candidates_for_vlm(run)}
    view = CandidateSerializer(no_match).data["vlm"]
    assert view["reason_code"] == "detector_no_match" and view["source"] == "policy"


def test_unmatched_annotation_no_budget_no_vlm_unit(settings: Any):
    run, inp, storage = setup_run()
    output = run_detector(inp, backend=FakeDetector([]), storage=storage)
    commit_shard_output(inp, output)
    assert start_vlm_stage(run.pk) == 0
    assert not VlmUnit.objects.filter(run_id=run.pk).exists()
    assert VlmBudget.objects.get(run_id=run.pk).used_calls == 0


def test_unmatched_context_blocks_structural_target_but_failure_does_not():
    run, inp, storage = setup_run()
    output = run_detector(inp, backend=FakeDetector([]), storage=storage)
    commit_shard_output(inp, output)
    detector = CandidateRecord.objects.get(run_id=run.pk)
    structural = CandidateRecord.objects.create(
        run=run,
        shard=detector.shard,
        dedup_key="f" * 64,
        engine="geometry",
        engine_version="1.0.0",
        family="E3",
        cvat_task_id=9,
        frame_number=0,
        anchor=detector.anchor,
        policy_version="1.0.0",
        evidence={},
    )
    assert structural.pk not in {c.pk for c in select_candidates_for_vlm(run)}
    # Detector failed before committing: no no-match result exists to block structural candidates.
    other = _make_run()
    _run_shards(other)
    other_shard = CandidateRecord.objects.filter(run_id=other.pk).first().shard
    other_candidate = CandidateRecord.objects.create(
        run=other,
        shard=other_shard,
        dedup_key="e" * 64,
        engine="schema",
        engine_version="1.0.0",
        family="E2",
        cvat_task_id=9,
        frame_number=0,
        anchor=detector.anchor,
        policy_version="1.0.0",
        evidence={},
    )
    assert other_candidate.pk in {c.pk for c in select_candidates_for_vlm(other)}


@pytest.mark.parametrize("failure", ["revision", "model", "classes", "media"])
def test_bad_provenance_rejected_before_commit(failure):
    run, inp, storage = setup_run()

    class WrongDetector(FakeDetector):
        def predict(self, frame, raw):
            data = super().predict(frame, raw)
            if failure == "revision":
                data["frame"] = {**frame, "snapshot_revision": "wrong"}
            elif failure == "model":
                data["model_sha256"] = "0" * 64
            else:
                data["classes"] = list(reversed(CLASSES))
            return data

    if failure == "media":
        key = next(iter(storage.blobs))
        storage.blobs[key] = b"x" * len(storage.blobs[key])
    with pytest.raises(ValueError):
        run_detector(inp, backend=WrongDetector(), storage=storage)
    assert not CandidateRecord.objects.filter(run_id=run.pk, engine="detector").exists()
