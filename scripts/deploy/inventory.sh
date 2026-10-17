#!/usr/bin/env bash
# Run on VPS Ubuntu. Read only; never display Secret contents or Docker env/config.
set -euo pipefail
[[ "$(kubectl config current-context)" == default ]] || { echo 'Wrong kubectl context'; exit 1; }
uname -m
free -h
df -h / /var/lib/rancher/k3s
kubectl get nodes -o wide
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{" podCIDR="}{.spec.podCIDR}{"\n"}{end}'
kubectl get pods,deploy,statefulset,pvc,ingress -A
kubectl get pv
kubectl -n argocd get applications,appprojects
kubectl -n argocd get application labelx -o jsonpath='{.spec.source.repoURL}{" "}{.spec.source.targetRevision}{" "}{.spec.source.path}{"\n"}' 2>/dev/null || true
if command -v docker >/dev/null; then
  docker compose version
  docker ps -a --format '{{.Names}} {{.Image}} {{.Ports}}'
  docker volume ls
fi
ss -ltn | awk 'NR==1 || /:80 |:443 |:18080 /'
for host in label-x.williamtrinh.online cvat.williamtrinh.online s3.williamtrinh.online; do
  getent ahostsv4 "$host" || true
  curl --silent --show-error --head --connect-timeout 5 --max-time 15 "https://$host" || true
done
