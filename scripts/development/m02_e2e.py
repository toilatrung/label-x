#!/usr/bin/env python3
"""M-02 E2E qua API thật: snapshot -> config -> run (hai lần) -> worker Celery -> ranking.

Không dispatch thủ công: chỉ gọi POST /api/snapshots/ và POST /api/runs/. Băm nội dung đã chuẩn hóa
(bỏ id/timestamp của run) để so AC-01. Chạy bằng `uv run --project src/backend python ...`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path

import httpx


def canon(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(obj: object) -> str:
    return hashlib.sha256(canon(obj).encode()).hexdigest()


class Api:
    def __init__(self, base: str, user: str, password: str) -> None:
        self.c = httpx.Client(base_url=base, timeout=120)
        self.c.get("/api/auth/csrf/")
        self.csrf = self.c.cookies.get("csrftoken", "")
        r = self.c.post(
            "/api/auth/login/",
            json={"username": user, "password": password},
            headers={"X-CSRFToken": self.csrf},
        )
        r.raise_for_status()
        self.csrf = self.c.cookies.get("csrftoken", self.csrf)

    def get(self, path: str, **params: object) -> httpx.Response:
        return self.c.get(path, params=params)

    def post(self, path: str, body: dict | None = None, key: str | None = None) -> httpx.Response:
        headers = {"X-CSRFToken": self.csrf}
        headers["Idempotency-Key"] = str(uuid.uuid5(uuid.NAMESPACE_URL, key or canon([path, body])))
        return self.c.post(path, json=body or {}, headers=headers)


def pages(api: Api, path: str, **params: object) -> list[dict]:
    out: list[dict] = []
    url: str | None = path
    while url:
        r = api.get(url, **params) if url == path else api.c.get(url)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return data
        out += data.get("results", data.get("items", []))
        url = data.get("next")
        params = {}
    return out


def wait(api: Api, path: str, done: set[str], timeout: int = 600) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        body = api.get(path).json()
        if body["status"] in done:
            return body
        time.sleep(2)
    raise TimeoutError(path)


def collect(api: Api, rid: int) -> dict:
    run = wait(api, f"/api/runs/{rid}/", {"completed", "partial", "failed", "cancelled"}, 900)
    cands = pages(api, f"/api/runs/{rid}/candidates/")
    rank = api.get(f"/api/runs/{rid}/ranking/").json()
    ledger = pages(api, f"/api/runs/{rid}/ledger/")
    shards = pages(api, f"/api/runs/{rid}/shards/")
    return {
        "run_id": rid,
        "status": run["status"],
        "finished_at": run.get("finished_at"),
        "candidates": len(cands),
        "candidates_sha256": sha(sorted(canon(c) for c in cands)),
        "content_hash": rank.get("content_hash"),
        "ranking_hash": rank.get("ranking_hash"),
        "ledger_sha256": sha(ledger),
        "ledger": [(x["engine"], x["total"], x["eligible"], x["completed"], x["not_checked"]) for x in ledger],
        "shards": {st: sum(1 for x in shards if x["status"] == st) for st in {x["status"] for x in shards}},
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot-id", type=int)
    p.add_argument("--config-id", type=int)
    p.add_argument("--create-only", action="store_true")
    p.add_argument("--collect", type=int)
    p.add_argument("--base", default="http://localhost:8000")
    p.add_argument("--users", type=Path, required=True)
    p.add_argument("--dataset-id", type=int, required=True)
    p.add_argument("--seed", type=int, default=20261010)
    p.add_argument("--tag", default="a")
    p.add_argument("--out", type=Path, default=Path("/dev/null"))
    a = p.parse_args()
    pw = json.loads(a.users.read_text())
    api = Api(a.base, "e2e_qa_lead", pw["qa_lead"])
    if a.collect:
        print(json.dumps(collect(api, a.collect)))
        return 0
    if a.create_only:
        r = api.post(
            "/api/runs/",
            {"snapshot_id": a.snapshot_id, "config_version_id": a.config_id, "seed": a.seed},
            key=f"e2e-run-{a.seed}-{a.tag}",
        )
        print(r.status_code, json.dumps(r.json())[:200])
        return 0 if r.status_code < 300 else 1
    admin = Api(a.base, "e2e_qc_admin", pw["qc_admin"])
    t0 = time.time()
    r = api.post(
        "/api/snapshots/",
        {"dataset_id": a.dataset_id, "scope": {"cvat_task_ids": [], "cvat_job_ids": []}},
        key=f"e2e-snap-{a.seed}",
    )
    print("snapshot create", r.status_code, r.text[:200])
    r.raise_for_status()
    sid = r.json()["id"]
    snap = wait(api, f"/api/snapshots/{sid}/", {"locked", "failed", "drift_detected", "rejected"})
    print("snapshot", snap["status"], snap.get("hash") or snap.get("sha256"))
    cfg = admin.post(
        "/api/config-versions/",
        {
            "name": f"m02-e2e-{a.seed}",
            "engines": {
                "duplicate": {"enabled": True},
                "geometry": {"enabled": True},
                "schema": {"enabled": True},
            },
            "thresholds": {},
        },
    )
    print("config", cfg.status_code, cfg.text[:300])
    cfg.raise_for_status()
    cid = cfg.json()["id"]
    pub = admin.post(f"/api/config-versions/{cid}/publish/")
    print("publish", pub.status_code, pub.text[:120])
    if pub.status_code not in (200, 409) and cfg.json().get("status") != "published":
        pub.raise_for_status()
    result: dict = {"snapshot": snap, "config_version_id": cid, "runs": []}
    for n in (1, 2):
        r = api.post(
            "/api/runs/",
            {"snapshot_id": sid, "config_version_id": cid, "seed": a.seed},
            key=f"e2e-run-{a.seed}-{a.tag}-{n}",
        )
        print("run create", r.status_code, r.text[:300])
        r.raise_for_status()
        rid = r.json()["id"]
        run = wait(api, f"/api/runs/{rid}/", {"completed", "partial", "failed", "cancelled"})
        cands = pages(api, f"/api/runs/{rid}/candidates/")
        rank = api.get(f"/api/runs/{rid}/ranking/")
        ledger = pages(api, f"/api/runs/{rid}/ledger/")
        shards = pages(api, f"/api/runs/{rid}/shards/")
        result["runs"].append(
            {
                "run": run,
                "candidates": cands,
                "ranking_status": rank.status_code,
                "ranking": rank.json(),
                "ledger": ledger,
                "shards": shards,
            }
        )
        print("run", rid, run["status"], "cands", len(cands), "rank", rank.status_code)
    a.out.write_text(json.dumps(result, indent=1, default=str))
    print("elapsed", round(time.time() - t0, 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
