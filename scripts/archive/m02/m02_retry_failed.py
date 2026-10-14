#!/usr/bin/env python3
"""retry-failed trên broker/worker thật: shard Schema lỗi cố định (taxonomy sai version) -> partial
-> POST retry-failed -> shard xếp lại (attempt+1) mà candidate/ledger của engine đã xong không đổi."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from m02_e2e import Api, collect, pages  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://localhost:8000")
    p.add_argument("--users", type=Path, required=True)
    p.add_argument("--snapshot-id", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    pw = json.loads(a.users.read_text())
    qa = Api(a.base, "e2e_qa_lead", pw["qa_lead"])
    admin = Api(a.base, "e2e_qc_admin", pw["qc_admin"])
    bad_taxonomy = {"version": "tax-sai-version", "labels": [{"label_id": 1, "name": "car"}]}
    cfg = admin.post("/api/config-versions/", {
        "name": "m02-retry-failed-schema-bad-taxonomy",
        "engines": {"duplicate": {"enabled": True}, "geometry": {"enabled": True},
                    "schema": {"enabled": True, "params": {"taxonomy": bad_taxonomy}}},
        "thresholds": {},
    })
    cfg.raise_for_status()
    cid = cfg.json()["id"]
    if cfg.json().get("status") != "published":
        admin.post(f"/api/config-versions/{cid}/publish/").raise_for_status()
    r = qa.post("/api/runs/", {"snapshot_id": a.snapshot_id, "config_version_id": cid, "seed": 7},
                key=f"retry-failed-{int(time.time())}")
    r.raise_for_status()
    rid = r.json()["id"]
    first = collect(qa, rid)
    shards1 = pages(qa, f"/api/runs/{rid}/shards/")
    rt = qa.post(f"/api/runs/{rid}/retry-failed/")
    print("retry-failed", rt.status_code, rt.json().get("status"))
    second = collect(qa, rid)
    shards2 = pages(qa, f"/api/runs/{rid}/shards/")
    out = {"run_id": rid, "config_id": cid, "first": first, "retry_http": rt.status_code,
           "second": second,
           "shard_attempts_before": {s["shard_key"] + "/" + s["engine"]: (s["status"], s["attempt"]) for s in shards1},
           "shard_attempts_after": {s["shard_key"] + "/" + s["engine"]: (s["status"], s["attempt"]) for s in shards2}}
    a.out.write_text(json.dumps(out, indent=1))
    print(json.dumps({"first": [first["status"], first["candidates"], first["shards"]],
                      "second": [second["status"], second["candidates"], second["shards"]]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
