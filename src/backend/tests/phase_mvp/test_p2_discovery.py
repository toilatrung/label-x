"""#393: deterministic discovery contracts; no real-model accuracy claims.

Each matrix case has a distinct node. Integration uses PostgreSQL, filesystem
images and a frozen detector transport stub, never a real-model accuracy claim.
"""

import hashlib
import io
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from engines.detector import DetectorProvenanceError, _candidates_for_frame, verify_artifact
from engines.matching import BoundingBox, match_one_to_one
from tests.engines.test_detector import _frame, _input, _settings, ann, det
from tests.engines.test_detector import artifact_files as artifact_files


def _sha(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@pytest.fixture
def discovery_run(artifact_files, settings, monkeypatch, tmp_path):
    from django.contrib.auth.models import User
    from django.core.files.base import ContentFile
    from django.core.files.storage import storages
    from PIL import ImageDraw

    from runs.models import ConfigVersion, ModelArtifact
    from runs.services import create_qc_run
    from snapshots.normalization import FrameExport, JobExport
    from snapshots.services import create_locked_snapshot

    settings.STORAGES = {
        **settings.STORAGES,
        "snapshots": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path / "images")},
        },
    }
    image = Image.new("RGB", (2400, 1400), "red")
    ImageDraw.Draw(image).rectangle((600, 400, 1799, 999), fill="lime")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    raw = buffer.getvalue()
    storage = storages["snapshots"]
    frames = []
    for index in range(3):
        # The final frame really cannot decode; its checksum is nevertheless valid.
        data = raw if index < 2 else b"invalid-png"
        key = storage.save(f"frame-{index}.png", ContentFile(data))
        frames.append(
            FrameExport(
                frame_index=index,
                source_frame_id=index,
                file_name=f"{index}.png",
                width=2400,
                height=1400,
                media_bytes=data,
                media_storage_key=key,
            )
        )
    user = User.objects.create(username="phase393")
    snapshot = create_locked_snapshot(
        dataset_id=393,
        created_by=user,
        jobs=[JobExport(5, 9, "frozen-393", {"shapes": [], "tracks": []}, tuple(frames), None)],
        taxonomy_version="t393",
        guideline_version="g393",
    )
    ModelArtifact.objects.create(
        name="frozen-393",
        version="v1",
        checksum=artifact_files.sha,
        class_mapping_version="bdd100k-det-10-v1",
        class_mapping=artifact_files.data["class_mapping"],
    )
    params = {"batch_size": 2, "score_threshold": 0.05}
    config = ConfigVersion.objects.create(
        name="phase393",
        status="published",
        created_by=user,
        payload={"shard_size": 2},
        engines={"detector": {"enabled": True, "params": params}},
        models={"name": "frozen-393", "version": "v1"},
    )
    requests = []

    def frozen_worker(method, path, body):
        import base64

        assert (method, path) == ("POST", "/infer")
        assert body["model_sha256"] == artifact_files.sha
        assert body["batch_size"] == 2 and body["score_threshold"] == 0.05
        requests.append(deepcopy(body))
        images = []
        for item in body["images"]:
            data = base64.b64decode(item["image_base64"])
            assert hashlib.sha256(data).hexdigest() == item["sha256"]
            try:
                with Image.open(io.BytesIO(data)) as decoded:
                    decoded.load()
                    assert decoded.size == (2400, 1400)
            except OSError as exc:
                raise ValueError("frozen worker: image decode failed") from exc
            # Worker contract returns original coordinates after its internal resize.
            images.append({"path": item["path"], "detections": [det([600, 400, 1800, 1000])]})
        return {
            "schema_version": "labelx.detector.predictions.v1",
            "model": artifact_files.worker,
            "images": images,
        }

    monkeypatch.setattr("engines.detector.worker_request", frozen_worker)
    with _settings(artifact_files):
        run, _ = create_qc_run(
            snapshot_id=snapshot.pk,
            config_version_id=config.pk,
            seed=393,
            created_by=user,
        )
        yield SimpleNamespace(
            run=run,
            storage=storage,
            raw=raw,
            params=params,
            files=artifact_files,
            requests=requests,
            user=user,
            snapshot=snapshot,
            config=config,
        )


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
def test_det_02_batch_ledger_original_coordinates_provenance_and_rerun(discovery_run):
    from orchestration.dispatch import run_work_unit
    from orchestration.models import CandidateRecord, LedgerUnit, ShardCommit
    from runs.services import create_qc_run

    fixture = discovery_run
    run = fixture.run
    units = list(run.work_units.order_by("shard_index"))
    assert len(units) == 2
    assert run_work_unit.run(units[0].pk) == "completed"
    # Delivery replay must neither call inference nor duplicate the commit/evidence.
    assert run_work_unit.run(units[0].pk) == "completed"
    assert len(fixture.requests) == 1 and len(fixture.requests[0]["images"]) == 2
    with pytest.raises(ValueError, match="image decode failed"):
        run_work_unit.run(units[1].pk)
    assert list(
        LedgerUnit.objects.filter(run=run)
        .order_by("frame_number")
        .values_list("cvat_task_id", "frame_number", "outcome")
    ) == [(9, 0, "completed"), (9, 1, "completed"), (9, 2, "failed")]
    result = run.engine_results.get(engine="detector")
    assert (result.eligible_units, result.completed_units, result.failed_units) == (3, 2, 1)
    assert result.status != "checked"
    candidates = list(CandidateRecord.objects.filter(run=run).order_by("frame_number"))
    assert [c.frame_number for c in candidates] == [0, 1]
    for candidate in candidates:
        evidence = candidate.evidence
        assert evidence["prediction_bbox"] == [600, 400, 1800, 1000]
        assert evidence["coordinate_space"] == "original"
        assert evidence["source_frame"] == {
            "snapshot_id": run.snapshot_id,
            "revision_sha256": fixture.snapshot.revision_sha256,
            "cvat_task_id": 9,
            "frame_number": candidate.frame_number,
            "media_sha256": hashlib.sha256(fixture.raw).hexdigest(),
            "width": 2400,
            "height": 1400,
        }
        assert evidence["checkpoint_sha256"] == fixture.files.sha
        assert evidence["model_version"] == "v1" and evidence["artifact_verified"] is True
        assert evidence["class_mapping_version"] == "bdd100k-det-10-v1"
        assert evidence["config_sha256"] == _sha(fixture.params)
        assert evidence["predictions_sha256"] == _sha([det([600, 400, 1800, 1000])])
    rerun, _ = create_qc_run(
        snapshot_id=run.snapshot_id,
        config_version_id=run.config_version_id,
        seed=run.seed,
        created_by=fixture.user,
    )
    assert run_work_unit.run(rerun.work_units.order_by("shard_index").first().pk) == "completed"
    assert list(
        CandidateRecord.objects.filter(run=rerun)
        .order_by("frame_number")
        .values_list("evidence_sha256", flat=True)
    ) == [c.evidence_sha256 for c in candidates]
    assert (
        ShardCommit.objects.get(run=run).output_sha256
        == ShardCommit.objects.get(run=rerun).output_sha256
    )


@pytest.mark.django_db(transaction=True)
def test_mat_03_original_crop_resize_and_wrong_frame_revision_rejected(discovery_run):
    from orchestration.dispatch import run_work_unit
    from orchestration.models import CandidateRecord
    from orchestration.vlm_crops import SnapshotCropProvider
    from vlm.errors import VlmInvalidCropError

    fixture = discovery_run
    run = fixture.run
    assert run_work_unit.run(run.work_units.order_by("shard_index").first().pk) == "completed"
    candidate = CandidateRecord.objects.get(run=run, frame_number=0)

    class DiskImages:
        # Real temporary files, adapted to the crop provider's head/get interface.
        def head(self, key):
            return SimpleNamespace(size=fixture.storage.size(key))

        def get(self, key):
            with fixture.storage.open(key, "rb") as stream:
                return stream.read()

    provider = SnapshotCropProvider(DiskImages())
    crop = provider.load(candidate)
    assert crop.origin["snapshot_id"] == run.snapshot_id
    assert crop.origin["revision_sha256"] == fixture.snapshot.revision_sha256
    assert crop.origin["box"] == [600, 400, 1800, 1000]
    assert crop.origin["padded_box"] == [480, 280, 1920, 1120]
    assert crop.origin["frame"]["frame_number"] == 0
    assert crop.origin["frame"]["media_sha256"] == hashlib.sha256(fixture.raw).hexdigest()
    image = Image.open(io.BytesIO(crop.data))
    assert image.size == (1024, 597) and crop.origin["output_size"] == [1024, 597]
    assert image.getpixel((512, 298)) == (0, 255, 0)
    assert image.getpixel((1, 1)) == (255, 0, 0)
    original = deepcopy(candidate.evidence)
    # Even an existing adjacent frame with identical pixels is the wrong frame.
    candidate.frame_number = 1
    assert provider.identity(candidate) == ""
    with pytest.raises(VlmInvalidCropError, match="frame/revision"):
        provider.load(candidate)
    candidate.frame_number = 0
    for field, wrong in (
        ("revision_sha256", "0" * 64),
        ("snapshot_id", run.snapshot_id + 1),
        ("media_sha256", "0" * 64),
        ("width", 1200),
    ):
        candidate.evidence = deepcopy(original)
        candidate.evidence["source_frame"][field] = wrong
        assert provider.identity(candidate) == ""
        with pytest.raises(VlmInvalidCropError, match="frame/revision"):
            provider.load(candidate)
    candidate.evidence = {**original, "coordinate_space": "resized"}
    assert provider.identity(candidate) == ""
    with pytest.raises(VlmInvalidCropError):
        provider.load(candidate)
    candidate.evidence = original
    candidate.anchor = {"objects": [{"namespace": "shape", "id": "missing"}]}
    with pytest.raises(VlmInvalidCropError):
        provider.load(candidate)
    candidate.refresh_from_db()
    key = fixture.snapshot.jobs.get().frames.get(frame_index=0).media_storage_key
    with fixture.storage.open(key, "wb") as stream:
        stream.write(bytes([fixture.raw[0] ^ 1]) + fixture.raw[1:])
    with pytest.raises(VlmInvalidCropError, match="sha256"):
        provider.load(candidate)
