#!/usr/bin/env python3
"""Prepare private CVAT env after inspecting existing instances. Does not start or replace CVAT."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CVAT = ROOT / 'infrastructure/cvat'


def run(*args):
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def validate_upstream():
    lock = json.loads((CVAT / 'upstream-lock.json').read_text())
    for name, digest in lock['files'].items():
        if hashlib.sha256((CVAT / 'upstream' / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Vendored upstream file changed: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    args = parser.parse_args()
    validate_upstream()
    if run('kubectl','config','current-context') != 'default':
        raise RuntimeError('Expected VPS kubectl context default')
    workloads=json.loads(run('kubectl','get','deployments,statefulsets','-A','-o','json'))['items']
    if any('cvat' in item['metadata']['name'].lower() or any(c.get('image','').startswith(('cvat/server','cvat/ui')) for c in item['spec']['template']['spec']['containers']) for item in workloads):
        raise RuntimeError('CVAT workload already exists in Kubernetes; inspect/adopt it instead of creating Compose instance')
    if args.env_file.resolve().is_relative_to(ROOT):
        raise RuntimeError('Keep private env outside the repository')
    names = run('docker', 'ps', '-a', '--format', '{{.Names}}').splitlines()
    volumes = run('docker', 'volume', 'ls', '--format', '{{.Name}}').splitlines()
    existing = [name for name in names if name.startswith(('cvat_', 'cvat-'))]
    data_exists = any(name.startswith(('cvat_', 'cvat-')) for name in volumes)
    if args.env_file.exists():
        if args.env_file.stat().st_mode & 0o077:
            raise RuntimeError('Existing private env must have mode 0600')
        print('Existing env preserved. Inspect the existing instance; do not create a second CVAT project.')
        return
    if existing or data_exists:
        raise RuntimeError('Existing CVAT containers or data found; recover original configuration and adopt deliberately')
    gateway = json.loads(run('docker', 'network', 'inspect', 'bridge'))[0]['IPAM']['Config'][0]['Gateway']
    if gateway != '172.17.0.1' or not ipaddress.ip_address(gateway).is_private:
        raise RuntimeError('Docker bridge differs from committed EndpointSlice; update both through a reviewed PR')
    # Reject the known ingress conflict; do not modify existing ports or infrastructure.
    sockets = run('ss', '-H', '-ltn')
    if any(line.split()[3].endswith(':18080') for line in sockets.splitlines() if len(line.split()) >= 4):
        raise RuntimeError('Port 18080 is already in use; inspect its owner')
    args.env_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.env_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as file:
        file.write('CVAT_HOST=cvat.williamtrinh.online\nCVAT_BIND_IP=172.17.0.1\n')
        file.write('CVAT_TRUSTED_PROXY_CIDRS=10.42.0.0/16,172.16.0.0/12\n')
        file.write('CVAT_POSTGRES_PASSWORD=' + secrets.token_hex(32) + '\n')
        file.write('CLICKHOUSE_PASSWORD=' + secrets.token_hex(32) + '\n')
        file.write('CVAT_GRAFANA_ADMIN_PASSWORD=' + secrets.token_hex(32) + '\n')
    print('Private env created mode 0600; copy securely off VPS before first start. No credentials printed.')
    print('Verify K3s pod CIDRs match trusted proxies; the Docker range covers the compose network gateway that docker-proxy shows to the router.')
    print('Do not bind CVAT to 0.0.0.0 or ports 80/443.')


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as error:
        print('CVAT preparation stopped: ' + str(error))
        raise SystemExit(1) from None
    except Exception as error:
        print('CVAT preparation stopped: ' + type(error).__name__ + '; inspect inventory/configuration, credentials omitted')
        raise SystemExit(1) from None
