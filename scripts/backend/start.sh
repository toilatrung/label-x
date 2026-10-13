#!/usr/bin/env bash
# Khởi động backend LabelX (Django API ở :8000).
# Dùng: scripts/backend/start.sh [--no-infra] [--no-migrate] [--worker] [--port N]
#   --no-infra    bỏ qua bật PostgreSQL/Redis/SeaweedFS (đã chạy sẵn)
#   --no-migrate  bỏ qua migrate
#   --worker      chạy thêm Celery worker nền cùng API
#   --port N      cổng API (mặc định 8000)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$ROOT/src/backend"
COMPOSE=(docker compose -f "$ROOT/infrastructure/docker-compose.dev.yml")
UV="$(command -v uv 2>/dev/null || echo "$HOME/.local/bin/uv")"

# WSL: giữ venv Linux tách khỏi .venv tạo trên Windows (giống Makefile).
if [[ -n "${WSL_DISTRO_NAME:-}" ]]; then
  export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-wsl}"
fi

infra=1 migrate=1 worker=0 port=8000
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-infra) infra=0 ;;
    --no-migrate) migrate=0 ;;
    --worker) worker=1 ;;
    --port) port="${2:?thiếu giá trị cho --port}"; shift ;;
    -h|--help) sed -n '2,7p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Tuỳ chọn không hợp lệ: $1" >&2; exit 2 ;;
  esac
  shift
done

[[ -x "$UV" ]] || { echo "Không tìm thấy uv. Chạy: make setup" >&2; exit 1; }
[[ -f "$BACKEND/.env" ]] || { echo "Thiếu $BACKEND/.env. Chạy: make env" >&2; exit 1; }

if (( infra )); then
  "${COMPOSE[@]}" up -d --wait postgres redis seaweedfs
  "${COMPOSE[@]}" run --rm seaweedfs-init
fi

cd "$BACKEND"
if (( migrate )); then
  "$UV" run --frozen python manage.py migrate
fi

if (( worker )); then
  "$UV" run --frozen celery -A config worker -l info &
  worker_pid=$!
  trap 'kill "$worker_pid" 2>/dev/null || true' EXIT
fi

"$UV" run --frozen python manage.py runserver "0.0.0.0:$port"
