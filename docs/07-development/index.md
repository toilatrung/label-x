---
id: development-overview
title: Development
type: reference
domain: development
module: repository
tags: [development, standards, workflow]
priority: 3
---
# Development

Hướng dẫn phát triển LabelX: quy ước viết mã, công cụ dev và quy trình làm việc theo agentic-sdlc-kit. Nội dung dựa trên cấu hình thật trong repo (`src/backend/pyproject.toml`, `src/frontend/`, `scripts/init-develop-environment.mk`, `.editorconfig`) và quyết định đã chốt (DEC-001, `CLAUDE.md`).

## Nội dung

- [coding-standards.md](coding-standards.md) — cấu hình ruff/mypy/ESLint/tsconfig; quy tắc kiến trúc (Celery task idempotent, quyền kiểm ở API, không ghi CVAT, UI theo Design System `lx-*`).
- [tooling.md](tooling.md) — uv, Python 3.12, Node ≥ 22, Docker Compose dev, toàn bộ make target.
- [workflow.md](workflow.md) — epic/task, executor → reviewer (Codex CLI) → QA, report trong `.agent/`, kiểm tra trước khi báo xong, hiện trạng git/PR.

## Bắt đầu

```bash
make setup && make help
```
