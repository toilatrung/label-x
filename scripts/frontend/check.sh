#!/usr/bin/env bash
# Kiểm tra frontend trước khi báo xong: lint, test, build, verify-design, rò rỉ mật khẩu mẫu.
#
#   scripts/frontend/check.sh [--skip-build] [--install]
#
#   --skip-build   Bỏ build và bước grep password123 trong .next/static (nhanh hơn).
#   --install      Chạy npm ci dù đã có node_modules (mặc định chỉ chạy khi thiếu).
#   -h, --help     Hiện trợ giúp này.
#
# Các bước: eslint · vitest --maxWorkers=3 · next build · node docs/design/tools/verify-design.cjs ·
# grep password123 trong src/frontend/.next/static. In bảng PASS/FAIL; thoát mã 1 nếu có bước FAIL.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

skip_build=0 install=0
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-build) skip_build=1; shift ;;
    --install) install=1; shift ;;
    -h|--help) fe_help "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "Tham số không hợp lệ: $1 (dùng --help)" >&2; exit 2 ;;
  esac
done
set -e
fe_ensure_deps "$install"
set +e

names=() results=()
step() { # step "tên" lệnh...
  local name="$1"; shift
  echo; echo "=== $name ==="
  if "$@"; then results+=(PASS); else results+=(FAIL); fi
  names+=("$name")
}
no_password_leak() {
  local out="$FE_DIR/.next/static"
  [ -d "$out" ] || { echo "Chưa có $out (cần build)."; return 1; }
  if grep -rq "password123" "$out"; then echo "Tìm thấy password123 trong $out"; grep -rl "password123" "$out" | head; return 1; fi
  echo "Không có password123 trong .next/static."
}

step "lint (eslint)" bash -c "cd '$FE_DIR' && npm run lint"
step "test (vitest --maxWorkers=3)" bash -c "cd '$FE_DIR' && npx vitest run --maxWorkers=3"
if [ "$skip_build" -eq 0 ]; then
  step "build (next build)" bash -c "cd '$FE_DIR' && npm run build"
fi
step "verify-design" node "$FE_ROOT/docs/design/tools/verify-design.cjs"
[ "$skip_build" -eq 0 ] && step "không lộ password123 trong .next/static" no_password_leak

echo; echo "================ TÓM TẮT ================"
fail=0
for i in "${!names[@]}"; do printf '  %-44s %s\n' "${names[$i]}" "${results[$i]}"; [ "${results[$i]}" = PASS ] || fail=1; done
[ "$skip_build" -eq 1 ] && echo "  (đã bỏ build và kiểm tra rò rỉ)"
if [ "$fail" -eq 0 ]; then echo "KẾT QUẢ: PASS"; else echo "KẾT QUẢ: FAIL"; fi
exit "$fail"
