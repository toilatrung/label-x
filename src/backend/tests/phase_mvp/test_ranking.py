"""#394: executable cases at their original test levels, without evaluation claims."""

import json
from dataclasses import FrozenInstanceError
from decimal import Decimal
from hashlib import sha256

import pytest

from ranking import FrameInput, ScoreVersion, control_rankings, random_audit_slice, rank_frames
from ranking.sampling import RankingSource
from runs.models import RunRanking
from runs.ranking import RankingPersistenceError, persist_run_rankings
from tests.runs.test_ranking import _candidate
from tests.runs.test_ranking import config as config
from tests.runs.test_ranking import qa_user as qa_user
from tests.runs.test_ranking import snapshot as snapshot


def test_rnk01_all_frames_tie_hash_and_canonical_result():
    frames = [FrameInput(9, index) for index in range(6)]
    candidates = [
        {**_candidate(), "frame": {"cvat_task_id": 9, "frame_number": index}} for index in [1, 3]
    ]
    ranked, digest = rank_frames(frames, candidates, seed=31)
    repeated, repeated_digest = rank_frames(frames[::-1], candidates[::-1], seed=31)
    assert (ranked, digest) == (repeated, repeated_digest)
    assert {row.frame_key for row in ranked} == {frame.key for frame in frames}
    assert [row.rank for row in ranked] == list(range(1, 7))
    assert all(
        row.tie_break_hash == sha256(f"{row.frame_key}31".encode()).hexdigest() for row in ranked
    )
    assert [row.frame_key for row in ranked] == [
        row.frame_key for row in sorted(ranked, key=lambda row: (-row.score, row.tie_break_hash))
    ]
    empty = [row for row in ranked if row.frame_key not in {"9:1", "9:3"}]
    assert len(empty) == 4 and all(row.contributions == () and row.score == 0 for row in empty)
    # Independent canonical serialization: detect a hash implementation that ignores content.
    payload = {
        "score_version": "score_v0",
        "annotation_epsilon": "0.01",
        "seed": 31,
        "frames": [
            {
                "frame_key": row.frame_key,
                "rank": row.rank,
                "score": str(row.score),
                "baseline_score": str(row.baseline_score),
                "missing_evidence": row.missing_evidence,
                "anchor_counts": row.anchor_counts,
                "contributions": [
                    {
                        "candidate_hash": c.candidate_hash,
                        "family": c.family,
                        "anchor_count": c.anchor_count,
                        "n_i": c.n_i,
                        "q_i": str(c.q_i),
                        "contribution": str(c.contribution),
                    }
                    for c in row.contributions
                ],
            }
            for row in ranked
        ],
    }
    assert (
        digest
        == sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    )


@pytest.mark.django_db
def test_rnk03_persisted_score_frozen_and_missing_required_evidence_visible(
    snapshot, config, qa_user
):
    from runs.services import create_qc_run

    config.engines = {"detector": {"enabled": True, "required": True}}
    config.save()
    for status in ["failed", "not_checked"]:
        run, _ = create_qc_run(
            snapshot_id=snapshot.pk, config_version_id=config.pk, seed=31, created_by=qa_user
        )
        run.engine_results.filter(engine="detector").update(status=status, required=True)
        rankings = persist_run_rankings(run_id=run.pk, candidates=[], audit_percent=Decimal("50"))
        risk = next(row for row in rankings if row.source == RunRanking.Source.RISK)
        before = list(
            risk.entries.order_by("rank").values("pk", "score", "missing_evidence", "explanation")
        )
        assert len(before) == 3
        assert all(
            row["missing_evidence"] and row["explanation"]["missing_evidence"] for row in before
        )
        assert risk.score_version == "score_v0"
        run.refresh_from_db()
        assert run.score_version == "score_v0"
        with pytest.raises(RankingPersistenceError, match="different normalized content"):
            persist_run_rankings(
                run_id=run.pk, candidates=[_candidate()], audit_percent=Decimal("50")
            )
        assert (
            list(
                risk.entries.order_by("rank").values(
                    "pk", "score", "missing_evidence", "explanation"
                )
            )
            == before
        )
    with pytest.raises(FrozenInstanceError):
        ScoreVersion().name = "changed"
    with pytest.raises(ValueError):
        ScoreVersion(name="unapproved-version")


def test_rnk04_audit_independent_and_controls_share_exact_universe():
    frames = [FrameInput(9, i, annotation_count=i) for i in range(17)]
    candidates = [{**_candidate(), "frame": {"cvat_task_id": 9, "frame_number": 1}}]
    audit = random_audit_slice(frames, percent=Decimal("20"), seed=31)
    controls = control_rankings(frames, candidates, seed=31)
    assert audit == random_audit_slice(frames[::-1], percent=Decimal("20"), seed=31)
    assert len(audit.entries) == 4  # ceil(17 * .20)
    expected = sorted(
        frames, key=lambda f: (sha256(f"random_audit|{f.key}|31".encode()).hexdigest(), f.key)
    )
    assert [e.frame_key for e in audit.entries] == [f.key for f in expected[:4]]
    # Changing risk inputs/order leaves the audit sample unchanged.
    risk, _ = rank_frames(frames, candidates, seed=31)
    changed_risk, _ = rank_frames(
        frames, [{**_candidate(), "frame": {"cvat_task_id": 9, "frame_number": 16}}], seed=31
    )
    assert risk != changed_risk
    assert audit == random_audit_slice(frames, percent=Decimal("20"), seed=31)
    assert {c.source for c in controls} == {
        RankingSource.RANDOM_CONTROL,
        RankingSource.ANNOTATION_COUNT_CONTROL,
        RankingSource.MAX_CONFIDENCE_CONTROL,
    }
    assert all({e.frame_key for e in c.entries} == {f.key for f in frames} for c in controls)
    assert len({c.content_hash for c in controls} | {audit.content_hash}) == 4
    assert controls == control_rankings(frames[::-1], candidates[::-1], seed=31)
