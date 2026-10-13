"""Contract adapter Faster R-CNN của backend."""

from types import SimpleNamespace

import pytest

from engines.detector import _candidates_for_frame, _detection_candidate
from engines.interface import EngineConfig, EngineInput, EngineUnitRef, FrameKey


def _input() -> EngineInput:
    return EngineInput(
        idempotency_key="k",
        run_id=1,
        snapshot_id=2,
        engine="detector",
        engine_version="1.0.0",
        config=EngineConfig("detector", "1", True, {}),
        seed=42,
        shard_index=0,
        units=(EngineUnitRef("frame", FrameKey(9, 4)),),
    )


def _frame(shapes=None):
    return SimpleNamespace(
        snapshot_job=SimpleNamespace(cvat_task_id=9),
        frame_index=4,
        shapes=shapes or [],
    )


def test_detection_becomes_candidate_with_routing_evidence():
    candidate = _detection_candidate(
        _input(),
        _frame(),
        0,
        {
            "bbox_xyxy": [1, 2, 30, 40],
            "class_id": 2,
            "class_name": "car",
            "confidence": 0.91,
        },
    )
    assert candidate.frame == FrameKey(9, 4)
    assert candidate.evidence["class_id"] == 2
    assert candidate.evidence["confidence"] == 0.91
    assert candidate.anchor.rule_id == "faster-rcnn-detection"


def test_detection_persists_model_provenance():
    candidate = _detection_candidate(
        _input(),
        _frame(),
        0,
        {
            "bbox_xyxy": [1, 2, 30, 40],
            "class_id": 2,
            "class_name": "car",
            "confidence": 0.91,
        },
        model={
            "version": "detector-v1",
            "sha256": "a" * 64,
            "class_mapping_version": "bdd100k-det-10-v1",
        },
    )
    assert candidate.evidence["model_version"] == "detector-v1"
    assert candidate.evidence["checkpoint_sha256"] == "a" * 64
    assert candidate.evidence["class_mapping_version"] == "bdd100k-det-10-v1"


@pytest.mark.parametrize(
    "detection",
    [
        {},
        {"bbox_xyxy": [1, 2, 3], "class_id": 2, "class_name": "car", "confidence": 0.9},
        {"bbox_xyxy": [1, 2, 3, 4], "class_id": "2", "class_name": "car", "confidence": 0.9},
        {"bbox_xyxy": [1, 2, 3, 4], "class_id": 2, "class_name": "car", "confidence": 2},
    ],
)
def test_invalid_worker_detection_is_rejected(detection):
    with pytest.raises(ValueError, match="không hợp lệ"):
        _detection_candidate(_input(), _frame(), 0, detection)


def test_matching_detection_same_label_is_not_a_qc_candidate():
    frame = _frame(
        [{"points": [1, 2, 30, 40], "label_id": 2, "source": {"kind": "shape", "id": 8}}]
    )
    detections = [
        {"bbox_xyxy": [1, 2, 30, 40], "class_id": 2, "class_name": "car", "confidence": 0.9}
    ]
    assert _candidates_for_frame(_input(), frame, detections) == []


def test_unmatched_detection_is_e1_and_wrong_label_match_is_e2():
    frame = _frame(
        [{"points": [1, 2, 30, 40], "label_id": 7, "source": {"kind": "shape", "id": 8}}]
    )
    detections = [
        {"bbox_xyxy": [1, 2, 30, 40], "class_id": 2, "class_name": "car", "confidence": 0.9},
        {"bbox_xyxy": [50, 50, 70, 70], "class_id": 0, "class_name": "person", "confidence": 0.8},
    ]
    candidates = _candidates_for_frame(_input(), frame, detections)
    assert [candidate.family for candidate in candidates] == ["E1", "E2"]
    assert candidates[1].evidence["annotated_class_id"] == 7
    assert candidates[1].evidence["iou"] == 1.0
