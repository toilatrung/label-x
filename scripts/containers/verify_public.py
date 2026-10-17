#!/usr/bin/env python3
"""Pull both recorded GHCR digests with an empty Docker credential store."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, default=Path(".ci-artifacts/images/image-digests.json"))
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text())
    failed = []
    with tempfile.TemporaryDirectory(prefix="labelx-anonymous-pull-") as folder:
        Path(folder, "config.json").write_text('{"auths":{}}\n')
        for component in ("backend", "frontend"):
            reference = receipt["images"][component]["reference"]
            result = subprocess.run(["docker", "--config", folder, "pull", "--platform", "linux/amd64", reference],
                capture_output=True, text=True)
            if result.returncode:
                failed.append(component)
                print(f"BLOCKED anonymous pull: {reference}")
                print(f"Package settings: https://github.com/users/toilatrung/packages/container/labelx-{component}/settings")
            else:
                print(f"PASS anonymous amd64 pull: {reference}")
    if failed:
        raise SystemExit("Set both existing packages to Public and rerun publication. Do not sync Argo CD.")


if __name__ == "__main__":
    main()
