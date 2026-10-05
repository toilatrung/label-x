---
id: development-tooling
title: Tooling và môi trường dev LabelX
type: reference
domain: development
module: repository
tags: [development, tooling, uv, node, make, docker]
priority: 2
---
# Tooling và môi trường dev LabelX

## Mục đích

Mô tả công cụ và lệnh dev **đang có trong repo**. Nguồn: `scripts/init-develop-environment.mk` (được `Makefile` gốc `include`), `README.md`, `src/backend/pyproject.toml`, `src/frontend/package.json`, `infrastructure/docker-compose.dev.yml`.

## 1. Yêu cầu trên máy

Hướng dẫn cho máy chưa có công cụ: `env-setup.md` ở root project. Windows chạy `scripts/init-develop-environment.ps1`; Ubuntu/WSL chạy `scripts/init-develop-environment.sh`. Make là wrapper tùy chọn, không phải điều kiện để chạy bootstrap. Script chỉ báo hoàn thành setup sau kiểm kết nối dịch vụ, migrate, Django check và build frontend.

| Công cụ | Phiên bản | Ghi chú |
|---|---|---|
| Git; Make/curl/build tools trên Ubuntu | — | Bootstrap cài khi chọn `-InstallGlobal` hoặc `--install-global`; Windows không cần Make/curl |
| Docker + Docker Compose v2 | — | Bootstrap cài Docker Desktop trên Windows hoặc Docker Engine trên Ubuntu trực tiếp nếu thiếu. WSL dùng Desktop integration; first-start/quyền/reboot có thể cần xử lý thủ công |
| Node.js + npm | ≥ 22 | Bootstrap cài khi thiếu/Node quá thấp; Windows dùng WinGet LTS, Ubuntu/WSL dùng nvm Node 22 |
| uv | — | Bootstrap cài khi thiếu và bật InstallGlobal |
| Python | 3.12 | uv tự cài và quản lý (`uv python install 3.12`), không đụng Python hệ thống |

`make env` dùng Node crypto để sinh secret ngẫu nhiên, không có fallback timestamp. File `.env` đã có được giữ; placeholder hoặc endpoint khác bundle Compose làm setup dừng. Script không tự tạo dữ liệu/đăng ký quyền CVAT hay model.

## 2. Bắt đầu nhanh

```bash
make setup          # sau bootstrap công cụ: env → dependency → healthy infra → verify → migrate → check → frontend build
make dev-backend    # http://localhost:8000/api/docs/
make dev-worker     # Celery worker
make dev-frontend   # http://localhost:3000
make superuser      # tạo tài khoản Django admin
make check          # lint + typecheck + test + validate-kit (cần infra-up)
```

`make setup` chạy lại an toàn: `make env` không ghi đè `src/backend/.env` và `src/frontend/.env.local` nếu đã có.

### Frontend :3000 gọi API :8000 (session + CSRF)

- API xác thực bằng session Django (`SessionAuthentication`). Frontend phải gửi request với `credentials: "include"` và gửi header `X-CSRFToken` (lấy từ cookie `csrftoken`) cho mọi request ghi.
- `CORS_ALLOWED_ORIGINS=http://localhost:3000` và `CORS_ALLOW_CREDENTIALS = True` đã có (`.env.example`, `settings.py`).
- `CSRF_TRUSTED_ORIGINS` đọc từ biến môi trường, mặc định bằng `CORS_ALLOWED_ORIGINS`, nên POST từ `localhost:3000` qua được kiểm CSRF Origin.
- **Chưa có** endpoint đăng nhập API trong `src/backend/config/urls.py` (chỉ có `admin/`, `api/schema/`, `api/docs/`). Tài khoản từ `make superuser` chỉ đăng nhập được Django admin.
- Cả hai mục trên là việc mở. Luồng chi tiết: [../06-security/security-policies.md](../06-security/security-policies.md) mục 9.

## 3. Danh sách make target (đúng theo `scripts/init-develop-environment.mk`)

Lệnh mặc định là `make help` (liệt kê target có chú thích `##`).

| Nhóm | Target | Việc làm |
|---|---|---|
| Trợ giúp | `help` | Liệt kê lệnh |
| Setup | `setup` | Gọi bootstrap Bash, thực hiện local tuần tự; không dùng prerequisites có thể chạy song song |
| | `doctor` | Bootstrap `--check`: kiểm công cụ, dependency, kết nối dịch vụ, Django check và migrations; không cài/migrate/build |
| | `tools` | Gọi bootstrap Bash `--install-global`, cài công cụ thiếu và khởi tạo local |
| | `env` | Tạo `src/backend/.env` từ `.env.example` (sinh `DJANGO_SECRET_KEY` dạng `dev-only-…`) và `src/frontend/.env.local` từ `.env.example`; không ghi đè file đã có |
| Hạ tầng | `infra-up` | `docker compose up -d --wait postgres redis seaweedfs`, rồi chạy `seaweedfs-init` tạo bucket |
| | `infra-down` | Tắt hạ tầng, giữ dữ liệu |
| | `infra-logs` | Xem log hạ tầng (`logs -f`) |
| | `infra-reset` | Hỏi xác nhận, **xoá** volume Postgres/SeaweedFS (`down -v`), rồi `infra-up` + `migrate` |
| Dependency | `backend-install` | `uv sync --frozen` theo `uv.lock` |
| | `frontend-install` | `npm ci --no-audit --no-fund` theo `package-lock.json` |
| | `migrate` | `python manage.py migrate` |
| | `superuser` | `python manage.py createsuperuser` |
| Chạy | `dev-backend` | `runserver 0.0.0.0:8000` |
| | `dev-worker` | `celery -A config worker -l info` |
| | `dev-beat` | `celery -A config beat -l info` — chỉ khởi động Celery beat. Hiện **chưa có** task hay lịch nào: `src/backend/config/celery.py` chỉ `autodiscover_tasks()`. Polling drift CVAT là việc mở (TBD-01) |
| | `dev-frontend` | `npm run dev` (Next.js :3000) |
| Chất lượng | `check` | `lint typecheck test validate-kit` — toàn bộ kiểm tra trước khi tạo PR |
| | `lint` | `ruff check .` + `ruff format --check .` (backend); `npm run lint` (frontend) |
| | `format` | `ruff check --fix .` + `ruff format .` (chỉ backend) |
| | `typecheck` | `mypy config` (backend); `npm run typecheck` (frontend) |
| | `test` | `pytest -q` (cần `infra-up`) |
| | `gen-api` | `npm run gen:api` — sinh type TypeScript từ OpenAPI (cần `dev-backend` đang chạy) |
| | `validate-kit` | `uv run --no-project python scripts/validate-framework.py` — kiểm cấu trúc agentic-sdlc-kit (`.agent/`, `docs/`) |
| Dọn | `clean` | Xoá `src/backend/.venv`, `src/frontend/node_modules`, `src/frontend/.next` |

Có thể gọi trực tiếp không qua `Makefile` gốc: `make -f scripts/init-develop-environment.mk <target>`.

## 4. Hạ tầng dev local (`infrastructure/docker-compose.dev.yml`)

| Service | Image | Cổng | Ghi chú |
|---|---|---|---|
| `postgres` | `postgres:17` | 5432 | Volume `postgres-data`; healthcheck `pg_isready` |
| `redis` | `redis:7-alpine` | 6379 | Broker (db 0) và result backend (db 1) của Celery theo `.env.example` |
| `seaweedfs` | `chrislusf/seaweedfs:latest` | 9000 (S3) | Thay Object Storage **chỉ ở local**; cấu hình định danh S3 ở `infrastructure/seaweedfs/s3.json` |
| `seaweedfs-init` | `chrislusf/seaweedfs:latest` | — | Tạo bucket `labelx-snapshots`, `labelx-evidence`, `labelx-reports` |

- CVAT **không** nằm trong compose. Adapter đọc instance CVAT đang triển khai (B-18); `CVAT_BASE_URL` và `CVAT_SERVICE_TOKEN` để trống trong `.env.example` (TBD-01).
- Credential trong compose/`s3.json`/`.env.example` là giá trị dev, không dùng cho môi trường thật.
- `settings.py` có ba storage theo bucket: `snapshots` (`OBJECT_STORAGE_BUCKET_SNAPSHOTS`, mặc định `labelx-snapshots`), `evidence` (`OBJECT_STORAGE_BUCKET_EVIDENCE`, `labelx-evidence`), `reports` (`OBJECT_STORAGE_BUCKET_REPORTS`, `labelx-reports`); `default` vẫn là `OBJECT_STORAGE_BUCKET`. Dùng `django.core.files.storage.storages["snapshots"]`.

## 5. Biến môi trường

| File | Tạo bởi | Nội dung (tên biến) |
|---|---|---|
| `src/backend/.env` | `make env` từ `.env.example` | `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `DATABASE_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `OBJECT_STORAGE_*`, `CVAT_BASE_URL`, `CVAT_SERVICE_TOKEN` |
| `src/frontend/.env.local` | `make env` từ `.env.example` | `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_CVAT_BASE_URL` |

Cả hai file bị `.gitignore` loại. Không commit, không chép giá trị của chúng vào tài liệu hay log.

## 6. Thư viện chính (DEC-001)

- Backend: Django 5.2 (`>=5.2,<5.3`), djangorestframework, drf-spectacular, django-filter, django-cors-headers, django-environ, django-storages[s3] + boto3, Celery 5 (`celery[redis]`) + django-celery-beat, psycopg 3, httpx, pillow, gunicorn.
- Frontend: next 16.3.8, react/react-dom 19.2.8, @tanstack/react-query, openapi-fetch, openapi-typescript.
- Chưa pin phiên bản CVAT/cvat-sdk; phải pin sau khi kiểm API instance thật (DEC-001, TBD-01).

## Liên quan

- [coding-standards.md](coding-standards.md)
- [workflow.md](workflow.md)
- [../08-devops/deployment.md](../08-devops/deployment.md)
