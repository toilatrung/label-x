#!/usr/bin/env python3
"""Provision labelx secrets without putting credentials in Git or command arguments."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def kubectl(*args, document=None, check=True):
    result = subprocess.run(["kubectl", *args], input=None if document is None else json.dumps(document),
        capture_output=True, text=True)
    if check and result.returncode:
        # Server validation errors can echo Secret contents. Never print stderr for secret writes.
        private_document = document is not None and document.get("kind") in ("Secret", "List")
        detail = "secret write rejected; credentials omitted" if private_document else result.stderr.strip()
        raise RuntimeError(f"kubectl {args[0]} failed (exit {result.returncode}): {detail}")
    return result


def secret(name, data):
    return {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": name, "namespace": "labelx",
        "annotations": {"argocd.argoproj.io/sync-options": "Prune=false,Delete=false"}},
        "type": "Opaque", "stringData": data}


def verify_images_on_vps(receipt):
    if not re.fullmatch(r"[a-f0-9]{40}", receipt.get("source_sha", "")) or receipt.get("mvp_acceptance") != "unverified":
        raise RuntimeError("A real source/CI/publish digest receipt is required before activation")
    if not str(receipt.get("ci_run_id", "")).isdigit() or not str(receipt.get("publish_run_id", "")).isdigit():
        raise RuntimeError("Verified CI and publish run IDs are required")
    for component, uid, command in (("backend", 10001, ["python", "-c", "print('image-pull-ok')"]),
                                    ("frontend", 1000, ["node", "-e", "console.log('image-pull-ok')"])):
        entry = receipt.get("images", {}).get(component, {})
        repository = "ghcr.io/toilatrung/labelx-" + component
        digest = entry.get("digest", "")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest) or entry.get("reference") != repository + "@" + digest:
            raise RuntimeError("Both actual GHCR digests are required; tags/placeholders are not activation inputs")
        name = "labelx-pull-check-" + component + "-" + secrets.token_hex(4)
        pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "namespace": "labelx"},
            "spec": {"restartPolicy": "Never", "activeDeadlineSeconds": 300,
                "automountServiceAccountToken": False, "imagePullSecrets": [{"name": "labelx-ghcr"}],
                "securityContext": {"runAsNonRoot": True, "runAsUser": uid,
                    "seccompProfile": {"type": "RuntimeDefault"}},
                "containers": [{"name": "pull-check", "image": entry["reference"], "imagePullPolicy": "Always",
                    "command": command, "securityContext": {"allowPrivilegeEscalation": False,
                        "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}},
                    "resources": {"requests": {"cpu": "50m", "memory": "64Mi"}, "limits": {"memory": "256Mi"}}}]}}
        kubectl("apply", "-f", "-", document=pod)
        try:
            result = kubectl("wait", "-n", "labelx", "pod/" + name,
                "--for=jsonpath={.status.phase}=Succeeded", "--timeout=300s", check=False)
            if result.returncode:
                pod_status = json.loads(kubectl("get", "pod", name, "-n", "labelx", "-o", "json").stdout)["status"]
                states = [state.get("state", {}).get("waiting", {}).get("reason", "")
                    for state in pod_status.get("containerStatuses", [])]
                reason = ",".join(filter(None, states)) or pod_status.get("reason", "pull or container check failed")
                raise RuntimeError(f"VPS image preflight failed for {entry['reference']}: {reason}")
            print(f"PASS VPS pulled and executed {entry['reference']}")
        finally:
            kubectl("delete", "pod", name, "-n", "labelx", "--wait=false")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Private JSON file outside Git")
    parser.add_argument("--recovery-file", type=Path, required=True, help="Private off-VPS recovery file; keep offline")
    parser.add_argument("--context", required=True, help="Expected kubectl context; avoids writing to another cluster")
    parser.add_argument("--activate", action="store_true", help="Apply the single auto-syncing Application after receipt verification")
    args = parser.parse_args()
    if kubectl("config", "current-context").stdout.strip() != args.context:
        raise RuntimeError("Current kubectl context does not match --context")
    if args.config.stat().st_mode & 0o077:
        raise RuntimeError("Private config must be mode 0600")
    config = json.loads(args.config.read_text())
    required = ["OBJECT_STORAGE_ENDPOINT_URL", "OBJECT_STORAGE_ACCESS_KEY", "OBJECT_STORAGE_SECRET_KEY",
        "OBJECT_STORAGE_BUCKET_SNAPSHOTS", "OBJECT_STORAGE_BUCKET_EVIDENCE", "OBJECT_STORAGE_BUCKET_REPORTS",
        "BACKUP_S3_ENDPOINT_URL", "BACKUP_S3_ACCESS_KEY", "BACKUP_S3_SECRET_KEY", "BACKUP_S3_BUCKET"]
    if any(not config.get(key) for key in required):
        raise RuntimeError("S3 application and off-VPS backup configuration are required")
    if not all(config[key].startswith("https://") for key in ("OBJECT_STORAGE_ENDPOINT_URL", "BACKUP_S3_ENDPOINT_URL")):
        raise RuntimeError("Use trusted HTTPS endpoints for external application and backup S3")
    for crd in ("applications.argoproj.io", "issuers.cert-manager.io", "middlewares.traefik.io"):
        kubectl("get", "crd", crd)
    kubectl("get", "ingressclass", "traefik")
    kubectl("apply", "-f", str(ROOT / "infrastructure/k8s/labelx/namespace.yaml"))
    kubectl("apply", "-f", str(ROOT / "infrastructure/k8s/storage-class.yaml"))
    # A namespace with partial secrets is not a fresh installation. Never regenerate its passwords.
    names = ("labelx-runtime", "labelx-migration", "labelx-postgres", "labelx-redis", "labelx-backup")
    old = {}
    for name in names:
        result = kubectl("get", "secret", name, "-n", "labelx", "-o", "json", "--ignore-not-found")
        if result.stdout.strip():
            old[name] = {key: base64.b64decode(value).decode() for key, value in json.loads(result.stdout)["data"].items()}
    if old and len(old) != len(names):
        raise RuntimeError("Partial existing secret set; recover the original secrets before continuing")
    if old:
        documents = [secret(name, data) for name, data in old.items()]
        print("Existing DB/Redis/Django/encryption secrets preserved; rotate separately")
    else:
        if kubectl("get", "pvc", "labelx-postgres", "-n", "labelx", "--ignore-not-found", "-o", "name").stdout.strip():
            raise RuntimeError("Existing database PVC without credentials; recover secrets instead of generating passwords")
        django_key, owner_password, runtime_password, redis_password = [secrets.token_hex(32) for _ in range(4)]
        owner_url = f"postgres://labelx_owner:{owner_password}@labelx-postgres:5432/labelx"
        runtime_url = f"postgres://labelx_runtime:{runtime_password}@labelx-postgres:5432/labelx"
        runtime = {key: json.dumps(value) if isinstance(value, dict) else str(value)
            for key, value in config.items() if key.startswith(("OBJECT_STORAGE_", "CVAT_", "GPU_WORKER_", "DETECTOR_")) or key in ("VLM_API_KEY", "GEMINI_API_KEY", "DASHSCOPE_API_KEY")}
        runtime.setdefault("OBJECT_STORAGE_BUCKET", runtime["OBJECT_STORAGE_BUCKET_EVIDENCE"])
        runtime.update({"DJANGO_SECRET_KEY": django_key, "DATABASE_URL": runtime_url,
            "CELERY_BROKER_URL": f"redis://:{redis_password}@labelx-redis:6379/0",
            "CELERY_RESULT_BACKEND": f"redis://:{redis_password}@labelx-redis:6379/1"})
        backup = {key: str(value) for key, value in config.items() if key.startswith("BACKUP_S3_")}
        backup.update({"BACKUP_ENCRYPTION_KEY": secrets.token_hex(32), "PGHOST": "labelx-postgres",
            "PGDATABASE": "labelx", "PGUSER": "labelx_owner", "PGPASSWORD": owner_password})
        documents = [secret("labelx-runtime", runtime), secret("labelx-migration", {
            "DJANGO_SECRET_KEY": django_key, "DATABASE_URL": owner_url, "RUNTIME_DB_PASSWORD": runtime_password}),
            secret("labelx-postgres", {"POSTGRES_DB": "labelx", "POSTGRES_USER": "labelx_owner", "POSTGRES_PASSWORD": owner_password}),
            secret("labelx-redis", {"REDIS_PASSWORD": redis_password}), secret("labelx-backup", backup)]
    # Write recovery material before applying any credentials. Refuse to overwrite an existing recovery file.
    args.recovery_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.recovery_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as recovery:
        json.dump({"apiVersion": "v1", "kind": "List", "items": documents}, recovery, indent=2)
    for document in documents:
        kubectl("apply", "-f", "-", document=document)
    registry = {"auths": {}}
    if config.get("GHCR_DOCKERCONFIG_FILE"):
        registry_path = Path(config["GHCR_DOCKERCONFIG_FILE"])
        if registry_path.stat().st_mode & 0o077:
            raise RuntimeError("GHCR authfile must be mode 0600 and contain read:packages credentials only")
        registry = json.loads(registry_path.read_text())
    document = secret("labelx-ghcr", {".dockerconfigjson": json.dumps(registry)})
    document["type"] = "kubernetes.io/dockerconfigjson"
    kubectl("apply", "-f", "-", document=document)
    print("PASS labelx secrets provisioned; retain the recovery file offline, outside the VPS")
    if args.activate:
        receipt = json.loads((ROOT / "infrastructure/k8s/labelx/release.json").read_text())
        verify_images_on_vps(receipt)
        print(f"Activating labelx/main at source {receipt['source_sha']}; MVP acceptance remains UNVERIFIED")
        kubectl("apply", "-f", str(ROOT / "infrastructure/argocd/project.yaml"))
        kubectl("apply", "-f", str(ROOT / "infrastructure/argocd/application.yaml"))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Bootstrap stopped: {type(error).__name__}: {error}")
        raise SystemExit(1) from None
