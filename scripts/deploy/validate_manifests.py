#!/usr/bin/env python3
"""Validate the rendered deployment, image receipt and persistent-data safeguards."""
import argparse
import json
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[2]


def pod_spec(item):
    if item["kind"] in ("Deployment", "StatefulSet", "Job"):
        return item["spec"]["template"]["spec"]
    if item["kind"] == "CronJob":
        return item["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    return None


def validate(items, receipt, application, storage_class):
    assert application["metadata"]["name"] == "labelx"
    assert application["spec"]["source"]["targetRevision"] == "main"
    assert application["spec"]["source"]["path"] == "infrastructure/k8s/labelx"
    assert application["spec"]["destination"]["namespace"] == "labelx"
    assert application["spec"]["syncPolicy"]["automated"]["prune"] is False
    assert application["spec"]["syncPolicy"]["automated"]["selfHeal"] is True
    assert not application["metadata"].get("finalizers"), "Application must not cascade-delete persistent data"
    assert storage_class["reclaimPolicy"] == "Retain"
    assert storage_class["volumeBindingMode"] == "WaitForFirstConsumer"
    assert receipt["deployment_policy"] == "CR-120" and receipt["mvp_acceptance"] == "unverified"
    assert re.fullmatch(r"[a-f0-9]{40}", receipt["source_sha"])
    expected = {}
    for component in ("frontend", "backend"):
        entry = receipt["images"][component]
        assert entry["repository"] == "ghcr.io/toilatrung/labelx-" + component
        assert entry["tag"] == "sha-" + receipt["source_sha"]
        assert re.fullmatch(r"sha256:[a-f0-9]{64}", entry["digest"])
        assert entry["reference"] == entry["repository"] + "@" + entry["digest"]
        expected[component] = entry["reference"]
    annotations = application["spec"]["source"]["kustomize"]
    assert annotations["commonAnnotationsEnvsubst"] is True
    assert annotations["commonAnnotations"]["labelx.io/gitops-revision"] == "${ARGOCD_APP_REVISION}"
    identities, workloads, pvcs, consumers = set(), {}, {}, {}
    for item in items:
        kind, name = item["kind"], item["metadata"]["name"]
        key = (kind, name)
        assert key not in identities, f"Duplicate resource {key}"
        identities.add(key)
        assert kind != "Secret", "Secret examples must stay outside Kustomize resources"
        assert kind == "Namespace" or item["metadata"]["namespace"] == "labelx"
        wave = int(item["metadata"].get("annotations", {}).get("argocd.argoproj.io/sync-wave", "0"))
        if kind == "PersistentVolumeClaim":
            options = item["metadata"]["annotations"]["argocd.argoproj.io/sync-options"]
            assert "Prune=false" in options and "Delete=false" in options
            pvcs[name] = wave
        pod = pod_spec(item)
        if not pod:
            continue
        workloads[name] = item
        assert pod["automountServiceAccountToken"] is False
        assert pod["securityContext"]["runAsNonRoot"] is True
        for container in pod["containers"]:
            image = container["image"]
            assert re.fullmatch(r"[^@\s]+@sha256:[a-f0-9]{64}", image), f"Unpinned image in {name}: {image}"
            if "ghcr.io/toilatrung/labelx-" in image:
                assert image in expected.values(), f"Image not in the verified receipt: {name}"
            assert container["securityContext"]["allowPrivilegeEscalation"] is False
            assert container["securityContext"]["readOnlyRootFilesystem"] is True
            assert "ALL" in container["securityContext"]["capabilities"]["drop"]
            assert container["resources"]["requests"]["memory"]
            assert container["resources"]["limits"]["memory"]
            assert container["resources"]["limits"]["cpu"]
            secrets_used = {value["secretRef"]["name"] for value in container.get("envFrom", []) if "secretRef" in value}
            if kind == "Deployment":
                assert not (secrets_used & {"labelx-postgres", "labelx-migration", "labelx-backup"})
                assert container.get("readinessProbe"), f"Readiness probe missing: {name}"
        for volume in pod.get("volumes", []):
            if "persistentVolumeClaim" in volume:
                consumers.setdefault(volume["persistentVolumeClaim"]["claimName"], []).append(wave)
    for claim, wave in pvcs.items():
        assert claim in consumers
        assert wave == min(consumers[claim]), f"WaitForFirstConsumer PVC must share its first consumer wave: {claim}"
    assert workloads["labelx-beat"]["spec"]["replicas"] == 1
    assert workloads["labelx-beat"]["spec"]["strategy"]["type"] == "Recreate"
    for name, wave in (("labelx-before-migrate-backup", -10), ("labelx-migrate", -5)):
        annotations = workloads[name]["metadata"]["annotations"]
        assert annotations["argocd.argoproj.io/hook"] == "Sync"
        assert int(annotations["argocd.argoproj.io/sync-wave"]) == wave
    preflight = workloads["labelx-release-preflight"]
    assert preflight["metadata"]["annotations"]["argocd.argoproj.io/hook"] == "PreSync"
    assert preflight["spec"]["template"]["spec"]["containers"][0]["command"][-1] == (ROOT / "infrastructure/k8s/labelx/ops/preflight.py").read_text()
    assert workloads["labelx-smoke"]["metadata"]["annotations"]["argocd.argoproj.io/hook"] == "PostSync"
    assert workloads["labelx-storage-init"]["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"] == "-15"
    assert isinstance(workloads["labelx-daily-backup"]["spec"]["suspend"], bool), "Explicit schedule state required"
    # Scope the storage to the application project; CVAT stays upstream Compose behind a private endpoint.
    assert ("StatefulSet", "labelx-s3") in identities
    assert ("EndpointSlice", "cvat-host") in identities
    return len(items)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rendered", type=Path, help="Output of kubectl kustomize infrastructure/k8s/labelx")
    args = parser.parse_args()
    count = validate(list(yaml.safe_load_all(args.rendered.read_text())),
        json.loads((ROOT / "infrastructure/k8s/labelx/release.json").read_text()),
        yaml.safe_load((ROOT / "infrastructure/argocd/application.yaml").read_text()),
        yaml.safe_load((ROOT / "infrastructure/k8s/storage-class.yaml").read_text()))
    print(f"PASS {count} deployment resources, real digest receipt, persistence and migration order")


if __name__ == "__main__":
    main()
