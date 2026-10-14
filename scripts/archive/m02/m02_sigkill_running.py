#!/usr/bin/env python3
"""SIGKILL worker khi chính shard của run mục tiêu đang RUNNING; đo thời gian phục hồi thật."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from m02_ac02_rerun import create, db_state, manage  # noqa: E402
from m02_e2e import Api, collect  # noqa: E402


def wait_running_fast(rid: int, timeout: float = 120) -> bool:
    """Thăm dò trực tiếp PostgreSQL mỗi 0,1 s (manage.py shell mất ~4 s/lần, run xong trước đó)."""
    import os

    import psycopg

    env = Path(__file__).resolve().parents[3] / "src" / "backend" / ".env"
    url = next(
        line.split("=", 1)[1].strip()
        for line in env.read_text().splitlines()
        if line.startswith("DATABASE_URL=")
    )
    end = time.time() + timeout
    with psycopg.connect(url.replace("postgres://", "postgresql://"), autocommit=True) as conn:
        while time.time() < end:
            n = conn.execute(
                "select count(*) from work_unit where run_id=%s and status='running'", (rid,)
            ).fetchone()[0]
            if n >= 1:
                return True
            time.sleep(0.1)
    return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--users", type=Path, required=True)
    p.add_argument("--snapshot-id", type=int, required=True)
    p.add_argument("--config-id", type=int, required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--worker-start", required=True)
    p.add_argument("--worker-kill", required=True)
    p.add_argument("--running-older-than", type=float, default=5)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    base = json.loads(a.baseline.read_text())
    api = Api("http://localhost:8000", "e2e_qa_lead", json.loads(a.users.read_text())["qa_lead"])
    rid, _, code = create(api, a.snapshot_id, a.config_id, 20261010, "sigkill-running")
    saw_running = wait_running_fast(rid)  # chính shard của run mục tiêu đang RUNNING
    t_kill = time.time()
    subprocess.run(a.worker_kill, shell=True, check=False)
    at_kill = db_state(rid)
    time.sleep(2)
    after_kill = db_state(rid)
    subprocess.run(a.worker_start, shell=True, check=False)
    time.sleep(25)  # worker mới lên; delivery lại (nếu có) bị _claim bỏ qua vì lease còn tươi
    before_sweep = db_state(rid)
    t_sweep = time.time()
    sweep = manage(
        "redispatch_pending_runs", "--older-than", "0",
        "--running-older-than", str(a.running_older_than),
    )
    c = collect(api, rid)
    t_done = time.time()
    final = db_state(rid)
    res = {
        "run_id": rid, "create_http": code, "target_shard_running_when_killed": saw_running, "db_at_kill": at_kill, "db_after_kill": after_kill,
        "db_before_sweep": before_sweep, "sweeper": sweep, "final": final,
        "seconds_kill_to_sweep": round(t_sweep - t_kill, 1),
        "seconds_kill_to_completed": round(t_done - t_kill, 1),
        "hash_equal_baseline": {
            k: c[k] == base[k]
            for k in ("candidates_sha256", "content_hash", "ranking_hash", "ledger_sha256")
        },
        "note": "sweeper chạy thủ công với --running-older-than; mặc định tự động là "
        "ORCHESTRATION_RUNNING_STALE_SECONDS=1800 + chu kỳ beat 120 s",
    }
    a.out.write_text(json.dumps(res, indent=1))
    print(json.dumps(res)[:2500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
