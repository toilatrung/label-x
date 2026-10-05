---
id: database-migrations
title: Quy tắc Django migrations
type: reference
domain: database
module: quality-control
tags: [database, migrations, django, postgresql]
priority: 2
---
# Django migrations

## Công cụ

- Schema được quản lý bằng **Django migrations** (DEC-001). A §20.1 đề xuất Alembic; đề xuất này không dùng.
- Mỗi app (xem [system-design.md](../02-architecture/system-design.md) mục 3) có thư mục `migrations/` riêng. Hiện chưa có app LabelX nào trong `INSTALLED_APPS`.
- CSDL dev: PostgreSQL 17 từ [docker-compose.dev.yml](../../infrastructure/docker-compose.dev.yml). Kết nối qua `DATABASE_URL` ([settings.py](../../src/backend/config/settings.py)).

## Quy tắc

1. **Mỗi thay đổi model đi kèm migration trong cùng PR.** Đề xuất: pipeline CI (khi được thiết lập) chạy `python manage.py makemigrations --check --dry-run` và thất bại nếu còn thay đổi model chưa có migration. Repository **hiện chưa có** CI thực thi bước này (chưa có `.github/workflows`). Trong lúc chờ, người tạo PR tự chạy lệnh ở bảng "Lệnh" bên dưới.
2. **Không sửa migration đã merge.** Muốn thay đổi thì tạo migration mới.
3. **Đặt tên có nghĩa**: `makemigrations <app> --name <mo_ta_ngan>`.
4. **Ràng buộc nghiệp vụ nằm trong model**: dùng `Meta.constraints` (`UniqueConstraint`, kể cả partial với `condition=Q(...)`, và `CheckConstraint`). Không dựa vào việc kiểm ở tầng ứng dụng cho các khoá idempotent và dedup trong [schema.md](schema.md).
5. **SQL đặc thù PostgreSQL** dùng `migrations.RunSQL`, và luôn có `reverse_sql`. Áp dụng cho:
   - `REVOKE UPDATE, DELETE, TRUNCATE ON audit_log …` và trigger chặn UPDATE/DELETE (append-only, FR-SEC-05, NFR-08). Tên role DB của ứng dụng lấy từ cấu hình triển khai; giá trị cụ thể là TBD theo môi trường.
   - Trigger chặn UPDATE trên `candidate`, `evidence`, `review_decision`, cũng như trên `config_version`, `score_version`, `reference` sau khi đã publish hoặc khoá.
6. **Migration dữ liệu** (`RunPython`) phải idempotent và có `reverse_code`, hoặc ghi rõ `migrations.RunPython.noop` kèm lý do.
7. **Không xoá hay đổi kiểu cột chứa bằng chứng** (snapshot, evidence, decision, audit, reference). Bằng chứng phải được giữ khi dataset còn cần đối chiếu (NFR-08; R "retention"). Muốn bỏ cột thì làm hai bước: ngừng ghi, rồi xoá sau khi người quản lý dữ liệu xác nhận.
8. **Thay đổi an toàn khi đang chạy**:
   - Thêm cột NULL được trước, backfill, rồi mới đặt NOT NULL.
   - Index trên bảng lớn tạo bằng `AddIndexConcurrently` (`django.contrib.postgres.operations`), trong migration có `atomic = False`.
9. **Không seed dữ liệu nghiệp vụ** (taxonomy, guideline, ngưỡng) bằng migration. Dữ liệu này vào qua `config_version` và guideline version có audit.
10. **Kiểm thử**: `pytest-django` tạo DB test từ migrations. Mỗi ràng buộc idempotent hoặc dedup cần ít nhất một test chèn trùng để chứng minh DB từ chối.

## Lệnh

| Việc | Lệnh (chạy trong `src/backend`) |
|---|---|
| Tạo migration | `uv run python manage.py makemigrations <app> --name <ten>` |
| Kiểm còn thiếu | `uv run python manage.py makemigrations --check --dry-run` |
| Áp dụng | `uv run python manage.py migrate` |
| Xem SQL | `uv run python manage.py sqlmigrate <app> <so>` |

## Sao lưu trước khi migrate ở môi trường thật

Sao lưu PostgreSQL theo cùng lịch với Object Storage (NFR-16). RPO/RTO: **TBD-17**.
