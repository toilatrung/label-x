#!/usr/bin/env python3
"""Check a fresh small-host deployment budget or report live disk pressure; no load acceptance."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['fresh', 'live'], default='fresh')
    args = parser.parse_args()
    budget = json.loads((ROOT / 'infrastructure/vps-budget.json').read_text())
    mem = {line.split(':')[0]: int(line.split()[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:', 'MemAvailable:'))}
    disks = {str(Path(path).resolve()): shutil.disk_usage(path) for path in ('/', '/var/lib/docker' if Path('/var/lib/docker').exists() else '/', '/var/lib/rancher/k3s' if Path('/var/lib/rancher/k3s').exists() else '/')}
    gib = 1024**3
    print(f"Memory total={mem['MemTotal']/gib:.2f} GiB available={mem['MemAvailable']/gib:.2f} GiB")
    print(f"Configured workload peak limits={budget['workload_peak_mib']/1024:.2f} GiB; control plane/OS reserve=3 GiB; desired additional headroom=1 GiB")
    failed = False
    if args.phase == 'fresh' and mem['MemTotal'] < (budget['workload_peak_mib'] + 4096) * 1024**2:
        print('BLOCKED nominal RAM is below combined ceilings + reserves. Move CVAT off-host or upgrade RAM; do not promise concurrent capacity.')
        failed = True
    if args.phase == 'fresh' and mem['MemAvailable'] < (budget['workload_peak_mib'] + 1024) * 1024**2:
        print('BLOCKED available RAM is below fresh workload limits + headroom. Inspect existing workloads; do not stop them automatically.')
        failed = True
    for path, disk in disks.items():
        used = disk.used / disk.total
        print(f"Disk {path}: {disk.free/gib:.1f} GiB free, {used:.0%} used")
        if used >= .85 or (args.phase == 'fresh' and disk.free < 65*gib):
            print('BLOCKED disk pressure or insufficient fresh small-dataset budget. Move CVAT/data or increase SSD.')
            failed = True
        elif used >= .75:
            print('WARNING disk at least 75% used; reduce ingestion and investigate before 85%')
    print('No VPS deployment, throughput, RTO or MVP acceptance is implied by this budget check.')
    return int(failed)


if __name__ == '__main__': sys.exit(main())
