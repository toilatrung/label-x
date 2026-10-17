"""#393: deterministic discovery contracts; no real-model accuracy claims.

DET-01, MAT-01 and MAT-02 are distinct contract/unit bindings. MAT-03 is supporting
coverage only until revision/resize acceptance exists; DET-02 remains planned.
"""

import hashlib
import io
import json
from unittest.mock import Mock

import pytest
from PIL import Image

from engines.detector import DetectorProvenanceError, _candidates_for_frame, verify_artifact
from engines.matching import BoundingBox, match_one_to_one
from tests.engines.test_detector import _frame, _input, _settings, ann, det
from tests.engines.test_detector import artifact_files as artifact_files


def test_mat_01_geometry_cardinality_iou_threshold_dense_and_ties():
    def box(identity, label, x1=0, x2=10, y2=10):
        return BoundingBox(identity, label, x1, 0, x2, y2)

    # The largest edge (.9) blocks a second match. Cardinality must win.
    left = [box("l1", "car"), box("l2", "bus", x2=7)]
    right = [box("r1", "person", x2=9), box("r2", "car", x1=3, x2=13)]
    result = match_one_to_one(left, right)
    assert {(m.left_id, m.right_id) for m in result.matches} == {("l1", "r2"), ("l2", "r1")}
    assert result.cardinality == 2
    # Geometry precedes class; same cardinality maximizes total IoU.
    result = match_one_to_one(
        [box("l1", "car"), box("l2", "bus", x1=20, x2=30)],
        [box("r1", "bus", y2=9), box("r2", "car", x1=20, x2=30, y2=9)],
    )
    assert result.cardinality == 2 and result.total_iou == 1.8
    assert match_one_to_one([box("l", "car")], [box("r", "bus", x2=5)]).cardinality == 1
    below = match_one_to_one([box("l", "car")], [box("r", "bus", x2=4.999)])
    assert below.cardinality == 0 and below.ambiguous
    # Dense equal-weight graph has a unique canonical result under permutations.
    left = [box(f"l{i:02}", "car") for i in range(16)]
    right = [box(f"r{i:02}", "bus") for i in range(16)]
    result = match_one_to_one(left, right)
    assert [(m.left_id, m.right_id) for m in result.matches] == [
        (f"l{i:02}", f"r{i:02}") for i in range(16)
    ]
    assert match_one_to_one(left[::-1], right[::-1]).to_dict() == result.to_dict()


def test_mat_02_disagreement_candidates_without_ground_truth():
    from orchestration.routing_policy import RoutingPolicy, route, routing_input_from_candidate

    model = {
        "version": "frozen-stub",
        "sha256": "a" * 64,
        "class_mapping_version": "bdd100k-det-10-v1",
        "verified": True,
    }
    frame = _frame(
        [ann([0, 0, 10, 10], label_id=4), ann([70, 70, 80, 80], label_id=3, source_id=9)]
    )
    candidates = _candidates_for_frame(
        _input(), frame, [det([0, 0, 10, 10]), det([30, 30, 40, 40])], model=model
    )
    by_family = {c.family: c for c in candidates}
    assert set(by_family) == {"E1", "E2", "E3"}
    assert by_family["E1"].evidence["match_status"] == "unmatched_detection"
    assert by_family["E2"].evidence["match_status"] == "matched"
    assert by_family["E2"].evidence["iou"] == 1.0
    assert by_family["E2"].evidence["annotated_class_name"] == "bus"
    assert by_family["E3"].evidence["match_status"] == "unmatched_annotation"
    assert "confidence" not in by_family["E3"].evidence
    for candidate in candidates:
        evidence = candidate.evidence
        assert candidate.frame == _input().units[0].frame
        assert evidence["artifact_verified"] is True
        assert evidence["checkpoint_sha256"] == model["sha256"]
        assert not ({"accuracy", "precision", "recall", "ground_truth"} & evidence.keys())
    decision = route(
        RoutingPolicy(),
        routing_input_from_candidate({"engine": "detector", "evidence": by_family["E2"].evidence}),
    )
    assert "label_conflict" in decision.reasons
    # Matching annotation is agreement, not an inferred confirmed error.
    assert (
        _candidates_for_frame(
            _input(), _frame([ann([0, 0, 10, 10])]), [det([0, 0, 10, 10])], model=model
        )
        == []
    )


@pytest.mark.django_db(transaction=True)
def test_det_01_artifact_fail_closed_and_no_model_not_checked(artifact_files, monkeypatch):  # noqa: F811
    from engines.detector import registered_model
    from orchestration.models import CandidateRecord
    from tests.orchestration.helpers import make_run

    worker = Mock()
    monkeypatch.setattr("engines.detector.worker_request", worker)
    monkeypatch.setattr("engines.detector.artifact_for_run", lambda _: artifact_files.row)
    with _settings(artifact_files):
        assert verify_artifact(artifact_files.worker, artifact_files.row)["verified"] is True
        original = artifact_files.checkpoint.read_bytes()
        artifact_files.checkpoint.write_bytes(b"tampered")
        with pytest.raises(DetectorProvenanceError):
            registered_model(1)
        artifact_files.checkpoint.write_bytes(original)
        artifact_files.data["class_mapping"]["classes"] = ["unmapped"]
        artifact_files.manifest.write_text(json.dumps(artifact_files.data))
        with pytest.raises(DetectorProvenanceError):
            registered_model(1)
        monkeypatch.setattr("engines.detector.artifact_for_run", lambda _: None)
        with pytest.raises(DetectorProvenanceError):
            registered_model(1)
    worker.assert_not_called()
    run = make_run("detector")
    result = run.engine_results.get(engine="detector")
    assert result.status == "not_checked" and result.reason == "no_model"
    assert result.completed_units == 0
    assert not run.work_units.filter(engine="detector").exists()
    assert not CandidateRecord.objects.filter(run=run, engine="detector").exists()
    worker.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_mat_03_support_pixels_checksum_and_frame_guard(settings, monkeypatch):
    from orchestration.vlm_crops import SnapshotCropProvider
    from tests.orchestration.test_vlm_crops import _candidate, _frame_png, _setup
    from tests.orchestration.test_vlm_stage import _env
    from vlm.errors import VlmInvalidCropError

    # Explicitly activate reused helper environment without importing its autouse fixture.
    _env.__wrapped__(settings, monkeypatch)
    run, storage = _setup([(7, [60, 40, 100, 80])])
    candidate = _candidate(run, ["shape:7"])
    provider = SnapshotCropProvider(storage)
    crop = provider.load(candidate)
    assert crop.origin["box"] == [60.0, 40.0, 100.0, 80.0]
    assert crop.origin["frame"]["frame_number"] == 0
    assert crop.origin["frame"]["media_sha256"] == hashlib.sha256(_frame_png()).hexdigest()
    image = Image.open(io.BytesIO(crop.data))
    assert image.size == (48, 48) and image.getpixel((24, 24)) == (0, 255, 0)
    assert image.getpixel((1, 1)) == (255, 0, 0)
    key = next(iter(storage.blobs))
    raw = storage.blobs[key]
    storage.blobs[key] = bytes([raw[0] ^ 1]) + raw[1:]
    with pytest.raises(VlmInvalidCropError, match="sha256"):
        provider.load(candidate)
    candidate.frame_number = 999999
    assert provider.identity(candidate) == ""
    with pytest.raises(VlmInvalidCropError):
        provider.load(candidate)
