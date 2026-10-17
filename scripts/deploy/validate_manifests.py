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


class _ComposeLoader(yaml.SafeLoader):
    """Read Compose files that use merge tags such as !override."""


_ComposeLoader.add_multi_constructor("!", lambda loader, suffix, node: loader.construct_undefined(node)
    if False else (loader.construct_sequence(node, deep=True) if isinstance(node, yaml.SequenceNode)
                   else loader.construct_mapping(node, deep=True) if isinstance(node, yaml.MappingNode)
                   else loader.construct_scalar(node)))


def validate_cvat_profiles():
    """The reduced default CVAT stack must stay self-contained and match the capacity budget."""
    resources = json.loads((ROOT / "infrastructure/cvat/resources.json").read_text())
    budget = json.loads((ROOT / "infrastructure/vps-budget.json").read_text())
    limits, profiles = resources["memory_limits_mib"], resources["profiles"]
    members = [name for names in profiles.values() for name in names]
    assert sorted(members) == sorted(limits), "Every CVAT service must belong to exactly one profile"
    totals = {name: sum(limits[service] for service in names) for name, names in profiles.items()}
    assert totals == resources["profile_total_mib"]
    assert resources["default_total_mib"] == totals["default"] == budget["cvat_total_mib"]
    assert resources["total_mib"] == sum(limits.values()) == budget["cvat_full_total_mib"]
    assert budget["workload_peak_mib"] == (budget["labelx_total_mib"] + budget["cvat_total_mib"]
        + budget["transient_backup_mib"] + budget["capacity_job_mib"])
    compose = yaml.load((ROOT / "infrastructure/cvat/compose.vps.yaml").read_text(), Loader=_ComposeLoader)["services"]
    upstream = yaml.safe_load((ROOT / "infrastructure/cvat/upstream/docker-compose.yml").read_text())["services"]
    assert set(compose) == set(limits) == set(upstream), "Compose override and resource budget must cover the same services"
    gated = {}
    for profile, names in profiles.items():
        for name in names:
            gated[name] = None if profile == "default" else profile
    for name, service in compose.items():
        assert service.get("profiles") == ([gated[name]] if gated[name] else None), name
        if gated[name] is None:
            dependencies = service.get("depends_on") or {}
            blocked = [dep for dep in dependencies if gated.get(dep)]
            assert not blocked, f"Default service {name} must not depend on optional services: {blocked}"
    for name in ("cvat_server", *[n for n in limits if n.startswith("cvat_worker_")]):
        assert "depends_on" in compose[name], f"{name} must override upstream ClickHouse dependency"
    environment = compose["cvat_server"]["environment"]
    assert str(environment["CVAT_ANALYTICS"]).endswith(":-0}"), "Analytics must default off in the reduced stack"
    assert str(environment["DJANGO_LOG_SERVER_HOST"]).endswith(":-}"), "Vector log handler must default off"
    return len(profiles["default"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rendered", type=Path, help="Output of kubectl kustomize infrastructure/k8s/labelx")
    args = parser.parse_args()
    count = validate(list(yaml.safe_load_all(args.rendered.read_text())),
        json.loads((ROOT / "infrastructure/k8s/labelx/release.json").read_text()),
        yaml.safe_load((ROOT / "infrastructure/argocd/application.yaml").read_text()),
        yaml.safe_load((ROOT / "infrastructure/k8s/storage-class.yaml").read_text()))
    print(f"PASS {count} deployment resources, real digest receipt, persistence and migration order")
    print(f"PASS reduced CVAT default profile of {validate_cvat_profiles()} services is self-contained and matches the budget")


if __name__ == "__main__":
    main()
