# LabelX

Quality Control cho annotation trên CVAT: snapshot → engine kiểm tra → review/rework → quality gate → phát hành.

## Cài đặt cho dev mới

Máy chưa có công cụ: xem [env-setup.md](env-setup.md). Không cần Make để khởi tạo. Script cài công cụ thiếu khi chọn `InstallGlobal`, rồi tạo cấu hình, cài dependency theo lockfile, bật dịch vụ, migrate và build frontend.

Windows (PowerShell, từ root project):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\init-develop-environment.ps1 -InstallGlobal
```

Ubuntu/WSL (Terminal):

```bash
bash scripts/init-develop-environment.sh --install-global
```

Docker lần đầu có thể cần hoàn thành khởi tạo hoặc reboot; WSL cần Docker Desktop integration. Phát triển Celery worker dùng Ubuntu/WSL. Lệnh Make hằng ngày dành cho Bash trên Ubuntu/WSL:

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
| `scripts/` | `init-develop-environment.ps1`/`.sh` bootstrap, `.mk` target Make, `validate-framework.py` của kit |
| `docs/` | Tài liệu theo agentic-sdlc-kit; SRS LaTeX ở `docs/label-x_system-requirement-specification/` |
| `.agent/` | Planning, execution, governance, reports theo [agentic-sdlc-kit](https://github.com/toilatrung/agentic-sdlc-kit) — xem `AGENT.md` |
| `docs/design/` | Design System và 25 màn hình (nguồn chuẩn H) |

Quyết định stack: `.agent/governance/decisions/DEC-001.md`.
