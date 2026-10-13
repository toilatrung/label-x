"""Opt-in GPU HTTP -> isolated locked snapshot -> persisted candidates (not accuracy)."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.files.base import ContentFile

from engines.detector import BDD100K_DETECTOR_CLASSES, run_detector_engine
from engines.interface import EngineConfig, EngineInput, EngineUnitRef, FrameKey
from orchestration.models import CandidateRecord
from orchestration.routing_policy import RoutingPolicy, route, routing_input_from_candidate
from orchestration.services import commit_shard_output, seed_ledger
from runs.models import ConfigVersion, ModelArtifact
from runs.services import create_qc_run
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        not os.environ.get("LABELX_DETECTOR_RUNTIME_SAMPLE"),
        reason="requires explicitly permitted real sample and GPU HTTP worker",
    ),
]


def test_real_gpu_http_snapshot_and_no_match_routing(settings):
    raw = Path(os.environ["LABELX_DETECTOR_RUNTIME_SAMPLE"]).read_bytes()
    settings.DETECTOR_WORKER_URL = os.environ["DETECTOR_WORKER_URL"]
    settings.DETECTOR_SERVICE_TOKEN = os.environ["DETECTOR_SERVICE_TOKEN"]
    settings.DETECTOR_CHECKPOINT_PATH = os.environ["LABELX_DETECTOR_RUNTIME_CHECKPOINT"]
    settings.DETECTOR_MANIFEST_PATH = os.environ["LABELX_DETECTOR_RUNTIME_MANIFEST"]
    manifest = json.loads(Path(settings.DETECTOR_MANIFEST_PATH).read_text())
    model = manifest["model"]
    user = User.objects.create(username="gpu-http-isolated")
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
        source_updated_at="isolated-runtime-test",
        annotations={"shapes": [], "tracks": []},
        frames=(frame,),
        assignee_cvat_user_id=None,
    )
    snapshot = create_locked_snapshot(
        dataset_id=3,
        created_by=user,
        jobs=[job],
        taxonomy_version="runtime-test",
        guideline_version="test",
    )
    cfg = ConfigVersion.objects.create(
        name="GPU HTTP fixture",
        status="published",
        created_by=user,
        engines={
            "detector": {"enabled": True},
            "schema": {
                "enabled": False,
                "params": {
                    "taxonomy": {
                        "version": snapshot.taxonomy_version,
                        "labels": [
                            {"label_id": i + 100, "name": name}
                            for i, name in enumerate(BDD100K_DETECTOR_CLASSES)
                        ],
                    }
                },
            },
        },
        models={"name": "frozen", "version": model["version"]},
    )
    ModelArtifact.objects.create(
        name="frozen",
        version=model["version"],
        checksum=model["sha256"],
        class_mapping_version=manifest["class_mapping"]["version"],
        class_mapping={"classes": list(BDD100K_DETECTOR_CLASSES)},
    )
    run, _ = create_qc_run(
        snapshot_id=snapshot.pk, config_version_id=cfg.pk, seed=42, created_by=user
    )
    inp = EngineInput(
        "real-gpu-http",
        run.pk,
        snapshot.pk,
        "detector",
        "1.0.0",
        EngineConfig("detector", str(cfg.pk), True, {}),
        42,
        0,
        (EngineUnitRef("frame", FrameKey(21, 0)),),
    )
    # Only storage is isolated; HTTP request and GPU model inference are real.
    with patch("engines.detector.storages") as stores:
        stores.__getitem__.return_value.open.side_effect = lambda *args: ContentFile(raw)
        output = run_detector_engine(inp)
    assert output.candidates
    for candidate in output.candidates:
        assert candidate.evidence["artifact_verified"] is True
        assert len(candidate.evidence["class_scores"]) == 11
        assert candidate.evidence["match_status"] == "unmatched_detection"
        decision = route(
            RoutingPolicy(),
            routing_input_from_candidate({"engine": "detector", "evidence": candidate.evidence}),
        )
        assert not decision.call_qwen and decision.human_review_required
    seed_ledger(run.pk, "detector", inp.units)
    assert commit_shard_output(inp, output) and not commit_shard_output(inp, output)
    assert CandidateRecord.objects.filter(run_id=run.pk).count() == len(output.candidates)
