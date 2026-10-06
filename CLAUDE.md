# LabelX — hướng dẫn cho agent

- Quy trình làm việc theo `AGENT.html` (agentic-sdlc-kit): chỉ làm việc có task được duyệt; ghi decision/blocker/report vào `.agent/`. Chạy `make validate-kit` sau khi sửa `.agent/` hoặc `docs/`.
- Tài liệu chỉ viết bằng HTML (CR-103): không tạo file `.md` trong `docs/`, `.agent/`; tạo bản ghi mới từ `.agent/templates/*.html`, metadata đặt trong `<meta name="labelx:id|title|type|domain|module|tags|priority">`. File này, `src/frontend/AGENTS.md`, `SKILL.md`, `README.md`, PR template là ngoại lệ vì công cụ bắt buộc Markdown.
- Nhánh (CR-104): tạo nhánh task từ `develop`, mở PR với base `develop`; chỉ PO merge `develop` → `main`. PR cần comment `Đã xem và duyệt` của @toilatrung hoặc @DucHa180104 (CR-102).
- Stack chốt ở `.agent/governance/decisions/DEC-001.html`. Không đổi framework/thư viện chính khi chưa có change request được duyệt.
- Ranh giới cứng: adapter CVAT **chỉ đọc**; sửa annotation bằng deep link sang CVAT. Celery task phải idempotent. Quyền project/job kiểm ở API.
- Backend: `src/backend` (uv). Frontend: `src/frontend` — đọc `src/frontend/AGENTS.md` trước khi viết code Next.js 16.
- UI theo Design System `docs/design/` (class `lx-*`, Inter, bảng-trước) — dùng skill `labelx-design` (`.agent/skills/labelx-design/SKILL.md`).
- Kiểm tra trước khi báo xong: `make check` (cần `make infra-up`).
