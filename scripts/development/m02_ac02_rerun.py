#!/usr/bin/env python3
"""AC-02 trên stack thật (Redis + Celery worker + PostgreSQL): Redis chết lúc tạo run, SIGKILL worker,
huỷ giữa chừng. Mỗi kịch bản ghi artifact JSON (thời gian API, trạng thái shard, hash, số commit).
Chạy tuần tự; cần restart.sh/killworker.sh do người chạy cung cấp (--worker-start/--worker-kill)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from m02_e2e import Api, collect  # noqa: E402

BACKEND = Path(__file__).resolve().parents[2] / "src" / "backend"


def manage(*args: str) -> str:
    out = subprocess.run(["uv", "run", "--frozen", "python", "manage.py", *args], cwd=BACKEND,
                         capture_output=True, text=True, timeout=300)
    return out.stdout.strip().splitlines()[-1] if out.stdout.strip() else out.stderr[-300:]


def db_state(rid: int) -> dict:
    code = (
        "import json;from runs.models import QCRun;from orchestration.models import ShardCommit,CandidateRecord,LedgerUnit;"
        "from django.db.models import Count;from collections import Counter;"
        f"r=QCRun.objects.get(pk={rid});"
        "print(json.dumps(dict(status=r.status,finished=bool(r.finished_at),cancel=bool(r.cancel_requested_at),"
        "units=dict(Counter(r.work_units.values_list('status',flat=True))),"
        f"commits=ShardCommit.objects.filter(run_id={rid}).count(),"
        f"dup_keys=ShardCommit.objects.filter(run_id={rid}).values('idempotency_key').annotate(n=Count('id')).filter(n__gt=1).count(),"
        f"cands=CandidateRecord.objects.filter(run_id={rid}).count(),ledger=LedgerUnit.objects.filter(run_id={rid}).count(),"
        "rankings=r.rankings.count())))"
    )
    return json.loads(manage("shell", "-c", code))


def create(api: Api, snap: int, cfg: int, seed: int, tag: str) -> tuple[int, float, int]:
    t = time.time()
    r = api.post("/api/runs/", {"snapshot_id": snap, "config_version_id": cfg, "seed": seed}, key=f"ac02v2-{tag}-{int(t)}")
    return r.json()["id"], round(time.time() - t, 2), r.status_code


def wait_units(rid: int, status: str, n: int, timeout: int = 180) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        s = db_state(rid)
        if s["units"].get(status, 0) >= n:
            return s
        time.sleep(1)
    return db_state(rid)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--users", type=Path, required=True)
    p.add_argument("--snapshot-id", type=int, required=True)
    p.add_argument("--config-id", type=int, required=True)
    p.add_argument("--seed", type=int, default=20261010)
    p.add_argument("--baseline", type=Path, required=True, help="JSON collect() của run chuẩn")
    p.add_argument("--worker-start", required=True)
    p.add_argument("--worker-kill", required=True)
    p.add_argument("--fillers", type=int, default=6)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    base = json.loads(a.baseline.read_text())
    api = Api("http://localhost:8000", "e2e_qa_lead", json.loads(a.users.read_text())["qa_lead"])
    res: dict = {"baseline_run": base["run_id"]}

    def same(c: dict) -> dict:
        return {k: c[k] == base[k] for k in ("candidates_sha256", "content_hash", "ranking_hash", "ledger_sha256")}

    # A. Redis chết lúc tạo run
    subprocess.run(["docker", "stop", "labelx-dev-redis-1"], check=True, capture_output=True)
    rid, secs, code = create(api, a.snapshot_id, a.config_id, a.seed, "brokerdown")
    subprocess.run(["docker", "start", "labelx-dev-redis-1"], check=True, capture_output=True)
    time.sleep(5)
    before = db_state(rid)
    sweep = manage("redispatch_pending_runs", "--older-than", "0", "--running-older-than", "5")
    c = collect(api, rid)
    res["A_broker_down"] = {"run_id": rid, "api_http": code, "api_seconds": secs, "db_after_create_redis_back": before,
                            "sweeper": sweep, "final": db_state(rid), "hash_equal_baseline": same(c)}
    # B. SIGKILL worker giữa chừng (sau khi dispatch nhanh, run xong trong ~vài giây: tạo run nền
    # trước để hàng đợi sâu rồi nhắm vào run cuối)
    fillers = [create(api, a.snapshot_id, a.config_id, a.seed, f"fill-kill-{i}")[0] for i in range(a.fillers)]
    rid, secs, code = create(api, a.snapshot_id, a.config_id, a.seed, "kill")
    mid = wait_units(rid, "running", 1)
    subprocess.run(a.worker_kill, shell=True, check=False)
    time.sleep(3)
    killed = db_state(rid)
    subprocess.run(a.worker_start, shell=True, check=False)
    time.sleep(40)
    sweep = manage("redispatch_pending_runs", "--older-than", "0", "--running-older-than", "5")
    c = collect(api, rid)
    res["B_sigkill_worker"] = {"run_id": rid, "db_at_kill": mid, "db_after_kill": killed, "sweeper": sweep,
                               "final": db_state(rid), "hash_equal_baseline": same(c)}
    for f in fillers:
        collect(api, f)
    # C. Huỷ giữa chừng
    fillers = [create(api, a.snapshot_id, a.config_id, a.seed, f"fill-cancel-{i}")[0] for i in range(a.fillers)]
    rid, secs, code = create(api, a.snapshot_id, a.config_id, a.seed, "cancel")
    mid = wait_units(rid, "running", 1)
    cr = api.post(f"/api/runs/{rid}/cancel/")
    time.sleep(60)
    res["C_cancel"] = {"run_id": rid, "db_at_cancel": mid, "cancel_http": cr.status_code, "final": db_state(rid)}
    res["fillers"] = a.fillers
    a.out.write_text(json.dumps(res, indent=1))
    print(json.dumps(res)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
