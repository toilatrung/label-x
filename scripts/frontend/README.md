# scripts/frontend — chạy và kiểm tra giao diện LabelX

Dành cho PO và dev xem giao diện M-FE01 mà không cần backend, Postgres, Redis hay CVAT.
Mọi script là bash (`set -euo pipefail`), có `--help`, chạy được từ thư mục bất kỳ, không đụng `.env` và không đổi mã ứng dụng.

## Xem giao diện

```bash
scripts/frontend/dev.sh                 # http://localhost:3000
scripts/frontend/dev.sh -p 3200 --role reviewer
```

- Tự chạy `npm ci` nếu thiếu `node_modules`; đăng nhập bằng tài khoản mẫu, mật khẩu `password123`:
  `admin`, `qalead`, `qcadmin`, `reviewer`, `annotator`, `productowner`, `modelowner`.
- Script in URL của từng route M-FE01. `--role` chỉ in sẵn tài khoản cần đăng nhập.
- Mặc định bật **API giả lập** (`mock-api.cjs`) nên các màn gọi API thật cũng có dữ liệu: Dataset, Snapshot, cấu hình, QC run, ranking, candidate, escalation, guideline, quyền workflow. Số liệu theo bộ chuẩn: 12,500 frame (3 task), coverage 92.4%, 384 candidate.
- Mặc định chỉ nghe `localhost`. `-H` khác (ví dụ `0.0.0.0`) bị từ chối trừ khi thêm `--i-know-lan`, vì mock auth (mật khẩu `password123`) và API giả sẽ mở ra cả mạng.
- `--no-api` bỏ API giả lập: chỉ `/api/auth/*` hoạt động, các trang gọi API khác báo lỗi kết nối (đúng hành vi khi chưa có backend).
- API giả lập chỉ để dev: ghi (POST) trả thành công giả và không lưu trạng thái; không nằm trong bundle production.

Vì sao API giả lập đứng trước Next: ở mock auth, giao diện luôn gọi API cùng origin và `next.config.ts` tắt rewrite `/api`.
`dev.sh` chạy Next ở cổng `PORT+1` (nội bộ) và `mock-api.cjs` ở `PORT`. `/api/auth/*` và mọi trang được chuyển nguyên cho Next, các `/api/*` còn lại do `mock-api.cjs` trả lời.

## Kiểm tra trước khi báo xong

```bash
scripts/frontend/check.sh               # lint + vitest --maxWorkers=3 + build + verify-design + grep password123
scripts/frontend/check.sh --skip-build  # nhanh hơn, bỏ build và grep
```

In bảng PASS/FAIL; thoát mã 1 nếu có bước FAIL.

## Chụp ảnh 1440 px và 390 px

```bash
scripts/frontend/dev.sh &                         # hoặc dùng --start bên dưới
scripts/frontend/screenshot.sh --role qalead      # ảnh vào src/frontend/evidence/shots/qalead/
scripts/frontend/screenshot.sh --role admin --start /analysis /reports
```

- Chụp 19 route M-FE01 (hoặc chỉ các route truyền vào); báo cuộn ngang và số cảnh báo "chưa kết nối" mỗi trang.
- `--start` tự chạy `dev.sh` ở cổng 3400 rồi dừng; `--url` trỏ tới giao diện đang chạy ở nơi khác.
- Playwright `1.56.1` được cài vào `~/.cache/labelx-frontend-scripts` (ngoài repo, không sửa `package.json`).
  Nếu Chromium thiếu `libnspr4`, `libnss3`, `libasound2`, script tự tải `.deb` bằng `apt-get download`, giải nén vào cache và dùng `LD_LIBRARY_PATH`; không cần root.
- `src/frontend/evidence/shots/` đã được gitignore.

## Tương thích

`scripts/dev-fe.sh` (nếu có trên máy bạn) vẫn chạy như cũ; `scripts/frontend/dev.sh` là bản thay thế đầy đủ hơn.
