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


BUCKETS = ("labelx-snapshots", "labelx-evidence", "labelx-reports")
CORE = ("labelx-runtime", "labelx-migration", "labelx-postgres", "labelx-redis", "labelx-backup")
S3_ENDPOINT = "https://s3.williamtrinh.online"


def dependency_config(config):
    mode = config.get("BACKUP_MODE", "local")
    if mode not in ("local", "offsite"):
        raise RuntimeError("BACKUP_MODE must be local or offsite")
    backup = {key: str(value) for key, value in config.items() if key.startswith("BACKUP_S3_") and value}
    if mode == "offsite":
        required = ("ENDPOINT_URL", "ACCESS_KEY", "SECRET_KEY", "BUCKET")
        if any(not backup.get("BACKUP_S3_" + key) for key in required):
            raise RuntimeError("Offsite mode requires a real backup endpoint, credentials and bucket")
        if not backup["BACKUP_S3_ENDPOINT_URL"].startswith("https://"):
            raise RuntimeError("Offsite backup requires trusted HTTPS")
        if backup["BACKUP_S3_ENDPOINT_URL"].rstrip("/") == S3_ENDPOINT:
            raise RuntimeError("Application storage on this VPS cannot be the offsite backup")
    url, token = config.get("CVAT_BASE_URL", ""), config.get("CVAT_SERVICE_TOKEN", "")
    if bool(url) != bool(token):
        raise RuntimeError("Configure both CVAT URL and read-only PAT, or leave both empty")
    if url and not url.startswith("https://"):
        raise RuntimeError("CVAT requires trusted HTTPS")
    return mode, backup


def build_documents(config, old, pvcs, update_dependencies=False):
    mode, external_backup = dependency_config(config)
    existing = {name: old[name] for name in CORE if name in old}
    if existing and len(existing) != len(CORE):
        raise RuntimeError("Partial core secrets; restore original credentials, never regenerate")
    if not existing and pvcs & {"labelx-postgres", "labelx-redis", "labelx-backups"}:
        raise RuntimeError("Persistent data without original core secrets; restore credentials")
    if "labelx-s3" in pvcs and "labelx-s3" not in old:
        raise RuntimeError("Persistent S3 data without original S3 credentials; restore credentials")
    optional = {key: json.dumps(value) if isinstance(value, dict) else str(value)
        for key, value in config.items() if key.startswith(("CVAT_", "GPU_WORKER_", "DETECTOR_"))
        or key in ("VLM_API_KEY", "GEMINI_API_KEY", "DASHSCOPE_API_KEY")}
    if existing:
        data = {name: dict(values) for name, values in existing.items()}
        if data["labelx-runtime"].get("OBJECT_STORAGE_ENDPOINT_URL", "").rstrip("/") != S3_ENDPOINT:
            raise RuntimeError("Existing external storage must be migrated explicitly; credentials preserved")
        if "labelx-s3" not in old:
            raise RuntimeError("Existing application storage credentials require original S3 secret recovery")
        if update_dependencies:
            data["labelx-runtime"].update(optional)
            backup = data["labelx-backup"]
            for key in list(backup):
                if key.startswith("BACKUP_S3_"):
                    del backup[key]
            backup.update(external_backup)
            backup["BACKUP_MODE"] = mode
    else:
        django_key, owner_password, runtime_password, redis_password = [secrets.token_hex(32) for _ in range(4)]
        owner_url = f"postgres://labelx_owner:{owner_password}@labelx-postgres:5432/labelx"
        data = {"labelx-runtime": {**optional, "DJANGO_SECRET_KEY": django_key,
            "DATABASE_URL": f"postgres://labelx_runtime:{runtime_password}@labelx-postgres:5432/labelx",
            "CELERY_BROKER_URL": f"redis://:{redis_password}@labelx-redis:6379/0",
            "CELERY_RESULT_BACKEND": f"redis://:{redis_password}@labelx-redis:6379/1"},
            "labelx-migration": {"DJANGO_SECRET_KEY": django_key, "DATABASE_URL": owner_url, "RUNTIME_DB_PASSWORD": runtime_password},
            "labelx-postgres": {"POSTGRES_DB": "labelx", "POSTGRES_USER": "labelx_owner", "POSTGRES_PASSWORD": owner_password},
            "labelx-redis": {"REDIS_PASSWORD": redis_password},
            "labelx-backup": {**external_backup, "BACKUP_MODE": mode, "BACKUP_ENCRYPTION_KEY": secrets.token_hex(32),
                "PGHOST": "labelx-postgres", "PGDATABASE": "labelx", "PGUSER": "labelx_owner", "PGPASSWORD": owner_password}}
    if "labelx-s3" in old:
        storage = dict(old["labelx-s3"])
        identities = json.loads(storage["s3.json"])["identities"]
        app_identity = next(identity for identity in identities if identity["name"] == "labelx-app")
        app = app_identity["credentials"][0]
    else:
        admin_key, admin_secret, app_key, app_secret = [secrets.token_hex(24) for _ in range(4)]
        app = {"accessKey": app_key, "secretKey": app_secret}
        identities = [{"name": "labelx-admin", "credentials": [{"accessKey": admin_key, "secretKey": admin_secret}], "actions": ["Admin", "Read", "Write", "List", "Tagging"]},
            {"name": "labelx-app", "credentials": [app], "actions": [action + ":" + bucket
                for bucket in BUCKETS for action in ("Read", "Write", "List", "Tagging")]}]
        storage = {"s3.json": json.dumps({"identities": identities}), "ADMIN_ACCESS_KEY": admin_key, "ADMIN_SECRET_KEY": admin_secret}
    runtime = data["labelx-runtime"]
    if existing:
        if runtime.get("OBJECT_STORAGE_ACCESS_KEY") != app["accessKey"] or runtime.get("OBJECT_STORAGE_SECRET_KEY") != app["secretKey"]:
            raise RuntimeError("Runtime/S3 credential mismatch; restore the matching original secrets")
    else:
        runtime.update({"OBJECT_STORAGE_ENDPOINT_URL": S3_ENDPOINT, "OBJECT_STORAGE_ACCESS_KEY": app["accessKey"],
            "OBJECT_STORAGE_SECRET_KEY": app["secretKey"], "OBJECT_STORAGE_REGION": "us-east-1",
            "OBJECT_STORAGE_BUCKET": BUCKETS[1], "OBJECT_STORAGE_BUCKET_SNAPSHOTS": BUCKETS[0],
            "OBJECT_STORAGE_BUCKET_EVIDENCE": BUCKETS[1], "OBJECT_STORAGE_BUCKET_REPORTS": BUCKETS[2]})
    return [secret(name, values) for name, values in data.items()] + [secret("labelx-s3", storage)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Private JSON, optional integrations only; mode 0600")
    parser.add_argument("--recovery-file", type=Path, required=True, help="New private recovery snapshot; copy securely off VPS")
    parser.add_argument("--context", required=True)
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--update-dependencies", action="store_true", help="Update CVAT/GPU/offsite settings only; preserve encryption/DB/storage keys")
    args = parser.parse_args()
    if kubectl("config", "current-context").stdout.strip() != args.context:
        raise RuntimeError("kubectl context mismatch")
    if args.config.stat().st_mode & 0o077:
        raise RuntimeError("Private config must be mode 0600")
    config = json.loads(args.config.read_text())
    dependency_config(config)
    for crd in ("applications.argoproj.io", "issuers.cert-manager.io", "middlewares.traefik.io"):
        kubectl("get", "crd", crd)
    kubectl("get", "ingressclass", "traefik")
    old = {}
    for name in (*CORE, "labelx-s3"):
        result = kubectl("get", "secret", name, "-n", "labelx", "-o", "json", "--ignore-not-found", check=False)
        if result.returncode and "not found" not in result.stderr.lower():
            raise RuntimeError("Cannot inspect existing secrets; refusing initialization")
        if result.stdout.strip():
            old[name] = {key: base64.b64decode(value).decode() for key, value in json.loads(result.stdout)["data"].items()}
    result = kubectl("get", "pvc", "-n", "labelx", "-o", "json", check=False)
    if result.returncode and "not found" not in result.stderr.lower():
        raise RuntimeError("Cannot inspect existing PVCs; refusing initialization")
    pvcs = {item["metadata"]["name"] for item in json.loads(result.stdout or '{"items":[]}')["items"]}
    documents = build_documents(config, old, pvcs, args.update_dependencies)
    args.recovery_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.recovery_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as recovery:
        json.dump({"apiVersion": "v1", "kind": "List", "items": documents}, recovery, indent=2)
    kubectl("apply", "-f", str(ROOT / "infrastructure/k8s/labelx/namespace.yaml"))
    kubectl("apply", "-f", str(ROOT / "infrastructure/k8s/storage-class.yaml"))
    for document in documents:
        kubectl("apply", "-f", "-", document=document)
    # Public GHCR packages require no stored registry credential.
    registry = secret("labelx-ghcr", {".dockerconfigjson": '{"auths":{}}'})
    registry["type"] = "kubernetes.io/dockerconfigjson"
    kubectl("apply", "-f", "-", document=registry)
    backup = next(item["stringData"] for item in documents if item["metadata"]["name"] == "labelx-backup")
    print("PASS secrets prepared and original keys preserved; copy recovery file securely off VPS")
    print("Backup mode: " + backup.get("BACKUP_MODE", "offsite") + "; disaster recovery remains UNVERIFIED")
    print("Repository default daily backup CronJob is suspended; enable through a reviewed config PR after offsite verification")
    if args.activate:
        verify_images_on_vps(json.loads((ROOT / "infrastructure/k8s/labelx/release.json").read_text()))
        kubectl("apply", "-f", str(ROOT / "infrastructure/argocd/project.yaml"))
        kubectl("apply", "-f", str(ROOT / "infrastructure/argocd/application.yaml"))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"Bootstrap stopped: {error}")
        raise SystemExit(1) from None
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Bootstrap stopped: {type(error).__name__}: credentials omitted")
        raise SystemExit(1) from None
