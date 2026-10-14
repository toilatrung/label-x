#!/usr/bin/env bash
# Chạy toàn bộ LabelX dev trên WSL/Linux: hạ tầng Docker (PostgreSQL, Redis, SeaweedFS), Django API,
# Celery worker + beat và Next.js. Không bật CVAT (dùng `make cvat-up` nếu cần).
#
#   scripts/dev-stack.sh start [--poll]     bật hạ tầng, migrate, chạy BE + worker + beat + FE ở nền
#   scripts/dev-stack.sh stop [--keep-infra] dừng tiến trình và hạ tầng (giữ dữ liệu)
#   scripts/dev-stack.sh refresh [fe|be|all] nạp lại code: mặc định fe (xoá cache .next, chạy lại Next)
#   scripts/dev-stack.sh status             trạng thái tiến trình và container
#   scripts/dev-stack.sh logs [be|worker|beat|fe]  theo dõi log (mặc định tất cả)
#
# Mã ở /mnt/<ổ> (sửa từ Windows) không phát sinh sự kiện inotify trong WSL, nên Next (Turbopack) không
# tự thấy thay đổi: dùng `refresh`, hoặc `start --poll` để chạy Next bằng webpack + polling (chậm hơn
# nhưng tự reload). Django runserver tự reload (StatReloader); Celery không, `refresh be` chạy lại.
# refresh cũng cài lại dependency khi package-lock.json / uv.lock đổi và chạy migrate khi cần.
# Log và PID ở .cache/dev-stack/. Cổng: API 127.0.0.1:8000, UI http://127.0.0.1:3000.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/src/backend"
FRONTEND="$ROOT/src/frontend"
RUN_DIR="$ROOT/.cache/dev-stack"
COMPOSE=(docker compose -f "$ROOT/infrastructure/docker-compose.dev.yml")
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
API_PORT="${LABELX_API_PORT:-8000}"
FE_PORT="${LABELX_FE_PORT:-3000}"
# Giống init-develop-environment.mk: venv Linux tách khỏi .venv do Windows tạo.
if [ -n "${WSL_DISTRO_NAME:-}" ]; then export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-wsl}"; fi


die() { echo "Lỗi: $*" >&2; exit 1; }
say() { echo ">> $*"; }
usage() { awk 'NR==1{next} /^[^#]/{exit} {sub(/^# ?/,""); print}' "$0"; }

pid_of() { cat "$RUN_DIR/$1.pid" 2>/dev/null || true; }
alive() { local p; p="$(pid_of "$1")"; [ -n "$p" ] && kill -0 "$p" 2>/dev/null; }
port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

wait_http() { # URL giây tên
  local i
  for ((i = 0; i < $2; i++)); do
    curl -s -o /dev/null --max-time 2 "$1" && return 0
    alive "$3" || return 1
    sleep 1
  done
  return 1
}

# launch tên thư_mục lệnh...: chạy trong nhóm tiến trình riêng (setsid) để stop dừng được cả cây con.
launch() {
  local name="$1" dir="$2"; shift 2
  if alive "$name"; then say "$name đang chạy (pid $(pid_of "$name"))"; return 0; fi
  : >"$RUN_DIR/$name.log"
  (cd "$dir" && exec setsid "$@" >>"$RUN_DIR/$name.log" 2>&1 </dev/null) &
  echo $! >"$RUN_DIR/$name.pid"
  say "$name: pid $!, log .cache/dev-stack/$name.log"
}

halt() {
  local name="$1" p i
  p="$(pid_of "$name")"
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
    kill -TERM -- "-$p" 2>/dev/null || kill -TERM "$p" 2>/dev/null || true
    for ((i = 0; i < 20; i++)); do kill -0 "$p" 2>/dev/null || break; sleep 0.5; done
    kill -KILL -- "-$p" 2>/dev/null || true
    say "đã dừng $name"
  fi
  rm -f "$RUN_DIR/$name.pid"
}

# ---------------------------------------------------------------- dependency

# uv sync không làm gì khi venv đã khớp uv.lock (dưới 1 giây).
deps_backend() { (cd "$BACKEND" && "$UV" sync --frozen -q); }

# npm ci mất vài phút trên /mnt: chỉ chạy khi package-lock.json mới hơn bản npm ghi lúc cài.
deps_frontend() {
  if [ ! -x "$FRONTEND/node_modules/.bin/next" ] || [ "$FRONTEND/package-lock.json" -nt "$FRONTEND/node_modules/.package-lock.json" ]; then
    say "npm ci (frontend)"
    (cd "$FRONTEND" && npm ci --no-audit --no-fund)
  fi
}

migrate() {
  if ! (cd "$BACKEND" && "$UV" run --frozen python manage.py migrate --check >/dev/null 2>&1); then
    say "migrate"
    (cd "$BACKEND" && "$UV" run --frozen python manage.py migrate)
  fi
}

# ---------------------------------------------------------------- tiến trình

start_infra() {
  command -v docker >/dev/null || die "Cần Docker (Docker Desktop bật WSL integration hoặc Docker Engine)."
  say "hạ tầng: postgres, redis, seaweedfs"
  "${COMPOSE[@]}" up -d --wait postgres redis seaweedfs
  "${COMPOSE[@]}" run --rm seaweedfs-init >/dev/null
}

start_be() {
  if ! alive be && port_busy "$API_PORT"; then die "Cổng $API_PORT đang bị tiến trình khác dùng."; fi
  launch be "$BACKEND" "$UV" run --frozen python manage.py runserver "127.0.0.1:$API_PORT"
  launch worker "$BACKEND" "$UV" run --frozen celery -A config worker -l info
  launch beat "$BACKEND" "$UV" run --frozen celery -A config beat -l info
  wait_http "http://127.0.0.1:$API_PORT/api/schema/" 90 be || die "API không lên, xem .cache/dev-stack/be.log"
}

start_fe() {
  if ! alive fe && port_busy "$FE_PORT"; then die "Cổng $FE_PORT đang bị tiến trình khác dùng."; fi
  local poll=0
  [ -f "$RUN_DIR/fe.poll" ] && poll=1
  if [ "$poll" -eq 1 ]; then
    launch fe "$FRONTEND" env WATCHPACK_POLLING=true npx next dev --webpack -H 127.0.0.1 -p "$FE_PORT"
  else
    launch fe "$FRONTEND" npx next dev -H 127.0.0.1 -p "$FE_PORT"
  fi
  wait_http "http://127.0.0.1:$FE_PORT/login" 180 fe || die "Next không lên, xem .cache/dev-stack/fe.log"
}

stop_be() { halt beat; halt worker; halt be; }

# ---------------------------------------------------------------- lệnh

cmd_start() {
  rm -f "$RUN_DIR/fe.poll"
  [ "${1:-}" = "--poll" ] && touch "$RUN_DIR/fe.poll"
  [ -f "$BACKEND/.env" ] && [ -f "$FRONTEND/.env.local" ] || node "$ROOT/scripts/development/environment.cjs" env
  start_infra
  deps_backend
  deps_frontend
  migrate
  start_be
  start_fe
  echo
  say "LabelX: http://127.0.0.1:$FE_PORT  (API http://127.0.0.1:$API_PORT/api/)"
}

cmd_stop() {
  halt fe
  stop_be
  if [ "${1:-}" != "--keep-infra" ]; then
    say "tắt hạ tầng (giữ dữ liệu)"
    "${COMPOSE[@]}" down
  fi
}

cmd_refresh() {
  local target="${1:-fe}"
  case "$target" in fe|be|all) ;; *) die "refresh nhận fe|be|all" ;; esac
  if [ "$target" != fe ]; then
    stop_be
    deps_backend
    migrate
    start_be
  fi
  if [ "$target" != be ]; then
    halt fe
    deps_frontend
    # Cache Turbopack/webpack giữ module cũ khi watcher không thấy thay đổi trên /mnt.
    rm -rf "$FRONTEND/.next/dev" "$FRONTEND/.next/cache"
    start_fe
  fi
  say "đã refresh $target"
}

cmd_status() {
  local name p
  for name in be worker beat fe; do
    p="$(pid_of "$name")"
    if alive "$name"; then printf '  %-7s chạy   (pid %s)\n' "$name" "$p"; else printf '  %-7s dừng\n' "$name"; fi
  done
  [ -f "$RUN_DIR/fe.poll" ] && echo "  (fe: webpack + polling)"
  "${COMPOSE[@]}" ps --format 'table {{.Service}}\t{{.Status}}' 2>/dev/null || true
}

cmd_logs() {
  local names=("$@")
  [ ${#names[@]} -gt 0 ] || names=(be worker beat fe)
  local files=() n
  for n in "${names[@]}"; do files+=("$RUN_DIR/$n.log"); done
  exec tail -n 50 -F "${files[@]}"
}

mkdir -p "$RUN_DIR"
cmd="${1:-}"
[ $# -gt 0 ] && shift
case "$cmd" in
  start) cmd_start "$@" ;;
  stop) cmd_stop "$@" ;;
  refresh) cmd_refresh "$@" ;;
  status) cmd_status ;;
  logs) cmd_logs "$@" ;;
  -h|--help|help|"") usage ;;
  *) usage >&2; exit 2 ;;
esac
