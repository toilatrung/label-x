"""AC gaps found by QA of M-03-RESOLVE: archive:238 AC2 (paging + filters), archive:239 AC2/AC3,
archive:243 AC4.

Synthetic DB rows through the real API/services; not CVAT E2E evidence.
"""

# Historical issue mapping: docs/08-devops/github-issue-migration-2026-10-17.html
# Anchors: issue-238, issue-239, issue-243.

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from django.core.files.storage import storages

from orchestration.models import CandidateRecord, LedgerUnit, ShardCommit
from review.finalization_service import (
    complete_scope_frames,
    operational_run,
    route_new_candidates,
)
from review.models import FrameReview, Issue
from runs.models import EngineResult, QCRun, RunRanking, RunRankingEntry
from runs.views import RunCursorPagination
from snapshots.models import SnapshotFrame
from snapshots.normalization import FrameExport, JobExport
from snapshots.services import create_locked_snapshot
from tests.review.test_final_source_guard import _complete_final
from tests.review.test_queue_lease import client, next_url

pytest_plugins = ["tests.review.test_queue_lease", "tests.review.test_final_source_guard"]
pytestmark = pytest.mark.usefixtures("snapshot_media_urls")


# --------------------------------------------------------------------------- archive:238 AC2


@pytest.fixture
def many_frames(world, monkeypatch):
    """A 7-frame run ranked 1..7; even frame_index are reviewed, odd are not (page size 3)."""

    monkeypatch.setattr(RunCursorPagination, "page_size", 3)
    snapshot = create_locked_snapshot(
        dataset_id=42,
        created_by=world["admin"],
        taxonomy_version="tax",
        guideline_version="guide",
        jobs=[
            JobExport(
                cvat_job_id=100,
                cvat_task_id=200,
                assignee_cvat_user_id=702,
                assignee_user_id=world["author"].pk,
                source_updated_at="2026-10-11T00:00:00Z",
                annotations={"shapes": [], "tracks": []},
                frames=[
                    FrameExport(
                        frame_index=index,
                        file_name=f"{index}.jpg",
                        width=100,
                        height=100,
                        media_bytes=f"frame-{index}".encode(),
                        media_storage_key=f"{index}.jpg",
                    )
                    for index in range(7)
                ],
            )
        ],
    )
    run = QCRun.objects.create(
        snapshot=snapshot,
        config_version=world["run"].config_version,
        seed=1,
        status=QCRun.Status.COMPLETED,
        dataset_id=42,
        scope_hash="9" * 64,
        created_by=world["admin"],
    )
    risk = RunRanking.objects.create(
        run=run,
        source=RunRanking.Source.RISK,
        seed=1,
        score_version="v0",
        content_hash="e" * 64,
        ranking_hash="f" * 64,
    )
    frames = list(SnapshotFrame.objects.filter(snapshot_job__snapshot=snapshot))
    frames.sort(key=lambda frame: frame.frame_index)
    for frame in frames:
        RunRankingEntry.objects.create(
            ranking=risk,
            snapshot_frame=frame,
            rank=frame.frame_index + 1,
            score=1,
            baseline_score=1,
            tie_break_hash="a" * 64,
            issue_counts={"E2": 1} if frame.frame_index % 3 == 0 else {},
        )
        if frame.frame_index % 2 == 0:
            FrameReview.objects.create(
                run=run, snapshot_frame=frame, state=FrameReview.State.REVIEWED
            )
    return {"run": run, "frames": frames}


def _walk(api, run_id, **params):
    """Follow `next` links; returns (frame_numbers per page, every next URL seen)."""

    pages, links = [], []
    response = api.get(f"/api/runs/{run_id}/ranking/", {"queue": "risk", **params})
    while True:
        assert response.status_code == 200, response.data
        pages.append([row["frame_key"]["frame_number"] for row in response.data["results"]])
        link = response.data["next"]
        if not link:
            return pages, links
        links.append(link)
        response = api.get(link)


@pytest.mark.django_db
def test_ranking_second_page_keeps_filter_and_never_duplicates_frames(world, many_frames):
    api, run_id = client(world["reviewer"]), many_frames["run"].pk

    pages, links = _walk(api, run_id)
    flat = [n for page in pages for n in page]
    assert [len(p) for p in pages] == [3, 3, 1]
    assert flat == list(range(7)) and len(set(flat)) == len(flat)  # complete, in rank order

    pages, links = _walk(api, run_id, review_state="reviewed")  # frames 0, 2, 4, 6
    flat = [n for page in pages for n in page]
    assert pages == [[0, 2, 4], [6]] and flat == [0, 2, 4, 6]
    for link in links:  # page 2 is requested with the same filter, not a bare cursor
        assert parse_qs(urlparse(link).query)["review_state"] == ["reviewed"]

    pages, links = _walk(api, run_id, review_state="unreviewed")  # frames 1, 3, 5
    assert pages == [[1, 3, 5]] and links == []

    pages, links = _walk(api, run_id, family="E2")  # frames 0, 3, 6 carry an E2 count
    assert [n for page in pages for n in page] == [0, 3, 6]

    pages, _ = _walk(api, run_id, review_state="reviewed", family="E2")  # intersection: 0, 6
    assert [n for page in pages for n in page] == [0, 6]


@pytest.mark.django_db
def test_ranking_paging_filter_follows_state_changes_between_pages(world, many_frames):
    api, run_id = client(world["reviewer"]), many_frames["run"].pk
    first = api.get(f"/api/runs/{run_id}/ranking/", {"queue": "risk", "review_state": "reviewed"})
    assert [r["frame_key"]["frame_number"] for r in first.data["results"]] == [0, 2, 4]
    # A frame on page 1 changes state while the reviewer is on page 2: it must not reappear.
    FrameReview.objects.filter(snapshot_frame=many_frames["frames"][0]).update(
        state=FrameReview.State.COMPLETED
    )
    second = api.get(first.data["next"])
    assert [r["frame_key"]["frame_number"] for r in second.data["results"]] == [6]


# --------------------------------------------------------------------------- archive:239 AC2/AC3


def _prediction_candidate(run, shard, *, key, family, engine="detector", bbox=(20, 20, 40, 40)):
    return CandidateRecord.objects.create(
        run=run,
        dedup_key=key * 64,
        shard=shard,
        engine=engine,
        engine_version="v7",
        family=family,
        cvat_task_id=200,
        frame_number=0,
        anchor={
            "kind": "prediction_region",
            "objects": [{"namespace": engine, "id": f"{key}:0"}],
            "rule_id": None,
            "bbox": dict(zip(("x1", "y1", "x2", "y2"), bbox, strict=True)),
            "policy_version": "anchor-v1",
        },
        policy_version="anchor-v1",
        evidence={"engine": engine, "prediction_class": "car", "confidence": 0.87},
        evidence_sha256=key * 64,
    )


@pytest.mark.django_db
def test_workspace_payload_has_real_predictions_guideline_and_engine_states(world, monkeypatch):
    monkeypatch.setattr(storages["snapshots"], "url", lambda name: f"https://storage.test/{name}")
    run = world["run"]
    shard = ShardCommit.objects.create(
        idempotency_key="ac-gap-shard",
        run=run,
        snapshot_id=run.snapshot_id,
        engine="detector",
        engine_version="v7",
        shard_index=0,
        output_sha256="a" * 64,
    )
    one = _prediction_candidate(run, shard, key="1", family="E2")
    two = _prediction_candidate(run, shard, key="2", family="structural", bbox=(50, 50, 80, 90))
    # Ledger per engine on this frame: failed / not_checked(no_reference) / completed.
    for engine, outcome, reason in (
        ("detector", "failed", ""),
        ("schema", "not_checked", "no_reference"),
        ("geometry", "completed", ""),
    ):
        LedgerUnit.objects.create(
            run=run,
            engine=engine,
            kind="frame",
            cvat_task_id=200,
            frame_number=0,
            outcome=outcome,
            not_checked_reason=reason,
        )
    EngineResult.objects.create(run=run, engine="detector", status="failed")
    EngineResult.objects.create(run=run, engine="schema", status="reference_unavailable")
    EngineResult.objects.create(run=run, engine="geometry", status="succeeded")

    api = client(world["reviewer"])
    claim = api.post(next_url(), {"run_id": run.pk}, format="json")
    assert claim.status_code == 200, claim.data
    body = api.get(f"/api/frames/{claim.data['frame']['id']}/issues/").data

    # AC2: shape 91 has no candidate of its own and is delivered next to real predictions.
    assert [a["id"] for a in body["annotations"]] == ["shape:91"]
    assert body["annotations"][0]["bbox"] == {"x1": 1, "y1": 1, "x2": 10, "y2": 10}
    predictions = {p["candidate_id"]: p for p in body["predictions"]}
    assert set(predictions) == {one.pk, two.pk}
    assert predictions[one.pk]["family"] == "E2"
    assert (
        predictions[one.pk]["engine"] == "detector"
        and predictions[one.pk]["engine_version"] == "v7"
    )
    assert predictions[two.pk]["anchor"]["bbox"] == {"x1": 50, "y1": 50, "x2": 80, "y2": 90}
    assert predictions[one.pk]["evidence"]["confidence"] == 0.87
    # AC3: guideline version of the locked snapshot, revision server-derived.
    assert body["guideline_version"] == run.snapshot.guideline_version == "guide"
    assert body["snapshot_revision"] == run.snapshot.revision_sha256
    # AC3: Failed and Not checked keep their meaning and are not shown as checked.
    engines = {e["engine"]: e for e in body["engines"]}
    assert engines["detector"]["status"] == "failed" and engines["detector"]["failed_units"] == 1
    assert engines["schema"]["status"] == "not_checked" and engines["schema"]["failed_units"] == 0
    assert engines["geometry"]["status"] == "checked"
    # Reading never creates or resolves issues beyond those the claim materialized.
    assert {i["state"] for i in body["issues"]} <= {"in_review", "pending_review"}
    assert not Issue.objects.filter(state__in=["confirmed", "resolved", "rejected"]).exists()


# --------------------------------------------------------------------------- archive:243 AC4


def _final_candidate(run, family, key):
    shard, _ = ShardCommit.objects.get_or_create(
        run=run,
        engine="geometry",
        shard_index=0,
        defaults={
            "idempotency_key": f"shard-{run.pk}",
            "snapshot_id": run.snapshot_id,
            "engine_version": "1",
            "output_sha256": "0" * 64,
        },
    )
    return CandidateRecord.objects.create(
        run=run,
        dedup_key=key,
        shard=shard,
        engine="geometry",
        engine_version="1",
        family=family,
        cvat_task_id=200,
        frame_number=0,
        anchor={"kind": "manual_region", "objects": []},
        policy_version="p1",
        evidence={},
        evidence_sha256="1" * 64,
    )


@pytest.mark.django_db
@pytest.mark.parametrize("family", ["E2", "E3", "structural"])
def test_new_non_e1_final_candidate_blocks_scope_until_decided(final_world, family):
    origin, final = final_world["run"], final_world["final"]
    frame = final_world["issue"].frame_review
    frame.state = FrameReview.State.AWAITING_FOLLOWUP
    frame.save(update_fields=["state"])
    _complete_final(final)
    new = _final_candidate(final, family, f"new-{family}")

    assert complete_scope_frames(origin.pk) == 0
    routed = Issue.objects.get(candidate=new)
    assert routed.family == family and routed.state == Issue.State.PENDING_REVIEW
    assert operational_run(origin).pk == origin.pk  # not selectable while undecided
    frame.refresh_from_db()
    assert frame.state == FrameReview.State.AWAITING_FOLLOWUP

    routed.state = Issue.State.REJECTED
    routed.save(update_fields=["state"])
    assert operational_run(origin).pk == final.pk
    assert complete_scope_frames(origin.pk) == 1


@pytest.mark.django_db
def test_every_new_family_must_be_decided_before_scope_completes(final_world):
    origin, final = final_world["run"], final_world["final"]
    frame = final_world["issue"].frame_review
    frame.state = FrameReview.State.AWAITING_FOLLOWUP
    frame.save(update_fields=["state"])
    _complete_final(final)
    candidates = [
        _final_candidate(final, family, f"mix-{family}")
        for family in ("E1", "E2", "E3", "structural")
    ]
    assert complete_scope_frames(origin.pk) == 0
    issues = {i.candidate_id: i for i in Issue.objects.filter(candidate__in=candidates)}
    assert {i.family for i in issues.values()} == {"E1", "E2", "E3", "structural"}
    assert route_new_candidates(origin, final) == 0  # idempotent: nothing routed twice

    states = [Issue.State.REJECTED, Issue.State.RESOLVED, Issue.State.REJECTED]
    for candidate, state in zip(candidates[:3], states, strict=True):
        issue = issues[candidate.pk]
        issue.state = state
        issue.save(update_fields=["state"])
        assert operational_run(origin).pk == origin.pk  # one family still undecided
        assert complete_scope_frames(origin.pk) == 0
    last = issues[candidates[3].pk]
    last.state = Issue.State.REJECTED
    last.save(update_fields=["state"])
    assert operational_run(origin).pk == final.pk
    assert complete_scope_frames(origin.pk) == 1
