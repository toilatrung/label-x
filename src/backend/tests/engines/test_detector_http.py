"""HTTP adapter, full ROI distribution and retained PR #315 routing contracts."""

import base64
import hashlib
import json
from unittest.mock import patch

import httpx
import pytest

from engines.detector import (
    BDD100K_DETECTOR_CLASSES,
    _candidates_for_frame,
    _run_worker,
    distribution_evidence,
    run_detector_engine,
)
from engines.interface import EngineConfig, EngineInput, EngineUnitRef, FrameKey
from orchestration.routing_policy import (
    RoutingInput,
    RoutingPolicy,
    RoutingReason,
    route,
    routing_input_from_candidate,
)
from runs.models import ConfigVersion, ModelArtifact, QCRun
from snapshots.models import SnapshotFrame
from tests.engines.test_detector import _frame, _input, ann, det
from tests.orchestration.test_vlm_crops import _frame_png
from tests.orchestration.test_vlm_stage import _env, _make_run  # noqa: F401


def scored(scores=None, class_id=2):
    values = scores or [0, 0, 0.9, 0.05, 0, 0, 0, 0, 0, 0, 0.05]
    return {**det([0, 0, 10, 10], class_id, values[class_id]), "class_scores": values}


def test_margin_excludes_background_without_renormalizing():
    result = distribution_evidence(scored([0, 0, 0.4, 0.2, 0, 0, 0, 0, 0, 0, 0.4]))
    assert result["score"] == 0.4 and result["margin"] == 0.2
    assert result["unknown"] is True


@pytest.mark.parametrize("scores", [[], [0.1] * 10, [0.1] * 11, [float("nan")] * 11, [True] * 11])
def test_incomplete_or_invalid_distribution_is_rejected(scores):
    with pytest.raises(ValueError):
        distribution_evidence({**det([0, 0, 10, 10]), "class_scores": scores}, required=True)


def test_confidence_must_come_from_same_roi():
    with pytest.raises(ValueError, match="confidence"):
        distribution_evidence({**scored(), "confidence": 0.8})


@pytest.mark.parametrize("margin, triggered", [(0.1499, True), (0.15, False), (0.1501, False)])
def test_low_margin_boundary_when_full_distribution_available(margin, triggered):
    decision = route(
        RoutingPolicy(),
        RoutingInput(score=0.95, margin=margin, full_distribution=True, source_trusted=True),
    )
    assert (RoutingReason.LOW_MARGIN in decision.reasons) is triggered
    assert decision.call_qwen is triggered


def test_background_unknown_and_full_scores_flow_to_existing_router():
    evidence = {
        **scored([0, 0, 0.2, 0.1, 0, 0, 0, 0, 0, 0, 0.7]),
        "artifact_verified": True,
        "match_status": "matched",
        "annotated_class_id": 102,
        "predicted_label_id": 102,
    }
    data = routing_input_from_candidate({"engine": "detector", "evidence": evidence})
    decision = route(RoutingPolicy(), data)
    assert decision.primary is RoutingReason.UNKNOWN and decision.call_qwen
    assert RoutingReason.LABEL_CONFLICT not in decision.reasons


def test_no_match_still_bypasses_qwen_even_with_unknown():
    evidence = {**scored(), "match_status": "unmatched_annotation", "artifact_verified": True}
    decision = route(
        RoutingPolicy(), routing_input_from_candidate({"engine": "detector", "evidence": evidence})
    )
    assert decision.primary is RoutingReason.DETECTOR_NO_MATCH
    assert decision.human_review_required and not decision.call_qwen


def test_matching_uses_cvat_label_ids_not_model_indices():
    labels = {name: i + 100 for i, name in enumerate(BDD100K_DETECTOR_CLASSES)}
    assert not _candidates_for_frame(
        _input(), _frame([ann([0, 0, 10, 10], 102)]), [scored()], label_ids=labels
    )
    (candidate,) = _candidates_for_frame(
        _input(), _frame([ann([0, 0, 10, 10], 103)]), [scored()], label_ids=labels
    )
    assert candidate.evidence["predicted_label_id"] == 102
    assert (
        route(
            RoutingPolicy(),
            routing_input_from_candidate(
                {
                    "engine": "detector",
                    "evidence": {**candidate.evidence, "artifact_verified": True},
                }
            ),
        ).primary
        is RoutingReason.LABEL_CONFLICT
    )


def test_same_label_unknown_is_retained_for_review():
    (candidate,) = _candidates_for_frame(
        _input(), _frame([ann([0, 0, 10, 10])]), [scored([0, 0, 0.2, 0.1, 0, 0, 0, 0, 0, 0, 0.7])]
    )
    assert candidate.evidence["unknown"] is True and candidate.evidence["match_status"] == "matched"


def test_http_adapter_has_auth_timeout_and_no_proxy_or_redirect(settings):
    settings.DETECTOR_WORKER_URL = "http://127.0.0.1:8501"
    settings.DETECTOR_SERVICE_TOKEN = "test-only-token-not-real-credential"
    settings.DETECTOR_TIMEOUT_SECONDS = 37
    with patch("engines.detector.httpx.Client") as client:
        post = client.return_value.__enter__.return_value.post
        post.return_value.json.return_value = {"ok": True}
        assert _run_worker({"frame_number": 1}, b"image", {"sha256": "a" * 64}) == {"ok": True}
        client.assert_called_once_with(timeout=37.0, trust_env=False, follow_redirects=False)
        assert post.call_args.kwargs["headers"]["Authorization"].startswith("Bearer ")
        assert base64.b64decode(post.call_args.kwargs["json"]["image_base64"]) == b"image"


@pytest.mark.parametrize(
    "url",
    ["http://worker.example", "https://user:pass@worker.example", "http://127.0.0.1:8501?secret=x"],
)
def test_remote_plaintext_or_unsafe_url_is_rejected(settings, url):
    settings.DETECTOR_WORKER_URL = url
    settings.DETECTOR_SERVICE_TOKEN = "test-token"
    with pytest.raises(ValueError):
        _run_worker({}, b"image", {"sha256": "a" * 64})


def test_network_error_redacts_sensitive_exception(settings):
    settings.DETECTOR_WORKER_URL = "http://127.0.0.1:8501"
    settings.DETECTOR_SERVICE_TOKEN = "test-token"
    with patch("engines.detector.httpx.Client") as client:
        client.return_value.__enter__.return_value.post.side_effect = httpx.ConnectError("secret")
        with pytest.raises(RuntimeError, match="^detector worker request failed$"):
            _run_worker({}, b"image", {"sha256": "a" * 64})


@pytest.fixture
def http_run(settings, tmp_path):
    raw = _frame_png()
    run = _make_run(
        frame_media={0: raw},
        frame_size=(200, 120),
        raw_shapes=[
            {"id": 7, "type": "rectangle", "frame": 0, "label_id": 103, "points": [0, 0, 10, 10]}
        ],
    )
    checkpoint = tmp_path / "model.pth"
    checkpoint.write_bytes(b"isolated-checkpoint")
    checksum = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "labelx.detector.model.v1",
                "model": {"sha256": checksum, "version": "v1"},
                "class_mapping": {
                    "version": "bdd100k-det-10-v1",
                    "classes": list(BDD100K_DETECTOR_CLASSES),
                },
            }
        )
    )
    settings.DETECTOR_CHECKPOINT_PATH = str(checkpoint)
    settings.DETECTOR_MANIFEST_PATH = str(manifest)
    cfg = ConfigVersion.objects.create(
        name="HTTP test",
        status="published",
        created_by=run.created_by,
        engines={
            "detector": {"enabled": True},
            "schema": {
                "enabled": False,
                "params": {
                    "taxonomy": {
                        "version": run.snapshot.taxonomy_version,
                        "labels": [
                            {"label_id": i + 100, "name": name}
                            for i, name in enumerate(BDD100K_DETECTOR_CLASSES)
                        ],
                    }
                },
            },
        },
    )
    artifact = ModelArtifact.objects.create(
        name="HTTP test",
        version="v1",
        checksum=checksum,
        class_mapping_version="bdd100k-det-10-v1",
        class_mapping={"classes": list(BDD100K_DETECTOR_CLASSES)},
    )
    QCRun.objects.filter(pk=run.pk).update(config_version=cfg, model_artifact=artifact)
    inp = EngineInput(
        "http-test",
        run.pk,
        run.snapshot_id,
        "detector",
        "1.0.0",
        EngineConfig("detector", "v1", True, {}),
        42,
        0,
        (EngineUnitRef("frame", FrameKey(9, 0)),),
    )
    frame = SnapshotFrame.objects.get(snapshot_job__snapshot_id=run.snapshot_id, frame_index=0)
    return run, inp, frame, raw, checkpoint


@pytest.mark.django_db(transaction=True)
def test_verified_http_snapshot_to_candidate_and_idempotent_commit(http_run):
    from orchestration.services import commit_shard_output, seed_ledger

    run, inp, frame, raw, _ = http_run

    def predict(identity, image, model):
        assert image == raw and model["verified"] is True
        return {
            "schema_version": "labelx.detector.frame.v1",
            "frame": identity,
            "model_sha256": model["sha256"],
            "class_mapping_version": model["class_mapping_version"],
            "model": model,
            "classes": list(BDD100K_DETECTOR_CLASSES),
            "detections": [scored()],
        }

    from django.core.files.base import ContentFile

    with (
        patch("engines.detector.storages") as stores,
        patch("engines.detector._run_worker", side_effect=predict),
    ):
        stores.__getitem__.return_value.open.side_effect = lambda *args: ContentFile(raw)
        output = run_detector_engine(inp)
    assert len(output.candidates) == 1 and output.candidates[0].family == "E2"
    assert output.candidates[0].evidence["artifact_verified"] is True
    assert output.candidates[0].evidence["predicted_label_id"] == 102
    seed_ledger(run.pk, "detector", inp.units)
    assert commit_shard_output(inp, output) and not commit_shard_output(inp, output)


@pytest.mark.django_db(transaction=True)
def test_artifact_preflight_fails_before_worker_is_called(http_run):
    _, inp, _, _, checkpoint = http_run
    checkpoint.write_bytes(b"tampered")
    with (
        patch("engines.detector._run_worker") as worker,
        pytest.raises(ValueError, match="checksum"),
    ):
        run_detector_engine(inp)
    worker.assert_not_called()
