import json
from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest

from engines.duplicate_overlap import (
    DUPLICATE_OVERLAP_ENGINE_NAME,
    DUPLICATE_OVERLAP_ENGINE_VERSION,
    Annotation,
    run_duplicate_overlap_engine,
)
from engines.interface import EngineConfig, EngineInput, EngineUnitRef, FrameKey
from ranking.sampling import RankingSource, control_rankings, explain_score, random_audit_slice
from ranking.score_v0 import FrameInput, rank_frames

BDD100K_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "normalized-snapshot-v1.json"


def _candidate(task_id: int, frame_number: int, confidence: str) -> dict[str, object]:
    return {
        "family": "E1",
        "frame": {"cvat_task_id": task_id, "frame_number": frame_number},
        "anchor": {"objects": [{"id": "a"}]},
        "evidence": {"confidence": confidence},
    }


def test_random_audit_slice_is_repeatable_and_independent_from_risk_order() -> None:
    frames = [FrameInput(9, index, annotation_count=index) for index in range(10)]
    first = random_audit_slice(frames, percent=Decimal("30"), seed=41)
    second = random_audit_slice(list(reversed(frames)), percent=Decimal("30"), seed=41)
    assert first == second
    assert first.source is RankingSource.RANDOM_AUDIT
    assert len(first.entries) == 3
    assert {entry.frame_key for entry in first.entries} != {frame.key for frame in frames[:3]}


def test_control_rankings_have_separate_sources_and_reproducible_hashes() -> None:
    frames = [FrameInput(1, 1, 2), FrameInput(1, 2, 7), FrameInput(1, 3, 1)]
    candidates = [_candidate(1, 1, "0.8"), _candidate(1, 3, "0.9")]
    controls = control_rankings(frames, candidates, seed=9)
    rerun = control_rankings(list(reversed(frames)), list(reversed(candidates)), seed=9)
    assert controls == rerun
    assert [item.source for item in controls] == [
        RankingSource.RANDOM_CONTROL,
        RankingSource.ANNOTATION_COUNT_CONTROL,
        RankingSource.MAX_CONFIDENCE_CONTROL,
    ]
    assert [entry.frame_key for entry in controls[1].entries] == ["1:2", "1:1", "1:3"]
    assert [entry.frame_key for entry in controls[2].entries] == ["1:3", "1:1", "1:2"]
    assert len({item.content_hash for item in controls}) == 3


def test_score_explanation_is_json_safe_and_preserves_contributions() -> None:
    ranked, _ = rank_frames([FrameInput(3, 4)], [_candidate(3, 4, "0.75")], seed=2)
    explanation = explain_score(ranked[0])
    assert explanation["score"] == "0.75"
    assert explanation["contributions"] == [
        {
            "candidate_hash": ranked[0].contributions[0].candidate_hash,
            "family": "E1",
            "anchor_count": 1,
            "n_i": 1,
            "q_i": "0.75",
            "contribution": "0.75",
        }
    ]


def test_bdd100k_snapshot_fixture_to_score_and_controls_is_reproducible() -> None:
    """M-02 seam: normalized BDD100K snapshot -> real engine -> score/control."""
    snapshot = json.loads(BDD100K_FIXTURE.read_text(encoding="utf-8"))
    job = snapshot["jobs"][0]
    frame_keys = tuple(
        FrameKey(job["cvat_task_id"], frame["frame_index"]) for frame in job["frames"]
    )
    engine_input = EngineInput(
        idempotency_key="m02-fixture:duplicate:shard-0",
        run_id=31,
        snapshot_id=20,
        engine=DUPLICATE_OVERLAP_ENGINE_NAME,
        engine_version=DUPLICATE_OVERLAP_ENGINE_VERSION,
        config=EngineConfig(
            engine=DUPLICATE_OVERLAP_ENGINE_NAME,
            version="bdd100k-guideline-v1",
            enabled=True,
            params={"iou_threshold": 0.85},
        ),
        seed=20261009,
        shard_index=0,
        units=tuple(EngineUnitRef(kind="frame", frame=key) for key in frame_keys),
    )
    annotations_by_frame = {
        key: tuple(
            Annotation(
                annotation_id=str(shape["source"]["id"]),
                label=str(shape["label_id"]),
                x1=shape["points"][0],
                y1=shape["points"][1],
                x2=shape["points"][2],
                y2=shape["points"][3],
            )
            for shape in frame["shapes"]
        )
        for key, frame in zip(frame_keys, job["frames"], strict=True)
    }
    engine_output = run_duplicate_overlap_engine(engine_input, annotations_by_frame)
    rerun_engine_output = run_duplicate_overlap_engine(
        engine_input, dict(reversed(tuple(annotations_by_frame.items())))
    )
    candidates = [asdict(candidate) for candidate in engine_output.candidates]
    frames = [
        FrameInput(
            job["cvat_task_id"],
            frame["frame_index"],
            len(frame["shapes"]),
            ((DUPLICATE_OVERLAP_ENGINE_NAME, "checked"),),
        )
        for frame in job["frames"]
    ]
    first_risk, first_risk_hash = rank_frames(
        frames,
        candidates,
        seed=20261009,
        required_engines=(DUPLICATE_OVERLAP_ENGINE_NAME,),
    )
    second_risk, second_risk_hash = rank_frames(
        list(reversed(frames)),
        list(reversed(candidates)),
        seed=20261009,
        required_engines=(DUPLICATE_OVERLAP_ENGINE_NAME,),
    )
    first_controls = control_rankings(frames, candidates, seed=20261009)
    second_controls = control_rankings(
        list(reversed(frames)), list(reversed(candidates)), seed=20261009
    )

    def content_hash(value: object) -> str:
        return sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()

    assert engine_output == rerun_engine_output
    assert first_risk == second_risk
    assert first_risk_hash == second_risk_hash
    assert first_controls == second_controls
    assert content_hash((engine_output, first_risk, first_controls)) == content_hash(
        (rerun_engine_output, second_risk, second_controls)
    )
    assert all(not frame.missing_evidence for frame in first_risk)
    assert len(random_audit_slice(frames, percent=Decimal("50"), seed=20261009).entries) == 1


@pytest.mark.parametrize("percent", [Decimal("-1"), Decimal("100.1")])
def test_random_audit_slice_rejects_invalid_percentage(percent: Decimal) -> None:
    with pytest.raises(ValueError, match="percent"):
        random_audit_slice([FrameInput(1, 1)], percent=percent, seed=1)
