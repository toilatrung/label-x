#!/usr/bin/env bash
# Chụp ảnh mọi route M-FE01 ở 1440 px và 390 px cho một vai trò bằng Playwright.
#
#   scripts/frontend/screenshot.sh [--role VAI_TRÒ] [--url URL] [--start] [--out THƯ_MỤC] [ROUTE ...]
#
#   --role VAI_TRÒ  admin|qalead|qcadmin|reviewer|annotator|productowner|modelowner (mặc định qalead).
#   --url URL       Địa chỉ giao diện đang chạy (mặc định http://localhost:3000, tức dev.sh mặc định).
#   --start         Tự chạy dev.sh (cổng 3400, API giả lập) rồi dừng sau khi chụp; bỏ qua --url.
#   --out THƯ_MỤC   Nơi lưu ảnh (mặc định src/frontend/evidence/shots/VAI_TRÒ; thư mục đã được gitignore).
#   ROUTE ...       Chỉ chụp các route này (mặc định: tất cả 19 route M-FE01).
#
# Playwright được cài vào ~/.cache/labelx-frontend-scripts (ngoài repo, không sửa package.json).
# Nếu Chromium thiếu libnspr4/libnss3/libasound2, script tự tải .deb và dùng LD_LIBRARY_PATH (không cần root).
# Tên ảnh: <route>-1440.png và <route>-390.png. Thoát mã 1 nếu có route lỗi hoặc cuộn ngang.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

role=qalead url=http://localhost:3000 start=0 out="" routes=()
while [ $# -gt 0 ]; do
  case "$1" in
    --role) role="${2:?thiếu vai trò}"; shift 2 ;;
    --url) url="${2:?thiếu URL}"; shift 2 ;;
    --start) start=1; shift ;;
    --out) out="${2:?thiếu thư mục}"; shift 2 ;;
    -h|--help) fe_help "${BASH_SOURCE[0]}"; exit 0 ;;
    -*) echo "Tham số không hợp lệ: $1 (dùng --help)" >&2; exit 2 ;;
    *) routes+=("$1"); shift ;;
  esac
done
fe_valid_role "$role" || fe_die "Vai trò không hợp lệ: $role (${FE_ROLES[*]})"
[ ${#routes[@]} -gt 0 ] || routes=("${FE_ROUTES[@]}")
[ -n "$out" ] || out="$FE_DIR/evidence/shots/$role"
fe_need_node
command -v curl >/dev/null || fe_die "Cần curl."

dev_pid=""
cleanup() { [ -n "$dev_pid" ] && kill -- "-$dev_pid" 2>/dev/null || true; }
trap cleanup EXIT
trap 'exit 130' INT TERM

if [ "$start" -eq 1 ]; then
  url=http://127.0.0.1:3400
  fe_port_busy 3400 && fe_die "Cổng 3400 đang được dùng."
  setsid bash "$FE_SCRIPTS_DIR/dev.sh" -p 3400 -H 127.0.0.1 >"${TMPDIR:-/tmp}/labelx-fe-dev.log" 2>&1 &
  dev_pid=$!
  fe_wait_http "$url/login" 240 "$dev_pid" || { tail -20 "${TMPDIR:-/tmp}/labelx-fe-dev.log" >&2; fe_die "dev.sh không lên."; }
else
  fe_wait_http "$url/login" 5 || fe_die "Không mở được $url. Chạy scripts/frontend/dev.sh trước hoặc dùng --start."
fi

pwdir="$(fe_playwright_dir)"
libs="$(fe_chromium_libs "$pwdir")"
[ -z "$libs" ] || export LD_LIBRARY_PATH="$libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

echo ">> Chụp $role tại $url -> $out"
node "$FE_SCRIPTS_DIR/shot.cjs" "$pwdir" "$url" "$role" "$out" "${routes[@]}"
