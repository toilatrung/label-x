"""Opt-in real GPU integration. Snapshot/storage and Qwen are isolated test fixtures."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User

from engines.interface import EngineConfig, EngineInput, EngineUnitRef, FrameKey
from orchestration.detector_engine import (
    CLASSES,
    FROZEN_SHA256,
    MAPPING_VERSION,
    HttpDetector,
    run_detector,
)
from orchestration.models import CandidateRecord, VlmEvidence, VlmUnit
from orchestration.services import commit_shard_output, seed_ledger
from orchestration.vlm_crops import SnapshotCropProvider
from orchestration.vlm_stage import execute_vlm_unit, start_vlm_stage
from runs.models import ConfigVersion, ModelArtifact
from runs.services import create_qc_run
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot
from tests.orchestration.test_vlm_crops import FakeStorage
from tests.orchestration.test_vlm_stage import VALID, FakeClient

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        not os.environ.get("LABELX_DETECTOR_RUNTIME_SAMPLE"),
        reason="requires explicit permitted real sample and warm GPU worker",
    ),
]


def test_real_gpu_snapshot_candidate_crop_vlm_bridge(settings):
    raw = Path(os.environ["LABELX_DETECTOR_RUNTIME_SAMPLE"]).read_bytes()
    settings.DETECTOR_WORKER_URL = os.environ["DETECTOR_WORKER_URL"]
    settings.DETECTOR_SERVICE_TOKEN = os.environ["DETECTOR_SERVICE_TOKEN"]
    user = User.objects.create(username="real-gpu-isolated")
    frame = FrameExport(
        frame_index=0,
        source_frame_id=0,
        file_name="bdd100k-val.jpg",
        width=1280,
        height=720,
        media_bytes=raw,
        media_storage_key="isolated/frame.jpg",
    )
    job = JobExport(
        cvat_job_id=18,
        cvat_task_id=21,
        source_updated_at="runtime-test",
        annotations={"shapes": [], "tracks": []},
        frames=(frame,),
        assignee_cvat_user_id=None,
    )
    snapshot = create_locked_snapshot(
        dataset_id=3,
        created_by=user,
        jobs=[job],
        taxonomy_version="bdd100k-runtime-test",
        guideline_version="test",
    )
    cfg = ConfigVersion.objects.create(
        name="real GPU fixture",
        status="published",
        created_by=user,
        engines={
            "detector": {"enabled": True},
            "vlm": {"enabled": True},
            "schema": {
                "enabled": False,
                "params": {
                    "taxonomy": {
                        "version": snapshot.taxonomy_version,
                        "labels": [
                            {"label_id": i + 100, "name": name} for i, name in enumerate(CLASSES)
                        ],
                    }
                },
            },
        },
        models={
            "detector": {"name": "frozen", "version": "v1"},
            "vlm": {**VALID, "prompt_version": "vlm-prompt-v1"},
        },
    )
    ModelArtifact.objects.create(
        name="frozen",
        version="v1",
        checksum=FROZEN_SHA256,
        class_mapping_version=MAPPING_VERSION,
        class_mapping={"classes": list(CLASSES)},
    )
    run, _ = create_qc_run(
        snapshot_id=snapshot.pk, config_version_id=cfg.pk, seed=42, created_by=user
    )
    inp = EngineInput(
        "real-gpu-key",
        run.pk,
        snapshot.pk,
        "detector",
        "1.0.0",
        EngineConfig("detector", str(cfg.pk), True, {}),
        42,
        0,
        (EngineUnitRef("frame", FrameKey(21, 0)),),
    )
    storage = FakeStorage({"isolated/frame.jpg": raw})
    output = run_detector(inp, backend=HttpDetector(), storage=storage)
    assert output.candidates and all(c.anchor.kind == "detector_box" for c in output.candidates)
    seed_ledger(run.pk, "detector", inp.units)
    assert commit_shard_output(inp, output)
    assert not commit_shard_output(inp, output)
    with patch("orchestration.vlm_stage.crop_provider", return_value=SnapshotCropProvider(storage)):
        assert start_vlm_stage(run.pk) > 0
        unit = VlmUnit.objects.filter(run_id=run.pk).order_by("pk").first()
        client = FakeClient(label="102")
        assert execute_vlm_unit(unit.pk, client=client) == "completed"
        evidence = VlmEvidence.objects.get(unit=unit)
        assert (
            evidence.crop_origin["frame"]["media_sha256"]
            == output.candidates[0].evidence["frame"]["media_sha256"]
        )
        assert evidence.policy_version == "candidate-vlm-routing-v1"
        assert execute_vlm_unit(unit.pk, client=client) == "completed" and client.calls == 1
    assert CandidateRecord.objects.filter(run_id=run.pk).count() == len(output.candidates)
