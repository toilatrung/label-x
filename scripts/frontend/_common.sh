# Dùng chung cho scripts/frontend/*.sh (được source, không chạy trực tiếp).
# shellcheck shell=bash

FE_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FE_ROOT="$(cd "$FE_SCRIPTS_DIR/../.." && pwd)"
FE_DIR="$FE_ROOT/src/frontend"

# Route của M-FE01 (kèm nhóm để in cho dễ đọc).
FE_ROUTES=(
  / /analysis /analysis/snapshots /analysis/config /analysis/history
  /review /review/workspace /review/rework /escalations
  /calibration/performance /calibration/benchmark /calibration/audit-sampling /calibration/calibration
  /reports /reports/gate /reports/releases
  /configuration /configuration/rules-thresholds /configuration/guidelines
)

FE_ROLES=(admin qalead qcadmin reviewer annotator productowner modelowner)
FE_PASSWORD=password123   # mật khẩu tài khoản mẫu của mock auth (src/lib/auth/mock-users.ts)

fe_die() { echo "Lỗi: $*" >&2; exit 1; }

# In khối chú thích đầu file (từ dòng 2 tới dòng trống đầu tiên) làm trợ giúp.
fe_help() { awk 'NR==1{next} /^[^#]/{exit} {sub(/^# ?/,""); print}' "$1"; }

fe_valid_role() {
  local r
  for r in "${FE_ROLES[@]}"; do [ "$r" = "$1" ] && return 0; done
  return 1
}

fe_need_node() { command -v node >/dev/null || fe_die "Cần Node.js (xem src/frontend/package.json)."; }

fe_ensure_deps() {
  fe_need_node
  if [ "${1:-0}" -eq 1 ] || [ ! -x "$FE_DIR/node_modules/.bin/next" ]; then
    echo ">> Cài dependency (npm ci)..."
    (cd "$FE_DIR" && npm ci --no-audit --no-fund)
  fi
}

# fe_wait_http URL [giây] [PID]: chờ tới khi URL trả mã HTTP bất kỳ; dừng sớm nếu PID đã thoát.
fe_wait_http() {
  local url="$1" tries="${2:-90}" pid="${3:-}" i
  for ((i = 0; i < tries; i++)); do
    curl -s -o /dev/null --max-time 2 "$url" && return 0
    [ -z "$pid" ] || kill -0 "$pid" 2>/dev/null || return 1
    sleep 1
  done
  return 1
}

fe_port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

# ---- Playwright / Chromium (không thêm vào package.json của repo) ----
FE_PW_VERSION=1.56.1
FE_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/labelx-frontend-scripts"

# Cài playwright@$FE_PW_VERSION vào thư mục cache riêng và in đường dẫn của nó.
fe_playwright_dir() {
  local dir="$FE_CACHE/playwright-$FE_PW_VERSION"
  if [ ! -d "$dir/node_modules/playwright" ]; then
    mkdir -p "$dir"
    echo ">> Cài playwright@$FE_PW_VERSION vào $dir (ngoài repo)..." >&2
    (cd "$dir" && npm init -y >/dev/null && npm i --no-audit --no-fund "playwright@$FE_PW_VERSION" >&2)
  fi
  PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}" \
    "$dir/node_modules/.bin/playwright" install chromium >&2
  echo "$dir"
}

# In LD_LIBRARY_PATH bổ sung nếu Chromium thiếu thư viện hệ thống (libnspr4, libnss3, libasound2).
# Không cần root: tải .deb bằng apt-get download rồi giải nén vào thư mục cache.
fe_chromium_libs() {
  local pwdir="$1" chrome libdir="$FE_CACHE/syslibs/usr/lib/x86_64-linux-gnu" missing
  chrome="$(find "${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}" -type f -name chrome -path '*chromium-*' 2>/dev/null | head -1)"
  [ -n "$chrome" ] || chrome="$(find "${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}" -type f -name headless_shell 2>/dev/null | head -1)"
  [ -n "$chrome" ] || { echo ""; return 0; }
  missing="$(ldd "$chrome" 2>/dev/null | grep -c 'not found' || true)"
  if [ "$missing" -gt 0 ]; then
    if ! ls "$libdir"/libnss3.so >/dev/null 2>&1; then
      echo ">> Chromium thiếu thư viện hệ thống; tải .deb (không cần root) vào $FE_CACHE/syslibs ..." >&2
      local tmp; tmp="$(mktemp -d)"
      (cd "$tmp" && apt-get download libnspr4 libnss3 libasound2t64 >&2 2>&1 || apt-get download libnspr4 libnss3 libasound2 >&2) \
        || fe_die "Không tải được .deb. Cài thủ công: sudo apt-get install -y libnspr4 libnss3 libasound2t64"
      mkdir -p "$FE_CACHE/syslibs"
      for d in "$tmp"/*.deb; do dpkg-deb -x "$d" "$FE_CACHE/syslibs"; done
      rm -rf "$tmp"
    fi
    echo "$libdir"
  else
    echo ""
  fi
}
