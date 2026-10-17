#!/usr/bin/env python3
"""Check both actual image pulls on the VPS before creating or syncing the Application."""
import argparse
import json
from pathlib import Path

from bootstrap import ROOT, kubectl, verify_images_on_vps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--receipt", type=Path, default=ROOT / "infrastructure/k8s/labelx/release.json")
    args = parser.parse_args()
    if kubectl("config", "current-context").stdout.strip() != args.context:
        raise RuntimeError("kubectl context mismatch")
    receipt = json.loads(args.receipt.read_text())
    verify_images_on_vps(receipt)
    print("PASS both images pulled and executed on the target cluster; no Application or Sync was created")


if __name__ == "__main__":
    main()
