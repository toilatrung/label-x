#!/usr/bin/env python3
"""Kiểm RBAC 7 vai trò trên API thật theo docs/04-api/rbac-matrix.html (cho phép + từ chối).

POST dùng body rỗng: vai trò được phép nhận 400 (validation), bị chặn nhận 403 -> không tạo dữ liệu.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from m02_e2e import Api  # noqa: E402

AN, RV, QA, AD, SA, PO, DMO = (
    "annotator", "reviewer", "qa_lead", "qc_admin", "super_admin", "product_owner", "data_model_owner",
)
ROLES = [AN, RV, QA, AD, SA, PO, DMO]
# (nhãn, method, path, vai trò được phép theo ma trận)
CASES = [
    ("snapshots_create", "POST", "/api/snapshots/", {QA, SA}),
    ("snapshots_list", "GET", "/api/snapshots/?dataset_id={ds}", {QA, AD, SA}),
    ("snapshots_retrieve", "GET", "/api/snapshots/{snap}/", {QA, AD, SA}),
    ("config_versions_list", "GET", "/api/config-versions/", {QA, AD, SA}),
    ("config_versions_create", "POST", "/api/config-versions/", {AD, SA}),
    ("runs_list", "GET", "/api/runs/", {QA, AD, SA}),
    ("runs_create", "POST", "/api/runs/", {QA, SA}),
    ("runs_retrieve", "GET", "/api/runs/{run}/", {RV, QA, AD, SA}),
    ("runs_ledger", "GET", "/api/runs/{run}/ledger/", {QA, AD, SA}),
    ("runs_shards", "GET", "/api/runs/{run}/shards/", {QA, AD, SA}),
    ("runs_ranking", "GET", "/api/runs/{run}/ranking/", {RV, QA, SA}),
    ("runs_cancel(terminal)", "POST", "/api/runs/{run}/cancel/", {QA, SA}),
    ("internal_metrics", "GET", "/internal/metrics/", {AD, SA}),
]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://localhost:8000")
    p.add_argument("--users", type=Path, required=True)
    p.add_argument("--dataset-id", type=int, default=1)
    p.add_argument("--snapshot-id", type=int, required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    pw = json.loads(a.users.read_text())
    table: dict[str, dict[str, int]] = {}
    bad: list[str] = []
    for role in ROLES:
        api = Api(a.base, f"e2e_{role}", pw[role])
        for label, method, path, allowed in CASES:
            url = path.format(ds=a.dataset_id, snap=a.snapshot_id, run=a.run_id)
            body: dict[str, object] = {"dataset_id": a.dataset_id, "scope": "invalid"} if "snapshots" in path else {}
            r = api.c.get(url) if method == "GET" else api.post(url, body)
            table.setdefault(label, {})[role] = r.status_code
            denied = r.status_code in (401, 403)
            if (role in allowed) == denied:
                bad.append(f"{label} {role}: HTTP {r.status_code}, allowed={role in allowed}")
    a.out.write_text(json.dumps({"table": table, "mismatches": bad}, indent=1))
    print("| action | " + " | ".join(ROLES) + " |")
    for label, row in table.items():
        print(f"| {label} | " + " | ".join(str(row[r]) for r in ROLES) + " |")
    print("MISMATCHES:", bad or "none")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
