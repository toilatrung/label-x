"""Review frame navigation preserves decisions and moves only the caller's single lease."""

from datetime import timedelta

import pytest
from django.utils import timezone

from review.models import FrameReview, Lease, ReviewDecision
from runs.models import QCRun, RunRanking, RunRankingEntry
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot
from tests.review.test_queue_lease import (  # noqa: F401
    client,
    next_url,
    persist_manual_decision,
    world,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def navigation(world):  # noqa: F811
    snapshot = create_locked_snapshot(
        dataset_id=42,
        created_by=world["admin"],
        taxonomy_version="t",
        guideline_version="g",
        jobs=[
            JobExport(
                cvat_job_id=101,
                cvat_task_id=201,
                assignee_cvat_user_id=702,
                assignee_user_id=world["author"].pk,
                source_updated_at="2026-10-11T00:00:00Z",
                annotations={"shapes": [], "tracks": []},
                frames=[
                    FrameExport(
                        frame_index=i,
                        file_name=f"{i}.jpg",
                        width=100,
                        height=100,
                        media_bytes=f"frame-{i}".encode(),
                        media_storage_key=f"nav-{i}.jpg",
                    )
                    for i in range(2)
                ],
            )
        ],
    )
    run = QCRun.objects.create(
        snapshot=snapshot,
        config_version=world["run"].config_version,
        seed=2,
        status="completed",
        dataset_id=42,
        scope_hash="b" * 64,
        created_by=world["admin"],
    )
    ranking = RunRanking.objects.create(
        run=run,
        source=RunRanking.Source.RISK,
        seed=1,
        score_version="v0",
        content_hash="d" * 64,
        ranking_hash="c" * 64,
    )
    frames = list(snapshot.jobs.get().frames.all())
    for index, frame in enumerate(frames):
        RunRankingEntry.objects.create(
            ranking=ranking,
            snapshot_frame=frame,
            rank=index + 1,
            score=1,
            baseline_score=1,
            tie_break_hash="a" * 64,
        )
    return {**world, "run": run, "frame": frames[0], "target": frames[1]}


def claim(api, nav, **extra):
    return api.post(next_url(), {"run_id": nav["run"].pk, **extra}, format="json")


def test_switch_releases_previous_frame_and_can_navigate_back(navigation):
    nav = navigation
    api = client(nav["reviewer"])
    first = claim(api, nav, frame_id=nav["frame"].pk).data
    moved = claim(api, nav, frame_id=nav["target"].pk, previous_lease_id=first["lease"]["id"])
    assert moved.status_code == 200, moved.data
    old = Lease.objects.get(pk=first["lease"]["id"])
    assert old.closed_at is not None
    old.frame_review.refresh_from_db()
    assert old.frame_review.state == FrameReview.State.UNREVIEWED
    assert Lease.objects.filter(holder=nav["reviewer"], closed_at__isnull=True).count() == 1
    back = claim(api, nav, frame_id=nav["frame"].pk, previous_lease_id=moved.data["lease"]["id"])
    assert back.status_code == 200
    assert back.data["frame"]["id"] == first["frame"]["id"]


def test_switch_preserves_saved_decisions_as_incomplete(navigation):
    api = client(navigation["reviewer"])
    first = claim(api, navigation, frame_id=navigation["frame"].pk).data
    persist_manual_decision(navigation, first["lease"]["id"])
    decisions = ReviewDecision.objects.count()
    moved = claim(
        api, navigation, frame_id=navigation["target"].pk, previous_lease_id=first["lease"]["id"]
    )
    assert moved.status_code == 200, moved.data
    previous = FrameReview.objects.get(pk=first["frame"]["id"])
    assert previous.state == FrameReview.State.INCOMPLETE
    assert previous.previous_reviewer_id == navigation["reviewer"].pk
    assert ReviewDecision.objects.count() == decisions


def test_unavailable_target_rolls_back_handoff_and_keeps_current_lease(navigation):
    api = client(navigation["reviewer"])
    first = claim(api, navigation, frame_id=navigation["frame"].pk).data
    other = claim(client(navigation["other"]), navigation, frame_id=navigation["target"].pk)
    assert other.status_code == 200
    moved = claim(
        api, navigation, frame_id=navigation["target"].pk, previous_lease_id=first["lease"]["id"]
    )
    assert moved.status_code == 409
    old = Lease.objects.get(pk=first["lease"]["id"])
    assert old.closed_at is None
    assert old.frame_review.state == FrameReview.State.IN_REVIEW


def test_cannot_release_another_reviewers_lease(navigation):
    first = claim(client(navigation["reviewer"]), navigation, frame_id=navigation["frame"].pk).data
    moved = claim(
        client(navigation["other"]),
        navigation,
        frame_id=navigation["target"].pk,
        previous_lease_id=first["lease"]["id"],
    )
    assert moved.status_code == 409
    assert Lease.objects.get(pk=first["lease"]["id"]).closed_at is None


def test_expired_previous_lease_requires_reload(navigation):
    api = client(navigation["reviewer"])
    first = claim(api, navigation, frame_id=navigation["frame"].pk).data
    Lease.objects.filter(pk=first["lease"]["id"]).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert (
        claim(
            api,
            navigation,
            frame_id=navigation["target"].pk,
            previous_lease_id=first["lease"]["id"],
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"previous_lease_id": True, "frame_id": 1},
        {"previous_lease_id": 1},
        {"previous_lease_id": -1, "frame_id": 1},
    ],
)
def test_invalid_handoff_is_rejected(navigation, extra):
    assert claim(client(navigation["reviewer"]), navigation, **extra).status_code == 400


def test_replaying_handoff_resumes_target_without_creating_another_lease(navigation):
    api = client(navigation["reviewer"])
    first = claim(api, navigation, frame_id=navigation["frame"].pk).data
    payload = {"frame_id": navigation["target"].pk, "previous_lease_id": first["lease"]["id"]}
    moved = claim(api, navigation, **payload)
    replayed = claim(api, navigation, **payload)
    assert replayed.status_code == 200
    assert replayed.data["lease"]["id"] == moved.data["lease"]["id"]
    assert Lease.objects.filter(holder=navigation["reviewer"], closed_at__isnull=True).count() == 1


def test_handoff_between_runs_preserves_old_decisions(navigation):
    nav = navigation
    api = client(nav["reviewer"])
    old_run = {**nav, "run": nav["run"], "frame": nav["frame"]}
    # The fixture retains the original run on another Snapshot: use an independent target run.
    first = claim(api, old_run, frame_id=nav["frame"].pk).data
    persist_manual_decision(nav, first["lease"]["id"])
    target_run = QCRun.objects.create(
        snapshot=nav["run"].snapshot,
        config_version=nav["run"].config_version,
        dataset_id=42,
        seed=3,
        scope_hash="7" * 64,
        status="completed",
        created_by=nav["admin"],
    )
    ranking = RunRanking.objects.create(
        run=target_run,
        source="risk",
        seed=1,
        score_version="v0",
        content_hash="8" * 64,
        ranking_hash="9" * 64,
    )
    # Same SnapshotFrame in a DIFFERENT run must still release the previous run's lease.
    RunRankingEntry.objects.create(
        ranking=ranking,
        snapshot_frame=nav["frame"],
        rank=1,
        score=1,
        baseline_score=1,
        tie_break_hash="a" * 64,
    )
    response = api.post(
        next_url(),
        {
            "run_id": target_run.pk,
            "frame_id": nav["frame"].pk,
            "previous_lease_id": first["lease"]["id"],
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    assert response.data["frame"]["run_id"] == target_run.pk
    assert response.data["frame"]["id"] != first["frame"]["id"]
    previous = Lease.objects.get(pk=first["lease"]["id"])
    assert previous.closed_at is not None
    assert previous.frame_review.state == "incomplete"
    assert ReviewDecision.objects.filter(issue__frame_review=previous.frame_review).exists()
    assert Lease.objects.filter(holder=nav["reviewer"], closed_at__isnull=True).count() == 1


def test_cross_run_denied_target_does_not_close_old_lease(navigation):
    nav = navigation
    api = client(nav["reviewer"])
    first = claim(api, nav, frame_id=nav["frame"].pk).data
    target = QCRun.objects.create(
        snapshot=nav["run"].snapshot,
        config_version=nav["run"].config_version,
        dataset_id=99999,
        seed=4,
        scope_hash="6" * 64,
        status="completed",
        created_by=nav["admin"],
    )
    response = api.post(
        next_url(),
        {
            "run_id": target.pk,
            "frame_id": nav["target"].pk,
            "previous_lease_id": first["lease"]["id"],
        },
        format="json",
    )
    assert response.status_code == 403
    assert Lease.objects.get(pk=first["lease"]["id"]).closed_at is None


def test_cross_run_unavailable_target_rolls_back_old_lease(navigation):
    nav = navigation
    api = client(nav["reviewer"])
    first = claim(api, nav, frame_id=nav["frame"].pk).data
    # Original fixture run is another valid run in the same dataset; frame not in its queue.
    original = QCRun.objects.exclude(pk=nav["run"].pk).get()
    response = api.post(
        next_url(),
        {
            "run_id": original.pk,
            "frame_id": nav["target"].pk,
            "previous_lease_id": first["lease"]["id"],
        },
        format="json",
    )
    assert response.status_code == 409
    assert Lease.objects.get(pk=first["lease"]["id"]).closed_at is None
