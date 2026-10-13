#!/usr/bin/env bash
# Chạy frontend LabelX độc lập, không cần backend, Postgres, Redis hay CVAT.
#
#   scripts/dev-fe.sh [-p PORT] [-H HOST] [--install]
#
# Dùng chế độ mock auth (NEXT_PUBLIC_AUTH_MODE=mock): đăng nhập bằng tài khoản mẫu, quyền theo vai trò.
# Chỉ các route /api/auth/* được giả lập. Màn hình gọi API khác (datasets, snapshots, runs...)
# sẽ báo lỗi kết nối cho tới khi lớp mock của FE-00 (#146) có mặt. Mock luôn tắt ở production.
set -euo pipefail

port=3000
host=localhost
install=0
while [ $# -gt 0 ]; do
  case "$1" in
    -p|--port) port="${2:?thiếu số cổng}"; shift 2 ;;
    -H|--host) host="${2:?thiếu host}"; shift 2 ;;
    --install) install=1; shift ;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Tham số không hợp lệ: $1 (dùng --help)" >&2; exit 2 ;;
  esac
done

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root/src/frontend"

command -v node >/dev/null || { echo "Cần Node.js (xem src/frontend/package.json)." >&2; exit 1; }
if [ "$install" -eq 1 ] || [ ! -x node_modules/.bin/next ]; then
  echo ">> Cài dependency (npm ci)..."
  npm ci --no-audit --no-fund
fi

# Biến môi trường của tiến trình thắng .env.local, nên không sửa file đó.
export NEXT_PUBLIC_AUTH_MODE=mock
export NEXT_PUBLIC_API_BASE_URL=
export NEXT_TELEMETRY_DISABLED=1

cat <<EOF

LabelX frontend (mock, không cần backend)
  URL:      http://${host}:${port}
  Tài khoản (mật khẩu: password123):
    admin (Super Admin) · qalead · qcadmin · reviewer · annotator · productowner · modelowner
  Lưu ý: chỉ /api/auth/* được giả lập; trang gọi API khác báo lỗi tới khi có lớp mock FE-00.

EOF

exec npx next dev -H "$host" -p "$port"
