"""#394: executable cases at their original test levels, without evaluation claims."""

import json
from dataclasses import FrozenInstanceError, asdict
from decimal import Decimal
from hashlib import sha256

import pytest

from engines.duplicate_overlap import (
    Annotation,
    generate_duplicate_overlap_candidates,
    match_duplicate_overlap_pairs,
)
from engines.interface import FrameKey
from ranking import (
    FrameInput,
    ScoreVersion,
    control_rankings,
    explain_score,
    random_audit_slice,
    rank_frames,
)
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


def _duplicate_candidates(frame: FrameKey, boxes: list[Annotation]) -> list[dict[str, object]]:
    pairs = match_duplicate_overlap_pairs(boxes)
    return [
        asdict(c)
        for c in generate_duplicate_overlap_candidates(
            frame=frame, annotations=boxes, matching_pairs=pairs
        )
    ]


def _box(annotation_id: str, x: float = 0.0, width: float = 100.0) -> Annotation:
    return Annotation(annotation_id, "car", x, 0.0, x + width, 100.0)


def test_rnk02_duplicate_cluster_counts_m_minus_one_once_and_explains_score():
    """BR-04/BR-08, bảng 6.4: cụm m box là một issue E3 với n_i = m-1, q_i = 0,5."""
    frame = FrameKey(9, 0)
    # Ba box trùng nhau: 3 cặp IoU=1 sinh 3 candidate cùng một cụm; đếm sai sẽ ra 3 × 1,0.
    triple = _duplicate_candidates(frame, [_box("a"), _box("b"), _box("c")])
    assert len(triple) == 3
    assert {tuple(o["id"] for o in c["anchor"]["objects"]) for c in triple} == {("a", "b", "c")}
    inputs = [FrameInput(9, 0, annotation_count=3), FrameInput(9, 1, annotation_count=1)]
    ranked, digest = rank_frames(inputs, triple, seed=7)
    top = {row.frame_key: row for row in ranked}["9:0"]
    (issue,) = top.contributions  # một issue, không phải ba
    assert (issue.family, issue.anchor_count, issue.n_i, issue.q_i) == ("E3", 3, 2, Decimal("0.5"))
    assert issue.contribution == Decimal("1.0")
    assert top.anchor_counts == (("E3", 1),)
    # Điểm = h(f) + Σ n_i q_i và lời giải thích có đủ từng thành phần.
    assert top.baseline_score == Decimal("0.03") and top.score == Decimal("1.03")
    explanation = explain_score(top)
    assert explanation["issue_counts"] == {"E3": 1}
    assert Decimal(str(explanation["baseline_score"])) + sum(
        Decimal(str(row["contribution"])) for row in explanation["contributions"]
    ) == Decimal(str(explanation["score"]))
    assert (ranked, digest) == rank_frames(inputs[::-1], triple[::-1], seed=7)

    # Chuỗi a-b, b-c (a-c không đủ IoU): hai candidate cặp nhưng vẫn một cụm m=3 → 2 lỗi.
    chain = _duplicate_candidates(frame, [_box("a", 0), _box("b", 6), _box("c", 12)])
    assert len(chain) == 2
    (chain_issue,) = rank_frames([FrameInput(9, 0)], chain, seed=7)[0][0].contributions
    assert (chain_issue.anchor_count, chain_issue.n_i, chain_issue.contribution) == (
        3,
        2,
        Decimal("1.0"),
    )

    # Cụm m=2 sinh đúng 1 lỗi; hai cụm tách biệt là hai issue độc lập, không gộp nhầm.
    pair = _duplicate_candidates(frame, [_box("a"), _box("b")])
    assert rank_frames([FrameInput(9, 0)], pair, seed=7)[0][0].contributions[0].n_i == 1
    two = _duplicate_candidates(
        frame, [_box("a"), _box("b"), _box("c", 500), _box("d", 500), _box("e", 500)]
    )
    row = rank_frames([FrameInput(9, 0)], two, seed=7)[0][0]
    assert sorted(item.n_i for item in row.contributions) == [1, 2]
    assert row.score == Decimal("0.5") + Decimal("1.0")

    # Nhiều candidate cùng issue E1 (nhiều engine/shard): tính một lần, q_i = confidence lớn nhất.
    first = {**_candidate("0.4"), "frame": {"cvat_task_id": 9, "frame_number": 0}}
    second = {**_candidate("0.9"), "engine": "detector-b", "frame": first["frame"]}
    other_anchor = {**_candidate("0.6"), "frame": first["frame"]}
    other_anchor["anchor"] = {
        **first["anchor"],
        "objects": [{"namespace": "prediction", "id": "p-2"}],
    }
    merged = rank_frames([FrameInput(9, 0)], [first, second], seed=7)[0][0]
    assert [(i.n_i, i.q_i) for i in merged.contributions] == [(1, Decimal("0.9"))]
    separate = rank_frames([FrameInput(9, 0)], [first, second, other_anchor], seed=7)[0][0]
    assert sorted(i.q_i for i in separate.contributions) == [Decimal("0.6"), Decimal("0.9")]
    # Khác nhóm lỗi trên cùng neo không bị gộp (E1 khác E2 là hai lỗi khác nhau).
    e2 = {**first, "family": "E2"}
    both = rank_frames([FrameInput(9, 0)], [first, e2], seed=7)[0][0]
    assert both.anchor_counts == (("E1", 1), ("E2", 1))
