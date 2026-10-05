# LabelX — hướng dẫn cho agent

- Quy trình làm việc theo `AGENT.md` (agentic-sdlc-kit): chỉ làm việc có task được duyệt; ghi decision/blocker/report vào `.agent/`; mọi file Markdown của kit cần frontmatter. Chạy `make validate-kit` sau khi sửa `.agent/` hoặc `docs/`.
- Stack chốt ở `.agent/governance/decisions/DEC-001.md`. Không đổi framework/thư viện chính khi chưa có change request được duyệt.
- Ranh giới cứng: adapter CVAT **chỉ đọc**; sửa annotation bằng deep link sang CVAT. Celery task phải idempotent. Quyền project/job kiểm ở API.
- Backend: `src/backend` (uv). Frontend: `src/frontend` — đọc `src/frontend/AGENTS.md` trước khi viết code Next.js 16.
- UI theo Design System `docs/design/` (class `lx-*`, Inter, bảng-trước) — dùng skill `labelx-design` (`.agent/skills/labelx-design/SKILL.md`).
- Kiểm tra trước khi báo xong: `make check` (cần `make infra-up`).
