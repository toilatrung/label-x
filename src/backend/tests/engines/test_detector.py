"""Contract adapter Faster R-CNN của backend."""

import hashlib
import json
from types import SimpleNamespace
from types import SimpleNamespace as NS

import pytest
from django.test import override_settings

from engines.detector import (
    BDD100K_DETECTOR_CLASSES,
    DetectorProvenanceError,
    _candidates_for_frame,
    _detection_candidate,
    verify_artifact,
)
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
        {
            "bbox_xyxy": [50, 50, 70, 70],
            "class_id": 0,
            "class_name": "pedestrian",
            "confidence": 0.8,
        },
    ]
    candidates = _candidates_for_frame(_input(), frame, detections)
    assert [candidate.family for candidate in candidates] == ["E1", "E2"]
    assert candidates[1].evidence["annotated_class_id"] == 7
    assert candidates[1].evidence["iou"] == 1.0


def det(box, class_id=2, confidence=0.9):
    return {
        "bbox_xyxy": box,
        "class_id": class_id,
        "class_name": BDD100K_DETECTOR_CLASSES[class_id],
        "confidence": confidence,
    }


def ann(points, label_id=2, source_id=8):
    return {"points": points, "label_id": label_id, "source": {"kind": "shape", "id": source_id}}


def test_iou_exactly_at_match_threshold_matches():
    # IoU = 50/100 = 0.5 đúng ngưỡng: ghép (>=) và khác nhãn ⇒ E2 match.
    frame = _frame([ann([0, 0, 10, 10], label_id=7)])
    candidates = _candidates_for_frame(_input(), frame, [det([0, 0, 5, 10])])
    assert [c.family for c in candidates] == ["E2"]
    assert candidates[0].evidence["match_status"] == "matched"
    assert candidates[0].evidence["iou"] == 0.5


def test_iou_below_threshold_does_not_match_either_side():
    # IoU = 40/100 = 0.4 là ambiguous (>=0,30 nhưng <0,50): không ghép ⇒ cả hai phía no-match.
    frame = _frame([ann([0, 0, 10, 10])])
    candidates = _candidates_for_frame(_input(), frame, [det([0, 0, 4, 10])])
    assert sorted(c.evidence["match_status"] for c in candidates) == [
        "unmatched_annotation",
        "unmatched_detection",
    ]


def test_unmatched_annotation_has_no_fake_prediction():
    candidates = _candidates_for_frame(_input(), _frame([ann([5, 5, 9, 9], label_id=3)]), [])
    (candidate,) = candidates
    evidence = candidate.evidence
    assert evidence["match_status"] == "unmatched_annotation"
    assert evidence["annotated_class_id"] == 3 and evidence["annotation_bbox"] == [5, 5, 9, 9]
    for key in ("class_id", "class_name", "confidence", "prediction_class", "margin"):
        assert key not in evidence


def test_one_to_one_never_reuses_an_annotation():
    frame = _frame([ann([0, 0, 10, 10], label_id=7)])
    detections = [det([0, 0, 10, 10]), det([0, 0, 10, 9], confidence=0.8)]
    candidates = _candidates_for_frame(_input(), frame, detections)
    assert sorted(c.family for c in candidates) == ["E1", "E2"]


def test_matching_is_deterministic_under_input_permutation():
    frame = _frame(
        [ann([0, 0, 10, 10], label_id=7), ann([20, 20, 30, 30], label_id=2, source_id=9)]
    )
    detections = [det([0, 0, 10, 10]), det([60, 60, 70, 70], class_id=4)]
    first = _candidates_for_frame(_input(), frame, detections)
    second = _candidates_for_frame(_input(), frame, list(reversed(detections)))
    key = lambda c: (c.family, c.evidence["match_status"], c.evidence.get("class_id"))  # noqa: E731
    assert sorted(map(key, first)) == sorted(map(key, second))


def test_matched_detection_without_conflict_creates_no_candidate_and_unmatched_pair_does():
    frame = _frame([ann([0, 0, 10, 10]), ann([40, 40, 50, 50], source_id=9)])
    candidates = _candidates_for_frame(_input(), frame, [det([0, 0, 10, 10])])
    assert [c.evidence["match_status"] for c in candidates] == ["unmatched_annotation"]


@pytest.mark.parametrize(
    "mutation",
    [
        {"class_id": 10},
        {"class_id": -1},
        {"class_name": "pedestrian"},
        {"class_id": 3, "class_name": "car"},
        {"confidence": float("nan")},
        {"confidence": float("inf")},
        {"confidence": -0.1},
        {"confidence": 1.01},
        {"bbox_xyxy": [0, 0, float("nan"), 4]},
        {"bbox_xyxy": [0, 0, float("inf"), 4]},
    ],
)
def test_strict_output_schema_rejects(mutation):
    with pytest.raises(ValueError, match="không hợp lệ"):
        _detection_candidate(_input(), _frame(), 0, {**det([0, 0, 4, 4]), **mutation})


# --- Xác minh artifact: manifest + checksum + class map -------------------------------------


@pytest.fixture
def artifact_files(tmp_path):
    checkpoint = tmp_path / "model.pth"
    checkpoint.write_bytes(b"not-a-real-checkpoint")
    sha = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "labelx.detector.model.v1",
        "model": {"version": "v1", "sha256": sha},
        "class_mapping": {
            "version": "bdd100k-det-10-v1",
            "classes": list(BDD100K_DETECTOR_CLASSES),
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    row = {
        "model_artifact__checksum": sha,
        "model_artifact__version": "v1",
        "model_artifact__class_mapping_version": "bdd100k-det-10-v1",
        "model_artifact__class_mapping": {},
    }
    worker = {"sha256": sha, "version": "v1", "class_mapping_version": "bdd100k-det-10-v1"}
    return NS(checkpoint=checkpoint, manifest=path, data=manifest, row=row, worker=worker, sha=sha)


def _settings(files):
    return override_settings(
        DETECTOR_CHECKPOINT_PATH=str(files.checkpoint), DETECTOR_MANIFEST_PATH=str(files.manifest)
    )


def test_verify_artifact_accepts_consistent_artifact(artifact_files):
    with _settings(artifact_files):
        provenance = verify_artifact(artifact_files.worker, artifact_files.row)
    assert provenance["verified"] is True and provenance["sha256"] == artifact_files.sha


def test_verify_artifact_rejects_missing_manifest(artifact_files):
    artifact_files.manifest.unlink()
    with _settings(artifact_files), pytest.raises(DetectorProvenanceError, match="manifest"):
        verify_artifact(artifact_files.worker, artifact_files.row)


def test_verify_artifact_rejects_checkpoint_checksum_mismatch(artifact_files):
    artifact_files.checkpoint.write_bytes(b"tampered")
    with _settings(artifact_files), pytest.raises(DetectorProvenanceError, match="checksum"):
        verify_artifact(artifact_files.worker, artifact_files.row)


def test_verify_artifact_rejects_registered_checksum_mismatch(artifact_files):
    row = {**artifact_files.row, "model_artifact__checksum": "b" * 64}
    with _settings(artifact_files), pytest.raises(DetectorProvenanceError, match="checksum"):
        verify_artifact(artifact_files.worker, row)


def test_verify_artifact_rejects_class_map_mismatch(artifact_files):
    data = artifact_files.data
    data["class_mapping"]["classes"] = list(reversed(BDD100K_DETECTOR_CLASSES))
    artifact_files.manifest.write_text(json.dumps(data))
    with _settings(artifact_files), pytest.raises(DetectorProvenanceError, match="class map"):
        verify_artifact(artifact_files.worker, artifact_files.row)


def test_verify_artifact_rejects_class_map_version_and_registered_map(artifact_files):
    worker = {**artifact_files.worker, "class_mapping_version": "other"}
    with _settings(artifact_files), pytest.raises(DetectorProvenanceError):
        verify_artifact(worker, artifact_files.row)
    row = {**artifact_files.row, "model_artifact__class_mapping": {"classes": ["car"]}}
    with _settings(artifact_files), pytest.raises(DetectorProvenanceError, match="class map"):
        verify_artifact(artifact_files.worker, row)


def test_verify_artifact_rejects_unfrozen_manifest_and_missing_artifact(artifact_files):
    data = artifact_files.data
    data["model"]["sha256"] = ""
    artifact_files.manifest.write_text(json.dumps(data))
    with _settings(artifact_files), pytest.raises(DetectorProvenanceError, match="đóng băng"):
        verify_artifact(artifact_files.worker, artifact_files.row)
    with _settings(artifact_files), pytest.raises(DetectorProvenanceError):
        verify_artifact(artifact_files.worker, None)
