"""Duplicate candidate -> materialized issue -> workspace, without any detector output."""

from dataclasses import asdict

import pytest

from engines.duplicate_overlap import (
    Annotation,
    MatchingPair,
    generate_duplicate_overlap_candidates,
)
from engines.interface import FrameKey
from orchestration.models import CandidateRecord, ShardCommit
from review.decision_source import materialize_candidate_issues
from review.models import FrameReview
from runs.models import EngineResult, QCRun
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot
from tests.review.test_queue_lease import client

pytest_plugins = ["tests.review.test_queue_lease"]
pytestmark = pytest.mark.usefixtures("snapshot_media_urls")


@pytest.mark.django_db
def test_e3_workspace_preserves_both_snapshot_boxes_with_detector_disabled(world):
    snapshot = create_locked_snapshot(
        dataset_id=42,
        created_by=world["admin"],
        taxonomy_version="tax",
        guideline_version="guide",
        jobs=[
            JobExport(
                cvat_job_id=4,
                cvat_task_id=13,
                assignee_cvat_user_id=702,
                assignee_user_id=world["author"].pk,
                source_updated_at="2026-10-18T00:00:00Z",
                annotations={
                    "shapes": [
                        {
                            "id": identifier,
                            "type": "rectangle",
                            "frame": 4,
                            "label_id": 45,
                            "points": points,
                        }
                        for identifier, points in [
                            (9090, [10, 20, 100, 120]),
                            (9142, [12, 22, 102, 122]),
                        ]
                    ],
                    "tracks": [],
                },
                frames=[
                    FrameExport(
                        frame_index=4,
                        file_name="4.jpg",
                        width=1280,
                        height=720,
                        media_bytes=b"snapshot-frame-4",
                        media_storage_key="4.jpg",
                    )
                ],
            )
        ],
    )
    run = QCRun.objects.create(
        snapshot=snapshot,
        config_version=world["run"].config_version,
        seed=42,
        status=QCRun.Status.COMPLETED,
        dataset_id=42,
        scope_hash="a" * 64,
        created_by=world["admin"],
    )
    shard = ShardCommit.objects.create(
        idempotency_key="issue-focus-duplicate",
        run=run,
        snapshot_id=snapshot.pk,
        engine="duplicate",
        engine_version="1.0.0",
        shard_index=0,
        output_sha256="b" * 64,
    )
    (generated,) = generate_duplicate_overlap_candidates(
        frame=FrameKey(cvat_task_id=13, frame_number=4),
        annotations=[
            Annotation("shape:9090", "45", 10, 20, 100, 120),
            Annotation("shape:9142", "45", 12, 22, 102, 122),
        ],
        matching_pairs=[MatchingPair("shape:9090", "shape:9142", 0.883964)],
    )
    candidate = CandidateRecord.objects.create(
        run=run,
        shard=shard,
        dedup_key="c" * 64,
        engine="duplicate",
        engine_version="1.0.0",
        family="E3",
        cvat_task_id=13,
        frame_number=4,
        anchor=asdict(generated.anchor),
        policy_version="1.0.0",
        evidence=asdict(generated.evidence),
        evidence_sha256="d" * 64,
    )
    EngineResult.objects.create(run=run, engine="detector", status="disabled", reason="disabled")
    frame = FrameReview.objects.create(run=run, snapshot_frame=snapshot.jobs.get().frames.get())
    materialize_candidate_issues(frame)
    response = client(world["reviewer"]).get(f"/api/frames/{frame.pk}/workspace/")
    assert response.status_code == 200, response.data
    body = response.data
    issue = body["issues"][0]
    assert issue["anchor"]["objects"] == [
        {"namespace": "cvat_shape", "id": "9090"},
        {"namespace": "cvat_shape", "id": "9142"},
    ]
    assert body["predictions"][0]["anchor"] == issue["anchor"]
    assert [annotation["source"]["id"] for annotation in body["annotations"]] == [9090, 9142]
    assert body["annotations"][0]["bbox"] == {"x1": 10, "y1": 20, "x2": 100, "y2": 120}
    assert body["annotations"][1]["bbox"] == {"x1": 12, "y1": 22, "x2": 102, "y2": 122}
    assert issue["evidence"][0]["annotation_ids"] == ["shape:9090", "shape:9142"]
    assert body["engines"][0]["engine"] == "detector"
    assert body["engines"][0]["status"] == "not_checked"
    candidate.refresh_from_db()
    assert candidate.anchor["objects"][0]["id"] == "shape:9090"
    assert frame.issues.get().anchor["objects"][0]["id"] == "shape:9090"
