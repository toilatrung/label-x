# LabelX

Quality Control cho annotation trên CVAT: snapshot → engine kiểm tra → review/rework → quality gate → phát hành.

## Cài đặt cho dev mới

Cần sẵn: `git`, `make`, `curl`, Docker (Compose v2), Node.js ≥ 22. uv và Python 3.12 được tự cài.

```bash
make setup          # kiểm tra máy, tạo .env, bật Postgres/Redis/S3, cài dependency, migrate
make dev-backend    # http://localhost:8000/api/docs/
make dev-worker     # Celery worker
make dev-frontend   # http://localhost:3000
make check          # lint + typecheck + test + validate kit
make help           # mọi lệnh
```

## Cấu trúc

| Đường dẫn | Nội dung |
|---|---|
| `src/backend/` | Django 5.2 + DRF (modular monolith), Celery, Python 3.12 / uv |
| `src/frontend/` | Next.js 16 + React 19 + TypeScript, Design System LabelX |
| `infrastructure/` | Docker Compose dev: PostgreSQL 17, Redis 7, SeaweedFS (S3) |
| `scripts/` | `Makefile` setup/dev, `validate-framework.py` của kit |
| `docs/` | Tài liệu theo agentic-sdlc-kit; SRS LaTeX ở `docs/label-x_system-requirement-specification/` |
| `.agent/` | Planning, execution, governance, reports theo [agentic-sdlc-kit](https://github.com/toilatrung/agentic-sdlc-kit) — xem `AGENT.md` |
| `docs/design/` | Design System và 25 màn hình (nguồn chuẩn H) |

Quyết định stack: `.agent/governance/decisions/DEC-001.md`.
