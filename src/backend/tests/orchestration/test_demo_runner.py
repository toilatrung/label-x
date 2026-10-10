"""M-DEMO01 / D-02 synchronous runner acceptance tests."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone

from orchestration.demo_runner import run_snapshot_synchronously
from orchestration.models import CandidateRecord
from runs.models import ConfigVersion, QCRun, WorkUnit
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = json.loads(
    (ROOT / "src/backend/fixtures/normalized-snapshot-v1.json").read_text(encoding="utf-8")
)

pytestmark = pytest.mark.django_db(transaction=True)


def _snapshot(user: User):
    job = FIXTURE["jobs"][0]
    frames = tuple(
        FrameExport(
            frame_index=frame["frame_index"],
            source_frame_id=frame["source_frame_id"],
            file_name=frame["file_name"],
            width=frame["width"],
            height=frame["height"],
            media_bytes=f"fixture-{frame['frame_index']}".encode(),
            media_storage_key=frame["media"]["storage_key"],
        )
        for frame in job["frames"]
    )
    shapes = [
        {
            "id": shape["source"]["id"],
            "type": "rectangle",
            "frame": shape["frame_index"],
            "label_id": shape["label_id"],
            "points": shape["points"],
            "attributes": shape["attributes"],
            "outside": shape["outside"],
            "occluded": shape["occluded"],
        }
        for frame in job["frames"]
        for shape in frame["shapes"]
    ]
    return create_locked_snapshot(
        dataset_id=FIXTURE["dataset_id"],
        created_by=user,
        jobs=(
            JobExport(
                cvat_job_id=job["cvat_job_id"],
                cvat_task_id=job["cvat_task_id"],
                source_updated_at=job["source_updated_at"],
                annotations={"shapes": shapes, "tracks": []},
                frames=frames,
                assignee_cvat_user_id=job["assignee_cvat_user_id"],
            ),
        ),
        taxonomy_version=FIXTURE["taxonomy_version"],
        guideline_version=FIXTURE["guideline_version"],
    )


def _config(user: User, engines: dict[str, object]) -> ConfigVersion:
    return ConfigVersion.objects.create(
        name="M-DEMO01 D-02",
        status=ConfigVersion.Status.PUBLISHED,
        payload={"shard_size": 100, "engines": engines},
        engines=engines,
        created_by=user,
        published_by=user,
        published_at=timezone.now(),
    )


def _all_engines() -> dict[str, object]:
    return {
        "duplicate": {"enabled": True},
        "geometry": {"enabled": True},
        "schema": {
            "enabled": True,
            "params": {
                "taxonomy": {
                    "version": FIXTURE["taxonomy_version"],
                    "labels": [
                        {
                            "label_id": 4,
                            "name": "car",
                            "required_attributes": [
                                {
                                    "spec_id": 8,
                                    "name": "motion_state",
                                    "rule_id": "A-007",
                                    "allowed_values": ["moving", "parked", "stopped"],
                                }
                            ],
                        }
                    ],
                }
            },
        },
    }


def test_command_runs_fixture_scores_every_frame_and_is_idempotent() -> None:
    user = User.objects.create_user("demo-runner")
    snapshot = _snapshot(user)
    config = _config(user, _all_engines())

    first_output = StringIO()
    call_command(
        "run_demo_snapshot",
        snapshot.pk,
        config_version_id=config.pk,
        created_by=user.username,
        seed=113,
        stdout=first_output,
    )
    run = QCRun.objects.get()
    first_counts = (
        QCRun.objects.count(),
        WorkUnit.objects.count(),
        CandidateRecord.objects.count(),
    )
    candidate = CandidateRecord.objects.get()
    assert candidate.family == "structural"
    assert candidate.anchor["rule_id"] == "A-007"
    assert candidate.evidence["actual"] == "<missing>"
    assert run.status == QCRun.Status.COMPLETED
    assert run.score_version == "score_v0"
    assert set(run.engine_results.values_list("status", flat=True)) == {"checked"}
    assert first_output.getvalue().count("rank=") == 2

    second_output = StringIO()
    call_command(
        "run_demo_snapshot",
        snapshot.pk,
        config_version_id=config.pk,
        created_by=user.username,
        seed=113,
        stdout=second_output,
    )
    assert (QCRun.objects.count(), WorkUnit.objects.count(), CandidateRecord.objects.count()) == (
        first_counts
    )
    assert "action=reused" in second_output.getvalue()
    assert "executed_work_units=0" in second_output.getvalue()
    assert (
        first_output.getvalue().split("ranking_hash=")[1].strip()
        == second_output.getvalue().split("ranking_hash=")[1].strip()
    )


@pytest.mark.parametrize(
    ("engines", "expected_status", "expected_reason"),
    [
        ({"missing": {"enabled": True}}, "failed", None),
        ({"schema": {"enabled": True}}, "not_checked", "no_reference"),
    ],
)
def test_failed_or_missing_reference_engine_is_visible_in_engine_result(
    engines: dict[str, object], expected_status: str, expected_reason: str | None
) -> None:
    user = User.objects.create_user(f"demo-{expected_status}")
    snapshot = _snapshot(user)
    config = _config(user, engines)

    summary = run_snapshot_synchronously(
        snapshot_id=snapshot.pk,
        config_version_id=config.pk,
        seed=7,
        created_by=user,
        idempotency_key=f"demo-{expected_status}",
    )

    result = QCRun.objects.get(pk=summary.run_id).engine_results.get()
    assert result.status == expected_status
    assert result.reason == expected_reason
    assert len(summary.ranked_frames) == 2
    assert all(frame.missing_evidence for frame in summary.ranked_frames)
