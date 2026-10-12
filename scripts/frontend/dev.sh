#!/usr/bin/env bash
# Chạy frontend LabelX để PO kiểm tra giao diện, không cần backend, Postgres, Redis hay CVAT.
#
#   scripts/frontend/dev.sh [-p PORT] [-H HOST] [--i-know-lan] [--role VAI_TRÒ] [--no-api] [--install]
#
#   -p, --port PORT   Cổng mở trình duyệt (mặc định 3000).
#   -H, --host HOST   Địa chỉ nghe (mặc định localhost).
#   --i-know-lan      Bắt buộc khi HOST không phải localhost/127.0.0.1/::1: mock auth (mật khẩu password123) và API giả
#                     sẽ mở cho mọi máy trong mạng. Chỉ dùng trên mạng tin cậy.
#   --role VAI_TRÒ    In sẵn tài khoản của vai trò: admin|qalead|qcadmin|reviewer|annotator|productowner|modelowner.
#   --no-api          Không bật API giả lập: chỉ /api/auth/* hoạt động, trang gọi API khác báo lỗi kết nối.
#   --install         Chạy npm ci dù đã có node_modules (mặc định chỉ chạy khi thiếu).
#   -h, --help        Hiện trợ giúp này.
#
# Chế độ mock auth (NEXT_PUBLIC_AUTH_MODE=mock); mật khẩu mọi tài khoản mẫu: password123.
# Mặc định bật thêm API giả lập (scripts/frontend/mock-api.cjs, chỉ dùng khi dev) đứng trước Next dev
# trên cổng công khai, nên mọi màn hình có dữ liệu mẫu. Không đụng .env, không đổi mã ứng dụng.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

port=3000 host=localhost role="" api=1 install=0 lan=0
while [ $# -gt 0 ]; do
  case "$1" in
    -p|--port) port="${2:?thiếu số cổng}"; shift 2 ;;
    -H|--host) host="${2:?thiếu host}"; shift 2 ;;
    --role) role="${2:?thiếu vai trò}"; shift 2 ;;
    --i-know-lan) lan=1; shift ;;
    --no-api) api=0; shift ;;
    --install) install=1; shift ;;
    -h|--help) fe_help "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "Tham số không hợp lệ: $1 (dùng --help)" >&2; exit 2 ;;
  esac
done
[[ "$port" =~ ^[0-9]+$ ]] || fe_die "Cổng không hợp lệ: $port"
[ -z "$role" ] || fe_valid_role "$role" || fe_die "Vai trò không hợp lệ: $role (${FE_ROLES[*]})"
case "$host" in
  localhost|127.0.0.1|::1) ;;
  *)
    [ "$lan" -eq 1 ] || fe_die "HOST=$host mở mock auth (tài khoản mẫu, mật khẩu $FE_PASSWORD) và API giả lập ra mạng. Dùng localhost, hoặc thêm --i-know-lan nếu chắc chắn mạng này tin cậy."
    echo "CẢNH BÁO: $host mở mock auth (mật khẩu $FE_PASSWORD) và API giả lập cho mọi máy trong mạng." >&2 ;;
esac
command -v curl >/dev/null || fe_die "Cần curl."
fe_ensure_deps "$install"

# Biến môi trường của tiến trình thắng .env.local, nên không sửa file đó.
export NEXT_PUBLIC_AUTH_MODE=mock
export NEXT_PUBLIC_API_BASE_URL=
export NEXT_TELEMETRY_DISABLED=1

fe_port_busy "$port" && fe_die "Cổng $port đang được dùng. Chọn cổng khác với -p."

next_pid=""
cleanup() {
  [ -n "$next_pid" ] && kill -- "-$next_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT TERM

if [ "$api" -eq 1 ]; then
  fe_need_node
  inner=$((port + 1))
  fe_port_busy "$inner" && fe_die "Cổng nội bộ $inner (Next dev) đang được dùng. Chọn cổng khác với -p."
  echo ">> Khởi động Next dev (nội bộ 127.0.0.1:$inner)..."
  (cd "$FE_DIR" && exec setsid npx next dev -H 127.0.0.1 -p "$inner") &
  next_pid=$!
  fe_wait_http "http://127.0.0.1:$inner/login" 120 "$next_pid" || fe_die "Next dev không lên (xem log ở trên)."
else
  (cd "$FE_DIR" && exec setsid npx next dev -H "$host" -p "$port") &
  next_pid=$!
fi

echo
echo "LabelX frontend (mock auth$([ "$api" -eq 1 ] && echo ' + API giả lập' || echo ', không API giả lập'))"
echo "  URL: http://${host}:${port}"
echo "  Mật khẩu mọi tài khoản: $FE_PASSWORD"
if [ -n "$role" ]; then echo "  Đăng nhập: $role / $FE_PASSWORD"; else echo "  Tài khoản: ${FE_ROLES[*]}"; fi
echo "  Route:"
for r in "${FE_ROUTES[@]}"; do echo "    http://${host}:${port}${r}"; done
echo
echo "Nhấn Ctrl+C để dừng."

if [ "$api" -eq 1 ]; then
  node "$FE_SCRIPTS_DIR/mock-api.cjs" --port "$port" --host "$host" --target "http://127.0.0.1:$inner"
  exit $?
fi
wait "$next_pid"
