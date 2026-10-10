"""Offline contract checks for the M-DEMO01 real-data smoke receipt."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RECEIPT_PATH = ROOT / "fixtures/demo/m-demo01-bdd100k-realdata-receipt.json"


def test_realdata_receipt_proves_snapshot_run_and_replay() -> None:
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))

    assert receipt["schema_version"] == "labelx-m-demo01-realdata-receipt-v1"
    assert receipt["source"]["dataset"] == "BDD100K"
    assert receipt["source"]["frame_count"] == 5
    assert receipt["source"]["annotation_count"] == 106

    snapshot = receipt["snapshot"]
    assert snapshot["status"] == "locked"
    assert snapshot["job_count"] == 1
    assert snapshot["frame_count"] == receipt["source"]["frame_count"]
    assert snapshot["replay_snapshot_id"] == snapshot["snapshot_id"]
    assert len(snapshot["revision_sha256"]) == 64

    run = receipt["run"]
    assert run["status"] == "completed"
    assert run["failed_work_units"] == 0
    assert run["score_version"] == "score_v0"
    assert run["replay"]["run_id"] == run["run_id"]
    assert run["replay"]["action"] == "reused"
    assert run["replay"]["executed_work_units"] == 0
    assert run["replay"]["ranking_hash"] == run["ranking_hash"]

    api = receipt["api"]
    assert api["ranks"] == list(range(1, api["item_count"] + 1))
    assert len(api["scores"]) == api["item_count"]
    assert {row["status"] for row in api["engines"]} == {"checked"}
    assert api["top_frame"]["image_status"] == 200
    assert api["top_frame"]["image_bytes"] > 0


def test_realdata_receipt_contains_no_images_or_credentials() -> None:
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    repository_payload = receipt["repository_payload"]

    assert repository_payload["contains_source_images"] is False
    assert repository_payload["contains_credentials"] is False
    assert "Bearer " not in RECEIPT_PATH.read_text(encoding="utf-8")
