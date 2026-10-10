#!/usr/bin/env bash
# Chạy LabelX local (Ubuntu/WSL) và tự kiểm tra các dịch vụ đã lên.
#
#   bash scripts/development/run-local.sh              # bật infra, migrate, chạy backend+worker+frontend, smoke check, giữ chạy
#   bash scripts/development/run-local.sh --check-only # bật, smoke check, rồi tắt (dùng để kiểm nhanh)
#   bash scripts/development/run-local.sh --tests      # thêm pytest + vitest trước khi chạy
#   bash scripts/development/run-local.sh --no-infra   # bỏ qua docker compose (infra đã chạy)
#   bash scripts/development/run-local.sh --no-worker  # không chạy Celery worker
#
# Ctrl+C tắt backend/worker/frontend; hạ tầng docker giữ nguyên (make infra-down để tắt).
set -Eeuo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
backend="$root/src/backend"
frontend="$root/src/frontend"
compose=(docker compose -f "$root/infrastructure/docker-compose.dev.yml")
logs="$root/.cache/run-local"
export PATH="$HOME/.local/bin:$PATH"
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [[ -s "$NVM_DIR/nvm.sh" ]]; then source "$NVM_DIR/nvm.sh"; fi
if [[ -n "${WSL_DISTRO_NAME:-}" ]]; then export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-wsl}"; fi

check_only=0 run_tests=0 use_infra=1 use_worker=1
for arg in "$@"; do
  case "$arg" in
    --check-only) check_only=1 ;;
    --tests) run_tests=1 ;;
    --no-infra) use_infra=0 ;;
    --no-worker) use_worker=0 ;;
    -h|--help) sed -n '2,10p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "Tuỳ chọn không hợp lệ: $arg" >&2; exit 2 ;;
  esac
done

pids=()
failures=0
step() { printf '\n\033[36m== %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m[OK]\033[0m   %s\n' "$*"; }
fail() { printf '  \033[31m[FAIL]\033[0m %s\n' "$*"; failures=$((failures + 1)); }

cleanup() {
  trap - EXIT INT TERM
  if ((${#pids[@]})); then
    step "Tắt tiến trình"
    for pid in "${pids[@]}"; do kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true; done
    wait 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# Chạy lệnh nền trong nhóm tiến trình riêng để tắt được cả cây con (npm/next, celery).
start() { # name, dir, cmd...
  local name="$1" dir="$2"; shift 2
  (cd "$dir" && exec setsid "$@" >"$logs/$name.log" 2>&1) &
  pids+=("$!")
  echo "  $name pid=$! log=${logs#"$root"/}/$name.log"
}

wait_http() { # name, url, accepted-code-regex, timeout
  local name="$1" url="$2" accept="$3" timeout="${4:-90}" code=000 i
  for ((i = 0; i < timeout; i++)); do
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$url" || true)"
    if [[ "$code" =~ $accept ]]; then ok "$name $url → $code"; return 0; fi
    sleep 1
  done
  fail "$name $url → $code sau ${timeout}s (xem log trong ${logs#"$root"/}/)"
  return 1
}

step "Kiểm công cụ"
for tool in uv node npm curl; do
  if command -v "$tool" >/dev/null; then ok "$tool"; else fail "thiếu $tool (chạy: make tools)"; fi
done
((use_infra)) && { command -v docker >/dev/null && ok docker || fail "thiếu docker"; }
[[ -f "$backend/.env" ]] && ok "backend .env" || fail "thiếu src/backend/.env (chạy: make env)"
[[ -x "$frontend/node_modules/.bin/next" ]] && ok "frontend node_modules" || fail "thiếu node_modules (chạy: make frontend-install)"
((failures == 0)) || { echo "Dừng: môi trường chưa đủ. Thử: make setup" >&2; exit 1; }

mkdir -p "$logs"

if ((use_infra)); then
  step "Bật hạ tầng (Postgres, Redis, SeaweedFS)"
  "${compose[@]}" up -d --wait postgres redis seaweedfs
  "${compose[@]}" run --rm seaweedfs-init >/dev/null
  ok "infra healthy"
fi

step "Kiểm kết nối DB/Redis/S3 và migrations"
(cd "$root" && uv run --project "$backend" --frozen python scripts/development/verify-services.py) \
  && ok "verify-services" || fail "verify-services"
(cd "$backend" && uv run --frozen python manage.py migrate --noinput >"$logs/migrate.log" 2>&1) \
  && ok "migrate" || fail "migrate (xem ${logs#"$root"/}/migrate.log)"
(cd "$backend" && uv run --frozen python manage.py check >"$logs/django-check.log" 2>&1) \
  && ok "manage.py check" || fail "manage.py check (xem ${logs#"$root"/}/django-check.log)"
((failures == 0)) || exit 1

if ((run_tests)); then
  step "Test backend + frontend"
  (cd "$backend" && uv run --frozen pytest -q) && ok "pytest" || fail "pytest"
  (cd "$frontend" && npm test --silent) && ok "vitest" || fail "vitest"
  ((failures == 0)) || exit 1
fi

step "Chạy dịch vụ"
start backend "$backend" uv run --frozen python manage.py runserver 0.0.0.0:8000 --noreload
((use_worker)) && start worker "$backend" uv run --frozen celery -A config worker -l info
start frontend "$frontend" npm run dev

step "Smoke check"
wait_http "API schema"  "http://localhost:8000/api/schema/" '^200$' 90 || true
wait_http "API docs"    "http://localhost:8000/api/docs/"   '^200$' 30 || true
# Chưa đăng nhập: API được bảo vệ phải từ chối (401/403), không phải 200/500.
wait_http "API runs (chưa đăng nhập bị chặn)" "http://localhost:8000/api/runs/" '^(401|403)$' 30 || true
wait_http "Frontend /login" "http://localhost:3000/login" '^200$' 120 || true
if ((use_worker)); then
  sleep 3
  if kill -0 "${pids[1]}" 2>/dev/null && grep -q "ready" "$logs/worker.log"; then ok "celery worker ready"
  else fail "celery worker chưa sẵn sàng (xem ${logs#"$root"/}/worker.log)"; fi
fi
for pid in "${pids[@]}"; do kill -0 "$pid" 2>/dev/null || fail "tiến trình pid=$pid đã thoát sớm"; done

step "Kết quả"
if ((failures)); then
  printf '  \033[31m%d kiểm tra lỗi.\033[0m Log: %s\n' "$failures" "${logs#"$root"/}"
else
  printf '  \033[32mTất cả kiểm tra đạt.\033[0m\n'
fi
if ((check_only)); then exit $((failures ? 1 : 0)); fi

cat <<EOF

  Frontend : http://localhost:3000
  API docs : http://localhost:8000/api/docs/
  Log      : ${logs#"$root"/}/*.log   (tail -f ... để theo dõi)
  Ctrl+C để tắt; hạ tầng docker giữ nguyên (make infra-down).
EOF
wait -n "${pids[@]}" 2>/dev/null || true
echo "Một tiến trình đã thoát; đang tắt phần còn lại." >&2
exit $((failures ? 1 : 0))
