#!/usr/bin/env python3
"""Read one real candidate/crop, call its configured VLM once, leave analysis state unchanged.

Usage: src/backend/.venv-wsl/bin/python scripts/smoke-vlm-candidate.py --run-id 5
Optional --env-file loads server settings when testing from an isolated checkout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--run-id", required=True, type=int)
parser.add_argument("--candidate-id", type=int)
parser.add_argument("--env-file", type=Path)
args = parser.parse_args()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/backend"))
if args.env_file:
    import environ

    environ.Env.read_env(args.env_file)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from orchestration.evaluation_service import route_candidates
from orchestration.models import CandidateRecord
from orchestration.vlm_crops import SnapshotCropProvider
from orchestration.vlm_stage import _taxonomy_for_run, run_vlm_config
from runs.models import QCRun
from vlm.client import DashScopeClient
from vlm.config import parse_vlm_config
from vlm.contract import CandidateContext, VlmRequest
from vlm.runner import CounterBudget, run_vlm_unit
from vlm.tasks import result_to_dict

run = QCRun.objects.select_related("config_version", "snapshot").get(pk=args.run_id)
raw, taxonomy = run_vlm_config(run), _taxonomy_for_run(run)
if not raw or not taxonomy:
    raise SystemExit(
        "Run lacks a valid enabled VLM configuration or snapshot taxonomy; no call made."
    )
config = replace(parse_vlm_config(raw), max_attempts=1)
qs = (
    CandidateRecord.objects.filter(run_id=run.pk)
    .exclude(engine="vlm")
    .select_related("run")
    .order_by("pk")
)
if args.candidate_id:
    qs = qs.filter(pk=args.candidate_id)
provider = SnapshotCropProvider()
chosen = None
for candidate in qs.iterator(chunk_size=100):
    decision = route_candidates(run, [candidate], exhausted=False)[0][1]
    if decision.call_qwen and provider.identity(candidate):
        chosen = candidate
        break
if chosen is None:
    raise SystemExit(
        "No policy-selected candidate with a resolvable crop; no call made."
    )
crop = provider.load(chosen)
print(
    json.dumps(
        {
            "run_id": run.pk,
            "candidate_id": chosen.pk,
            "model": config.model,
            "provider": config.provider,
            "crop_bytes": len(crop.data),
            "max_calls": 1,
        }
    ),
    flush=True,
)
request = VlmRequest(
    crop=crop,
    taxonomy=taxonomy,
    context=CandidateContext(
        candidate_id=chosen.dedup_key,
        snapshot_revision=run.snapshot.revision_sha256 or str(run.snapshot_id),
    ),
    config=config,
)
started = time.monotonic()
gate = CounterBudget(1)
result = result_to_dict(run_vlm_unit(request, DashScopeClient(), gate))
print(
    json.dumps(
        {
            "candidate_id": chosen.pk,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "reserved_attempts": gate.used,
            "result": result,
        },
        ensure_ascii=False,
    ),
    flush=True,
)
if result["status"] == "failed":
    raise SystemExit(1)
