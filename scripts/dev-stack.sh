#!/usr/bin/env bash
# Chạy toàn bộ LabelX dev trên WSL/Linux: hạ tầng Docker (PostgreSQL, Redis, SeaweedFS), Django API,
# Celery worker + beat và Next.js. Không bật CVAT (dùng `make cvat-up` nếu cần).
#
#   scripts/dev-stack.sh start [--poll] [--follow]   bật hạ tầng, migrate, chạy BE + worker + beat + FE ở nền
#   scripts/dev-stack.sh stop [--keep-infra]          dừng tiến trình và hạ tầng (giữ dữ liệu)
#   scripts/dev-stack.sh restart [fe|be|all]          bounce nhanh tiến trình, không xoá cache (mặc định all)
#   scripts/dev-stack.sh refresh [fe|be|all]          tự phát hiện & nạp lại phần thay đổi (mặc định auto)
#   scripts/dev-stack.sh status                       trạng thái tiến trình và container
#   scripts/dev-stack.sh logs [be|worker|beat|fe]     theo dõi log (mặc định tất cả)
#
# Mã ở /mnt/<ổ> (sửa từ Windows) không phát sinh sự kiện inotify trong WSL, nên Next (Turbopack) không
# tự thấy thay đổi: dùng `refresh`, hoặc `start --poll` để chạy Next bằng webpack + polling (chậm hơn
# nhưng tự reload). Django runserver tự reload (StatReloader); Celery không, `refresh be` chạy lại.
# refresh cũng cài lại dependency khi package-lock.json / uv.lock đổi và chạy migrate khi cần.
# Worker mặc định 2 process; xem scripts/development/runtime-memory.md để chỉnh giới hạn.
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

# ---------------------------------------------------------------- màu & output

# Tắt màu khi không phải terminal hoặc khi NO_COLOR được đặt (https://no-color.org)
_color_on() { [ -z "${NO_COLOR:-}" ] && [ -t 1 ]; }
if _color_on; then
  C_RESET=$'\033[0m'  C_BOLD=$'\033[1m'   C_DIM=$'\033[2m'
  C_RED=$'\033[31m'   C_GREEN=$'\033[32m' C_YELLOW=$'\033[33m' C_CYAN=$'\033[36m'
else
  C_RESET='' C_BOLD='' C_DIM='' C_RED='' C_GREEN='' C_YELLOW='' C_CYAN=''
fi

ts()   { date '+%H:%M:%S'; }
die()  { printf '%s\n' "${C_RED}${C_BOLD}[$(ts)] ✗ Lỗi:${C_RESET}${C_RED} $*${C_RESET}" >&2; exit 1; }
say()  { printf '%s\n' "${C_GREEN}[$(ts)]${C_RESET} ${C_BOLD}▶${C_RESET} $*"; }
info() { printf '%s\n' "${C_DIM}[$(ts)]   $*${C_RESET}"; }
warn() { printf '%s\n' "${C_YELLOW}[$(ts)] ⚠ $*${C_RESET}"; }
usage() { awk 'NR==1{next} /^[^#]/{exit} {sub(/^# ?/,""); print}' "$0"; }

# ---------------------------------------------------------------- PID / cổng

pid_of()   { cat "$RUN_DIR/$1.pid" 2>/dev/null || true; }
alive()    { local p; p="$(pid_of "$1")"; [ -n "$p" ] && kill -0 "$p" 2>/dev/null; }
port_busy(){ (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

# ---------------------------------------------------------------- chờ HTTP + stream log

# wait_http URL giây tên — cuộn log service ra màn hình khi chờ khởi động.
wait_http() {
  local url="$1" secs="$2" name="$3" log="$RUN_DIR/$3.log"
  local i last_size=0 new_size chunk
  info "Chờ $name khởi động (tối đa ${secs}s) — log: ${C_CYAN}.cache/dev-stack/$name.log${C_RESET}"
  for ((i = 0; i < secs; i++)); do
    # Stream log mới kể từ lần kiểm tra trước
    if [ -f "$log" ]; then
      new_size=$(wc -c < "$log" 2>/dev/null || echo 0)
      if [ "$new_size" -gt "$last_size" ]; then
        tail -c +"$((last_size + 1))" "$log" 2>/dev/null \
          | head -30 \
          | sed "s/^/${C_DIM}  │ /" \
          | sed "s/$/${C_RESET}/"
        last_size=$new_size
      fi
    fi
    curl -s -o /dev/null --max-time 2 "$url" && return 0
    if ! alive "$name"; then
      warn "$name thoát sớm. Xem log:"
      tail -40 "$log" 2>/dev/null | sed "s/^/  ${C_RED}│${C_RESET} /"
      return 1
    fi
    sleep 1
  done
  warn "Hết thời gian chờ $name (${secs}s). Xem log:"
  tail -40 "$log" 2>/dev/null | sed "s/^/  ${C_YELLOW}│${C_RESET} /"
  return 1
}

# ---------------------------------------------------------------- launch / halt

# launch tên thư_mục lệnh...: chạy trong nhóm tiến trình riêng (setsid) để stop dừng được cả cây con.
launch() {
  local name="$1" dir="$2"; shift 2
  if alive "$name"; then say "$name đang chạy (pid $(pid_of "$name"))"; return 0; fi
  : >"$RUN_DIR/$name.log"
  (cd "$dir" && exec setsid "$@" >>"$RUN_DIR/$name.log" 2>&1 </dev/null) &
  echo $! >"$RUN_DIR/$name.pid"
  touch "$RUN_DIR/$name.started"   # dấu mốc thời gian để refresh tự phát hiện thay đổi
  say "$name bắt đầu — pid $! — log ${C_CYAN}.cache/dev-stack/$name.log${C_RESET}"
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

# ---------------------------------------------------------------- giới hạn tài nguyên

validate_runtime_settings() {
  local setting value
  for setting in LABELX_WORKER_CONCURRENCY LABELX_WORKER_MAX_TASKS_PER_CHILD LABELX_WORKER_MAX_MEMORY_KIB; do
    case "$setting" in
      LABELX_WORKER_CONCURRENCY) value="${LABELX_WORKER_CONCURRENCY-2}" ;;
      LABELX_WORKER_MAX_TASKS_PER_CHILD) value="${LABELX_WORKER_MAX_TASKS_PER_CHILD-20}" ;;
      LABELX_WORKER_MAX_MEMORY_KIB) value="${LABELX_WORKER_MAX_MEMORY_KIB-393216}" ;;
    esac
    [[ "$value" =~ ^[1-9][0-9]*$ ]] || die "$setting phải là số nguyên dương."
  done
  [[ "${LABELX_DJANGO_AUTORELOAD-1}" =~ ^[01]$ ]] || die "LABELX_DJANGO_AUTORELOAD chỉ nhận 0 hoặc 1."
}

# ---------------------------------------------------------------- dependency

# uv sync không làm gì khi venv đã khớp uv.lock (dưới 1 giây).
deps_backend() {
  say "kiểm tra dependency backend (uv sync)"
  (cd "$BACKEND" && "$UV" sync --frozen -q)
}

# npm ci mất vài phút trên /mnt: chỉ chạy khi package-lock.json mới hơn bản npm ghi lúc cài.
deps_frontend() {
  if [ ! -x "$FRONTEND/node_modules/.bin/next" ] \
    || [ "$FRONTEND/package-lock.json" -nt "$FRONTEND/node_modules/.package-lock.json" ]; then
    say "npm ci (frontend)"
    (cd "$FRONTEND" && npm ci --no-audit --no-fund)
  else
    info "npm: node_modules đã khớp package-lock.json, bỏ qua"
  fi
}

migrate() {
  if ! (cd "$BACKEND" && "$UV" run --frozen python manage.py migrate --check >/dev/null 2>&1); then
    say "chạy migrate"
    (cd "$BACKEND" && "$UV" run --frozen python manage.py migrate)
  else
    info "migrate: không có migration mới"
  fi
}

# ---------------------------------------------------------------- tiến trình

start_infra() {
  command -v docker >/dev/null \
    || die "Cần Docker (Docker Desktop bật WSL integration hoặc Docker Engine)."
  say "hạ tầng: postgres, redis, seaweedfs"
  "${COMPOSE[@]}" up -d --wait postgres redis seaweedfs
  "${COMPOSE[@]}" run --rm seaweedfs-init >/dev/null
}

start_be() {
  validate_runtime_settings
  # Nếu process tồn tại nhưng API không phản hồi → restart thay vì chờ rồi die
  if alive be; then
    if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$API_PORT/api/schema/"; then
      info "be đã sẵn sàng (pid $(pid_of be)) — bỏ qua"
      return 0
    else
      warn "be đang chạy nhưng không phản hồi — khởi động lại"
      stop_be
    fi
  fi
  if port_busy "$API_PORT"; then die "Cổng $API_PORT đang bị tiến trình khác dùng."; fi
  local reload_args=()
  [ "${LABELX_DJANGO_AUTORELOAD-1}" = 0 ] && reload_args+=(--noreload)
  launch be "$BACKEND" "$UV" run --frozen python manage.py runserver "127.0.0.1:$API_PORT" "${reload_args[@]}"
  launch worker "$BACKEND" "$UV" run --frozen celery -A config worker -l info \
    --concurrency "${LABELX_WORKER_CONCURRENCY-2}" \
    --max-tasks-per-child "${LABELX_WORKER_MAX_TASKS_PER_CHILD-20}" \
    --max-memory-per-child "${LABELX_WORKER_MAX_MEMORY_KIB-393216}"
  launch beat   "$BACKEND" "$UV" run --frozen celery -A config beat -l info
  wait_http "http://127.0.0.1:$API_PORT/api/schema/" 90 be \
    || die "API không lên — xem .cache/dev-stack/be.log"
}

start_fe() {
  # Nếu process tồn tại nhưng UI không phản hồi → restart thay vì chờ rồi die
  if alive fe; then
    if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$FE_PORT/login"; then
      info "fe đã sẵn sàng (pid $(pid_of fe)) — bỏ qua"
      return 0
    else
      warn "fe đang chạy nhưng không phản hồi — khởi động lại"
      halt fe
    fi
  fi
  if port_busy "$FE_PORT"; then die "Cổng $FE_PORT đang bị tiến trình khác dùng."; fi
  local poll=0
  [ -f "$RUN_DIR/fe.poll" ] && poll=1
  if [ "$poll" -eq 1 ]; then
    launch fe "$FRONTEND" env WATCHPACK_POLLING=true npx next dev --webpack -H 127.0.0.1 -p "$FE_PORT"
  else
    launch fe "$FRONTEND" npx next dev -H 127.0.0.1 -p "$FE_PORT"
  fi
  wait_http "http://127.0.0.1:$FE_PORT/login" 180 fe \
    || die "Next không lên — xem .cache/dev-stack/fe.log"
}

stop_be() { halt beat; halt worker; halt be; }


# ---------------------------------------------------------------- lệnh

cmd_start() {
  validate_runtime_settings
  local follow=0
  rm -f "$RUN_DIR/fe.poll"
  for arg in "$@"; do
    case "$arg" in
      --poll)   touch "$RUN_DIR/fe.poll" ;;
      --follow) follow=1 ;;
      *) die "start không nhận tùy chọn '$arg' (hợp lệ: --poll, --follow)" ;;
    esac
  done

  [ -f "$BACKEND/.env" ] && [ -f "$FRONTEND/.env.local" ] \
    || node "$ROOT/scripts/development/environment.cjs" env

  printf '%s\n' \
    "${C_BOLD}${C_CYAN}" \
    "  ╔══════════════════════════════════════╗" \
    "  ║     LabelX Dev Stack — khởi động     ║" \
    "  ╚══════════════════════════════════════╝${C_RESET}"

  start_infra
  deps_backend
  deps_frontend
  migrate
  start_be
  start_fe

  echo
  printf '%s\n' \
    "${C_GREEN}${C_BOLD}  ✓ LabelX sẵn sàng!${C_RESET}" \
    "${C_BOLD}    UI :  http://127.0.0.1:$FE_PORT${C_RESET}" \
    "${C_DIM}    API:  http://127.0.0.1:$API_PORT/api/${C_RESET}" \
    "${C_DIM}    Log:  .cache/dev-stack/{be,worker,beat,fe}.log${C_RESET}" \
    "${C_DIM}    Tip:  ./scripts/dev-stack.sh logs        — xem log trực tiếp${C_RESET}" \
    "${C_DIM}    Tip:  ./scripts/dev-stack.sh logs be     — chỉ log Django${C_RESET}" \
    "${C_DIM}    Tip:  ./scripts/dev-stack.sh restart     — bounce nhanh khi service treo${C_RESET}" \
    "${C_DIM}    Tip:  ./scripts/dev-stack.sh refresh     — nạp lại code từ Windows${C_RESET}" \
    "${C_DIM}    Tip:  ./scripts/dev-stack.sh status      — trạng thái tiến trình${C_RESET}"
  echo

  if [ "$follow" -eq 1 ]; then
    say "follow mode — Ctrl+C để thoát (các tiến trình vẫn chạy nền)"
    cmd_logs be worker beat fe
  fi
}

cmd_stop() {
  halt fe
  stop_be
  if [ "${1:-}" != "--keep-infra" ]; then
    say "tắt hạ tầng (giữ dữ liệu)"
    "${COMPOSE[@]}" down
  fi
}

# restart: bounce nhanh (không xoá cache, không cài dep, không migrate).
# Dùng khi process crash hoặc bị treo — nhanh hơn refresh vì giữ Turbopack cache.
cmd_restart() {
  local target="${1:-all}"
  case "$target" in fe|be|all) ;; *) die "restart nhận fe|be|all" ;; esac
  if [ "$target" != fe ]; then
    validate_runtime_settings
    stop_be
    start_be
  fi
  if [ "$target" != be ]; then
    halt fe
    # Không xoá .next — giữ Turbopack cache để khởi động lại nhanh (~15s vs ~50s)
    start_fe
  fi
  say "đã restart $target"
}


# ---------------------------------------------------------------- phát hiện thay đổi

# _src_changed marker dir [find-args...]: true nếu có file trong dir mới hơn marker.
# -print -quit dừng ngay khi tìm thấy file đầu tiên → nhanh trên /mnt.
_src_changed() {
  local marker="$1" dir="$2"; shift 2
  [ ! -f "$marker" ] && return 0   # chưa từng start = coi như đã thay đổi
  find "$dir" -newer "$marker" "$@" -print -quit 2>/dev/null | grep -q .
}

needs_be_refresh() {
  local m="$RUN_DIR/be.started"
  # uv.lock / settings thay đổi → cần restart
  { [ "$BACKEND/uv.lock" -nt "$m" ] || [ "$BACKEND/config/settings.py" -nt "$m" ]; } 2>/dev/null && return 0
  # Bất kỳ file .py nào trong src (bỏ qua .venv, __pycache__)
  _src_changed "$m" "$BACKEND" \
    -not \( -path "*/.venv*" -o -path "*/.venv-wsl*" -o -path "*/__pycache__/*" \) \
    -name "*.py"
}

needs_fe_refresh() {
  local m="$RUN_DIR/fe.started"
  # package-lock.json / next.config thay đổi → cần restart
  { [ "$FRONTEND/package-lock.json" -nt "$m" ] || [ "$FRONTEND/next.config.ts" -nt "$m" ]; } 2>/dev/null && return 0
  # Bất kỳ file nào trong src/ (bỏ qua node_modules, .next)
  _src_changed "$m" "$FRONTEND/src" \
    -not \( -path "*/node_modules/*" -o -path "*/.next/*" \)
}

cmd_refresh() {
  local target="${1:-auto}"
  case "$target" in fe|be|all|auto) ;; *) die "refresh nhận: fe | be | all (hoặc bỏ trống = tự phát hiện)" ;; esac

  local do_be=0 do_fe=0
  case "$target" in
    auto)
      if needs_be_refresh; then do_be=1; else info "be: không phát hiện thay đổi — bỏ qua"; fi
      if needs_fe_refresh; then do_fe=1; else info "fe: không phát hiện thay đổi — bỏ qua"; fi
      ;;
    be)  do_be=1 ;;
    fe)  do_fe=1 ;;
    all) do_be=1; do_fe=1 ;;
  esac

  if [ "$do_be" -eq 0 ] && [ "$do_fe" -eq 0 ]; then
    say "không có thay đổi cần refresh — dùng 'refresh all' để ép buộc"
    return 0
  fi

  if [ "$do_be" -eq 1 ]; then
    validate_runtime_settings
    stop_be
    deps_backend
    migrate
    start_be
  fi
  if [ "$do_fe" -eq 1 ]; then
    halt fe
    deps_frontend
    # Cache Turbopack/webpack giữ module cũ khi watcher không thấy thay đổi trên /mnt.
    rm -rf "$FRONTEND/.next/dev" "$FRONTEND/.next/cache"
    start_fe
  fi

  local refreshed=()
  [ "$do_be" -eq 1 ] && refreshed+=(be)
  [ "$do_fe" -eq 1 ] && refreshed+=(fe)
  say "đã refresh: ${refreshed[*]}"
}

cmd_status() {
  local name p
  echo "${C_BOLD}  Tiến trình:${C_RESET}"
  for name in be worker beat fe; do
    p="$(pid_of "$name")"
    if alive "$name"; then
      printf "  ${C_GREEN}●${C_RESET} %-7s ${C_GREEN}chạy${C_RESET}   (pid %-6s)  ${C_DIM}log: .cache/dev-stack/%s.log${C_RESET}\n" \
        "$name" "$p" "$name"
    else
      printf "  ${C_DIM}○${C_RESET} %-7s ${C_DIM}dừng${C_RESET}\n" "$name"
    fi
  done
  [ -f "$RUN_DIR/fe.poll" ] && echo "${C_DIM}  (fe: webpack + polling)${C_RESET}"
  echo
  echo "${C_BOLD}  Container Docker:${C_RESET}"
  "${COMPOSE[@]}" ps --format 'table {{.Service}}\t{{.Status}}' 2>/dev/null \
    | sed 's/^/  /' || true
}

cmd_logs() {
  local names=("$@")
  [ ${#names[@]} -gt 0 ] || names=(be worker beat fe)
  local files=() n
  for n in "${names[@]}"; do
    [ -f "$RUN_DIR/$n.log" ] || warn "chưa có log: $n (service chưa khởi động?)"
    files+=("$RUN_DIR/$n.log")
  done
  say "Theo dõi log: ${names[*]} — Ctrl+C để thoát (service vẫn chạy nền)"
  exec tail -n 50 -F "${files[@]}"
}

main() {
  mkdir -p "$RUN_DIR"
  cmd="${1:-}"
  [ $# -gt 0 ] && shift
  case "$cmd" in
    start)   cmd_start "$@" ;;
    stop)    cmd_stop "$@" ;;
    restart) cmd_restart "$@" ;;
    refresh) cmd_refresh "$@" ;;
    status)  cmd_status ;;
    logs)    cmd_logs "$@" ;;
    -h|--help|help|"") usage ;;
    *) usage >&2; exit 2 ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
