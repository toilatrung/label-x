#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/infrastructure/cvat/version.conf"

CHECKOUT="$ROOT/.cache/cvat/$CVAT_VERSION"
COMPOSE_FILE="$CHECKOUT/docker-compose.yml"

usage() {
  echo "Usage: $0 {up|down|logs|ps|create-superuser}"
}

ensure_checkout() {
  if [[ ! -d "$CHECKOUT/.git" ]]; then
    mkdir -p "$(dirname "$CHECKOUT")"
    git clone --depth 1 --branch "$CVAT_VERSION" \
      https://github.com/cvat-ai/cvat.git "$CHECKOUT"
  fi

  local actual
  actual="$(git -C "$CHECKOUT" describe --tags --exact-match 2>/dev/null || true)"
  if [[ "$actual" != "$CVAT_VERSION" ]]; then
    echo "CVAT cache mismatch: expected $CVAT_VERSION, got ${actual:-unknown}." >&2
    echo "Move $CHECKOUT aside and retry; the script will not delete it." >&2
    exit 1
  fi
}

compose() {
  CVAT_VERSION="$CVAT_VERSION" CVAT_HOST="$CVAT_HOST" CVAT_PORT="$CVAT_PORT" \
    docker compose -f "$COMPOSE_FILE" "$@"
}

command="${1:-}"
case "$command" in
  up)
    ensure_checkout
    compose up -d
    echo "CVAT $CVAT_VERSION is starting at http://$CVAT_HOST:$CVAT_PORT"
    ;;
  down)
    ensure_checkout
    compose down
    ;;
  logs)
    ensure_checkout
    compose logs -f
    ;;
  ps)
    ensure_checkout
    compose ps
    ;;
  create-superuser)
    ensure_checkout
    compose exec cvat_server python3 manage.py createsuperuser
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
