#!/usr/bin/env python3
"""Pause labelx reconciliation and prepare a reviewed rollback to a recorded image pair."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def run(*args):
    return subprocess.run(args, cwd=ROOT, check=True, text=True, capture_output=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-commit", required=True, help="Full Git revision containing the last working receipt")
    parser.add_argument("--context", required=True)
    args = parser.parse_args()
    if len(args.release_commit) != 40 or any(char not in "0123456789abcdef" for char in args.release_commit):
        raise RuntimeError("An immutable full Git revision is required")
    if run("kubectl", "config", "current-context") != args.context:
        raise RuntimeError("kubectl context mismatch")
    if run("git", "status", "--porcelain"):
        raise RuntimeError("Use a clean checkout/worktree for the rollback PR")
    receipt = json.loads(run("git", "show", args.release_commit + ":infrastructure/k8s/labelx/release.json"))
    run("node", "-e", "require('./scripts/ci/gitops-update.cjs').validateReceipt(JSON.parse(process.argv[1]))", json.dumps(receipt))
    # Argo selfHeal would immediately undo kubectl rollout undo. Pause first.
    run("kubectl", "patch", "application", "labelx", "-n", "argocd", "--type=merge",
        "-p", '{"spec":{"syncPolicy":{"automated":null}}}')
    run("kubectl", "patch", "cronjob", "labelx-daily-backup", "-n", "labelx", "--type=merge",
        "-p", '{"spec":{"suspend":true}}')
    path = ROOT / "infrastructure/k8s/labelx/kustomization.yaml"
    current = json.loads(path.read_text())
    # Restore only images/identity. Keep the present infrastructure, secrets and PVCs.
    result = run("node", "-e", "const m=require('./scripts/ci/gitops-update.cjs');process.stdout.write(JSON.stringify(m.render(JSON.parse(process.argv[1]),JSON.parse(process.argv[2])),null,2)+'\\n')", json.dumps(current), json.dumps(receipt))
    path.write_text(result + "\n")
    (ROOT / "infrastructure/k8s/labelx/release.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("Reconciliation and scheduled backups paused. Review the digest diff, run a fresh backup, then merge the rollback PR.")
    print("Perform a full Argo sync, verify smoke, resume the CronJob and auto sync. Database and object data are preserved.")
    print("Schema rollback/DB restore requires a maintenance plan; this command does not restore or delete data.")


if __name__ == "__main__":
    main()
