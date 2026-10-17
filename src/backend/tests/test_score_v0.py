from decimal import Decimal

import pytest

from engines.interface import EngineStatus
from ranking.score_v0 import SCORE_V0, FrameInput, ScoreVersion, rank_frames


def _candidate(
    family: str,
    task_id: int,
    frame_number: int,
    *,
    confidence: float | None = None,
    anchors: int = 1,
) -> dict[str, object]:
    return {
        "engine": "detector",
        "engine_version": "fixture-v1",
        "family": family,
        "frame": {"cvat_task_id": task_id, "frame_number": frame_number},
        "anchor": {
            "kind": "annotation_cluster" if family == "E3" else "prediction_region",
            "objects": [{"namespace": "cvat_shape", "id": str(index)} for index in range(anchors)],
            "policy_version": "fixture-v1",
        },
        "evidence": {"engine": "detector", "confidence": confidence},
    }


def test_scores_every_frame_and_explains_score_v0_contributions() -> None:
    frames = [
        FrameInput(7, 1, annotation_count=3),
        FrameInput(7, 2, annotation_count=4),
        FrameInput(7, 3),
    ]
    candidates = [
        _candidate("E1", 7, 1, confidence=0.8),
        _candidate("E3", 7, 1, anchors=3),
        _candidate("E2", 7, 2, confidence=0.4),
    ]
    ranked, ranking_hash = rank_frames(frames, candidates, seed=29)
    by_frame = {item.frame_key: item for item in ranked}
    assert len(ranked) == 3
    assert by_frame["7:1"].score == Decimal("1.83")
    assert by_frame["7:1"].anchor_counts == (("E1", 1), ("E3", 1))
    assert {(item.n_i, item.q_i, item.contribution) for item in by_frame["7:1"].contributions} == {
        (1, Decimal("0.8"), Decimal("0.8")),
        (2, Decimal("0.5"), Decimal("1.0")),
    }
    assert by_frame["7:3"].score == Decimal(0) and by_frame["7:3"].contributions == ()
    assert len(ranking_hash) == 64 and all(item.score_version == SCORE_V0 for item in ranked)


def test_ranking_hash_and_order_are_reproducible_when_candidate_input_order_changes() -> None:
    frames = [FrameInput(3, 1), FrameInput(3, 2)]
    candidates = [_candidate("E1", 3, 1, confidence=0.5), _candidate("E2", 3, 2, confidence=0.5)]
    first, first_hash = rank_frames(frames, candidates, seed=91)
    second, second_hash = rank_frames(frames, list(reversed(candidates)), seed=91)
    assert first == second and first_hash == second_hash
    assert [item.tie_break_hash for item in first] == sorted(item.tie_break_hash for item in first)


def test_missing_evidence_is_marked_without_dropping_frame_from_ranking() -> None:
    frames = [
        FrameInput(1, 1, engine_statuses=(("detector", EngineStatus.FAILED.value),)),
        FrameInput(1, 2, engine_statuses=(("detector", EngineStatus.CHECKED.value),)),
        FrameInput(1, 3, engine_statuses=(("detector", EngineStatus.NOT_CHECKED.value),)),
        FrameInput(1, 4),
    ]
    ranked, _ = rank_frames(frames, [], seed=1, required_engines=("detector",))
    assert len(ranked) == 4
    assert {item.frame_key: item.missing_evidence for item in ranked} == {
        "1:1": True,
        "1:2": False,
        "1:3": True,
        "1:4": True,
    }


def test_score_version_is_frozen_and_rejects_unknown_versions() -> None:
    version = ScoreVersion()
    with pytest.raises(AttributeError):
        version.name = "score_v1"  # type: ignore[misc]
    with pytest.raises(ValueError, match="score_v0"):
        ScoreVersion(name="score_v1")
    with pytest.raises(ValueError, match="finite"):
        ScoreVersion(annotation_epsilon=Decimal("NaN"))


def test_frame_input_rejects_ambiguous_engine_evidence() -> None:
    with pytest.raises(ValueError, match="at most one"):
        FrameInput(
            1,
            1,
            engine_statuses=(
                ("detector", EngineStatus.CHECKED.value),
                ("detector", EngineStatus.FAILED.value),
            ),
        )
    with pytest.raises(ValueError, match="unknown status"):
        FrameInput(1, 1, engine_statuses=(("detector", "unknown"),))


@pytest.mark.parametrize(
    ("candidate", "message"),
    [
        (_candidate("E1", 1, 1), "confidence"),
        (_candidate("E1", 1, 1, confidence=float("nan")), "between 0 and 1"),
        (_candidate("E3", 1, 1, anchors=1), "at least two"),
        (_candidate("structural", 1, 1), "does not define"),
    ],
)
def test_invalid_candidate_fails_explicitly(candidate: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        rank_frames([FrameInput(1, 1)], [candidate], seed=1)
