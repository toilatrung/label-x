# LabelX — hướng dẫn cho agent

- Quy trình làm việc theo `AGENT.html` (agentic-sdlc-kit): chỉ làm việc có task được duyệt; ghi decision/blocker/report vào `.agent/`. Chạy `make validate-kit` sau khi sửa `.agent/` hoặc `docs/`.
- Tài liệu chỉ viết bằng HTML (CR-103): không tạo file `.md` trong `docs/`, `.agent/`; tạo bản ghi mới từ `.agent/templates/*.html`, metadata đặt trong `<meta name="labelx:id|title|type|domain|module|tags|priority">`. File này, `src/frontend/AGENTS.md`, `SKILL.md`, `README.md`, PR template là ngoại lệ vì công cụ bắt buộc Markdown.
- Nhánh (CR-104): tạo nhánh task từ `develop`, mở PR với base `develop`; chỉ PO merge `develop` → `main`. PR cần comment `Đã xem và duyệt` của @toilatrung hoặc @DucHa180104 (CR-102).
- Ngoại lệ M-03 được PO chỉ định tại issue #97: task T-033…T-046 tạo nhánh riêng từ `origin/integration/m03`, PR vào `integration/m03`. Hà (@DucHa180104) review/merge PR của nhóm; PR do Hà viết cần Thọ (@tdt2112) review và Việt Anh QC độc lập. Sau review/CI/test đủ gate mới merge; không push trực tiếp vào nhánh tích hợp. Nam mở PR tổng `integration/m03` → `develop`, chỉ PO review/merge sau khi xem toàn luồng. T-032/PR #111 đã merge vào develop và có trong baseline. Chi tiết `.github/M03-INTEGRATION.html`; ngoại lệ chỉ áp dụng M-03, không đổi luồng develop → main.
- Stack chốt ở `.agent/governance/decisions/DEC-001.html`. Không đổi framework/thư viện chính khi chưa có change request được duyệt.
- Ranh giới cứng: adapter CVAT **chỉ đọc**; sửa annotation bằng deep link sang CVAT. Celery task phải idempotent. Quyền project/job kiểm ở API.
- Backend: `src/backend` (uv). Frontend: `src/frontend` — đọc `src/frontend/AGENTS.md` trước khi viết code Next.js 16.
- UI theo Design System `docs/design/` (class `lx-*`, Inter, bảng-trước) — dùng skill `labelx-design` (`.agent/skills/labelx-design/SKILL.md`).
- Review PR trước khi comment duyệt: skill `labelx-pr-review` (`.agent/skills/labelx-pr-review/SKILL.md`). Review toàn luồng trước khi merge `develop` → `main` hoặc đóng đợt: skill `labelx-flow-review` (`.agent/skills/labelx-flow-review/SKILL.md`).
- QC sau review, kèm gộp file `-@user` của dev vào file chính rồi xoá chúng (CR-100): skill `labelx-qc-integrate` (`.agent/skills/labelx-qc-integrate/SKILL.md`); chỉ integrator.
- Kiểm tra trước khi báo xong: `make check` (cần `make infra-up`).
