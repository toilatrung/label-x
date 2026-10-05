---
id: development-coding-standards
title: Coding standards LabelX
type: reference
domain: development
module: repository
tags: [development, coding-standards, ruff, mypy, eslint, typescript]
priority: 2
---
# Coding standards LabelX

## Mục đích

Quy ước viết mã cho `src/backend` (Python/Django) và `src/frontend` (Next.js/TypeScript). Phần "Cấu hình công cụ" chép đúng cấu hình đang có trong repo. Phần "Quy tắc kiến trúc" lấy từ quyết định đã chốt (`CLAUDE.md`, DEC-001, B-10, B-12, B-18). Mọi kiểm tra tự động chạy bằng `make lint` và `make typecheck` (xem [tooling.md](tooling.md)).

## 1. Định dạng chung (`.editorconfig`)

| Áp dụng | Quy tắc |
|---|---|
| Mọi file | UTF-8, xuống dòng LF, có dòng trống cuối file, bỏ khoảng trắng cuối dòng, thụt lề 2 dấu cách |
| `*.py` | Thụt lề 4 dấu cách |
| `*.md` | Không bỏ khoảng trắng cuối dòng (giữ ngắt dòng Markdown) |

## 2. Backend Python

### Cấu hình công cụ (`src/backend/pyproject.toml`)

- **Python**: `requires-python = ">=3.12"`; ruff `target-version = "py312"`; mypy `python_version = "3.12"`.
- **Ruff**: `line-length = 100`. Các rule bật: `E`, `F`, `W` (pycodestyle/pyflakes), `I` (sắp xếp import), `B` (bugbear), `UP` (pyupgrade), `DJ` (Django), `S` (bandit/bảo mật). Bỏ `S101` (cho phép `assert`). Thư mục `**/tests/**` bỏ toàn bộ nhóm `S`.
- **Ruff format** là formatter duy nhất; `make lint` chạy `ruff format --check`, `make format` tự sửa.
- **mypy**: `strict = true`, `ignore_missing_imports = true`, plugin `mypy_django_plugin.main` và `mypy_drf_plugin.main`, `django_settings_module = "config.settings"`. Stub dev: `django-stubs`, `djangorestframework-stubs`, `celery-types`.
  - Hiện trạng: `make typecheck` chỉ chạy `mypy config`. Khi thêm app nghiệp vụ, phải thêm package đó vào lệnh typecheck trong `scripts/init-develop-environment.mk`. Việc này **chưa làm**, vì chưa có app nào.
- **pytest**: `DJANGO_SETTINGS_MODULE = "config.settings"`, file test `test_*.py` hoặc `*_tests.py`. Dev dependency có `pytest-django`, `factory-boy`. Hiện có `src/backend/tests/test_smoke.py`.

### Quy ước mã

- Kiến trúc **modular monolith**: mỗi module nghiệp vụ là một Django app, đăng ký trong `INSTALLED_APPS` khi epic tương ứng được triển khai (chú thích trong `settings.py`). Danh sách module theo SRS chương 10: CVAT Adapter, Snapshot, QC Orchestrator, Aggregation, Ranking, Review Workflow, Evaluation, Auth/RBAC/Audit/Guideline. Tên package cụ thể **chưa chốt**.
- Mọi giá trị môi trường đọc qua `django-environ` từ biến môi trường/`.env`; thêm biến mới thì cập nhật `src/backend/.env.example` (không chứa secret thật).
- API dùng DRF + `drf-spectacular`. Mặc định đã cấu hình: `SessionAuthentication`, `IsAuthenticated`, `DjangoFilterBackend`, `CursorPagination` (`PAGE_SIZE = 50`). Schema OpenAPI là hợp đồng duy nhất để sinh type cho frontend (DEC-001).
- Phản hồi lỗi có `code`, `message`, `request_id`; dùng đúng mã 400/403/404/409/422 theo SRS `09-interfaces.tex` (hợp đồng lỗi).
- Lưu file qua `STORAGES["default"]` (S3, `file_overwrite: False`). Không ghi thẳng ra đĩa local.

## 3. Frontend TypeScript

### Cấu hình công cụ

- **Next.js 16.3.8**, **React 19.2.8**, TypeScript 5 (`src/frontend/package.json`). `engines.node >= 22`.
- **Đọc `src/frontend/AGENTS.md` trước khi viết code**: Next 16 có thay đổi phá vỡ so với bản cũ; tra hướng dẫn trong `node_modules/next/dist/docs/`.
- **tsconfig**: `strict: true`, `noEmit`, `module: esnext`, `moduleResolution: bundler`, `isolatedModules`, `jsx: react-jsx`, alias `@/*` → `./src/*`.
- **ESLint 9** flat config (`eslint.config.mjs`): `eslint-config-next/core-web-vitals` + `eslint-config-next/typescript`; bỏ qua `.next/**`, `out/**`, `build/**`, `next-env.d.ts`.
- `npm run typecheck` = `next typegen && tsc --noEmit`.
- Gọi API bằng `openapi-fetch`. Type sinh bằng `npm run gen:api` (`openapi-typescript` từ `http://localhost:8000/api/schema/` ra `src/lib/api/schema.d.ts`). Không viết tay type cho payload API. Quản lý dữ liệu server bằng TanStack Query.
- Test runner frontend: **chưa có** (DEC-001: vitest bị loại khỏi scaffold do lỗi npm peer-set; chọn lại khi có epic frontend).

### UI theo Design System LabelX

Nguồn: `.agent/skills/labelx-design/SKILL.md`, `docs/design/README.md`; repo đã chép `src/frontend/src/styles/tokens.css` và `labelx.css`.

- Chỉ dùng token và class `lx-*`. Không hard-code màu, bo góc hay khoảng cách mà token đã có. Thiếu class thì thêm vào Design System trước.
- Trung tính, bảng là chính (table-first); font Inter cho chữ, JetBrains Mono chỉ cho định danh; khoảng cách theo bậc 4/8/12/16/24/32.
- Góc vuông mặc định; viền 1px thay cho bóng đổ (bóng chỉ dùng cho dropdown).
- Trạng thái luôn có chữ (`StatusBadge`), không chỉ dựa vào màu. Engine không chạy hiển thị "Not checked", không bao giờ "passed". Tương phản tối thiểu 4.5:1 (WCAG AA, NFR-10).
- Thao tác trên dòng dùng `lx-iconbtn` có `data-tip` và `aria-label` cùng cụm động từ tiếng Việt. Mỗi vùng chỉ có một nút primary.
- Giao diện tiếng Việt; thuật ngữ miền giữ tiếng Anh (Dataset, Quality Control Run, Snapshot, Coverage, Gate, Issue, Rework, Release). Viết đầy đủ, không viết tắt "QC", "IoU", "GT" trên UI.
- Khi làm màn hình mới, dùng skill `labelx-design` (`.agent/skills/labelx-design/SKILL.md`).

## 4. Quy tắc kiến trúc bắt buộc

| Quy tắc | Cách áp dụng | Nguồn |
|---|---|---|
| **Celery task idempotent** | Chạy lại cùng khoá không tạo bản ghi trùng: khoá theo `(run, engine, shard)`, T đề xuất snapshot + step + frame + config/model version. Blob ghi trước với khoá theo hash nội dung, rồi commit metadata trong một transaction. Settings đã bật `CELERY_TASK_ACKS_LATE`, `CELERY_TASK_REJECT_ON_WORKER_LOST`, `CELERY_WORKER_PREFETCH_MULTIPLIER = 1`, nên task **có thể chạy lại**. Hết retry thì ghi Failed/Partial kèm phạm vi chưa kiểm, không quy thành Checked | `CLAUDE.md`; B-10; NFR-05, NFR-06; A mục 20.3; T mục 6 |
| **Timeout theo loại task** | Đặt riêng cho đọc CVAT, Detector theo lô, kiểm thị giác – ngôn ngữ. **Chưa đặt số** khi chưa đo pilot; số lần retry là TBD-14 | `settings.py` (chú thích); phiếu chốt B-10 |
| **Quyền kiểm ở API** | Mỗi view/action DRF có permission theo vai trò + scope; self-review và tách nhiệm vụ kiểm ở backend; không dựa vào việc ẩn nút | `CLAUDE.md`; B-12; FR-SEC-01…06 |
| **Không ghi CVAT** | CVAT adapter chỉ gọi thao tác đọc; không viết hàm tạo/sửa/xoá annotation; sửa bằng deep link (dựng URL tập trung ở adapter) | `CLAUDE.md`; B-18; FR-SNP-01, FR-SNP-08 |
| **Engine đọc snapshot, không đọc CVAT live** | Worker engine nhận dữ liệu từ snapshot đã export | ADR-02 |
| **Audit cùng transaction** | Ghi AuditEvent trong cùng transaction với thay đổi trạng thái; không có API sửa/xoá audit | FR-SEC-05; ADR-04, ADR-06 |
| **PostgreSQL là nguồn chuẩn của lease** | Cấp lease bằng khoá dòng trong transaction; Redis chỉ là broker/cache | SRS 10, bảng trách nhiệm module |
| **Không đổi stack** | Không đổi framework/thư viện chính khi chưa có change request được duyệt | `CLAUDE.md`; DEC-001; `AGENT.md` (Change Request Rule) |
| **Không log secret** | Không log token CVAT, mật khẩu, secret | NFR-07; [../13-observability/logging.md](../13-observability/logging.md) |

## 5. Tài liệu Markdown

Mọi file `.md` trong `docs/` và `.agent/` bắt đầu bằng YAML frontmatter gồm đúng 7 trường bắt buộc, không rỗng: (1) `id` (duy nhất, ổn định), (2) `title`, (3) `type`, (4) `domain`, (5) `module`, (6) `tags`, (7) `priority` (1…5) (`AGENT.md`, Metadata Standard). Link nội bộ phải trỏ tới file tồn tại. Kiểm bằng `make validate-kit`.
