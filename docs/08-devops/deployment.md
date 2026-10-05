---
id: devops-deployment
title: Triển khai LabelX
type: reference
domain: devops
module: repository
tags: [devops, deployment, topology, docker-compose]
priority: 3
---
# Triển khai LabelX

## Mục đích

Mô tả topology triển khai tham chiếu (SRS chương 10 + DEC-001), cách chạy môi trường dev local và những gì còn mở cho production.

## 1. Thành phần (DEC-001, B-01)

- **Modular monolith** Django 5.2 + DRF, chạy bằng Gunicorn (dependency `gunicorn` có trong `pyproject.toml`).
- **Worker pool Celery 5** + Redis 7 làm broker/result backend; `django-celery-beat` cho lịch định kỳ (`CELERY_BEAT_SCHEDULER = DatabaseScheduler`).
- **PostgreSQL 17**: snapshot, run, issue, lease, decision, audit, effort.
- **Object Storage S3-compatible hiện có** (qua `django-storages`): ảnh, evidence, báo cáo/manifest. SeaweedFS **chỉ dùng cho dev local**.
- **Frontend** Next.js 16 + React 19.
- **CVAT hiện có**: hệ thống ngoài; adapter chỉ đọc (B-18).

## 2. Topology tham chiếu (SRS `10-architecture.tex`, hình deployment)

```text
+---------------------------+   +-----------------------+   +----------------------+
| App server (Linux)        |<->| GPU server            |<->| Data                 |
|  Gunicorn + Django/DRF    |   |  Celery GPU worker    |   |  PostgreSQL          |
|  Celery CPU workers       |   |  Detector baseline    |   |  Redis               |
+---------------------------+   +-----------------------+   |  Object Storage      |
      ^            ^                                        +----------------------+
      | HTTPS      | HTTPS (chỉ đọc)                              ^
 [Trình duyệt]  [CVAT hiện có]           App server <-------------+
```

- CPU worker chạy Schema, Geometry, Duplicate, Matching, Ranking; GPU worker chạy Detector baseline (SRS 10, sơ đồ thành phần).
- T và A đề xuất tách hàng đợi CPU và GPU (A mục 20.1: "worker GPU tách hàng đợi riêng"). Tên queue và routing Celery **chưa cấu hình** trong repo.
- Cấu hình phần cứng app server và GPU server: **TBD-02** (Tech Lead, trước build).
- Cách phục vụ frontend Next.js ở production (`next start` hay host khác) và reverse proxy/TLS: **chưa có căn cứ**, chờ TBD-02.

## 3. Dev local

Chi tiết lệnh: [../07-development/tooling.md](../07-development/tooling.md).

```bash
make setup        # bật postgres, redis, seaweedfs bằng infrastructure/docker-compose.dev.yml, cài dependency, migrate
make dev-backend  # Django runserver :8000 (không phải Gunicorn)
make dev-worker   # Celery worker
make dev-beat     # Celery beat — hiện chưa có task/lịch nào (polling drift CVAT: việc mở, TBD-01)
make dev-frontend # Next.js dev :3000
```

- Compose chỉ chứa hạ tầng (PostgreSQL, Redis, SeaweedFS + job tạo bucket). Django, Celery và Next.js chạy trực tiếp trên máy dev.
- CVAT không chạy trong compose; trỏ `CVAT_BASE_URL` tới instance thật khi có (TBD-01). `NEXT_PUBLIC_CVAT_BASE_URL` mặc định `http://localhost:8080` chỉ dùng để dựng deep link.
- Repo **chưa có** Dockerfile cho backend/frontend.

## 4. Production — TBD

| Hạng mục | Trạng thái | Căn cứ |
|---|---|---|
| Phần cứng app server, GPU server | **TBD-02** | SRS 11 |
| Phiên bản CVAT được pin, URL, quyền token | **TBD-01** | SRS 11; DEC-001 |
| Object Storage thật (endpoint, bucket, versioning) | Dùng storage hiện có; chi tiết chưa có. Bật versioning theo NFR-16 | DEC-001; NFR-16 |
| HTTPS, cấu hình bảo mật Django production | Đề xuất trong [../06-security/security-policies.md](../06-security/security-policies.md) mục 9 | NFR-07 |
| Secret store cho token CVAT, `DJANGO_SECRET_KEY` | Chưa chọn | FR-SNP-02 |
| Sao lưu PostgreSQL + Object Storage cùng lịch, diễn tập khôi phục | RPO/RTO **TBD-17** | NFR-16 |
| Pipeline triển khai | Chưa triển khai thật; xem [ci-cd.md](ci-cd.md) | — |

### Thứ tự khởi động và migration (đề xuất)

1. Hạ tầng dữ liệu (PostgreSQL, Redis, Object Storage) sẵn sàng.
2. Chạy `manage.py migrate` một lần trước khi bật phiên bản mới.
3. Bật Gunicorn, CPU worker, GPU worker, beat. Chỉ chạy **một** tiến trình beat.
4. Bật frontend.

Task Celery phải idempotent (B-10), nên worker có thể restart giữa chừng: `CELERY_TASK_ACKS_LATE` và `CELERY_TASK_REJECT_ON_WORKER_LOST` đã bật trong `settings.py`, task bị gián đoạn sẽ được giao lại.

## 5. Sao lưu và khôi phục nhất quán (NFR-16)

NFR-16 yêu cầu sao lưu PostgreSQL và Object Storage (bật versioning) **theo cùng lịch**, và khôi phục được snapshot, ảnh, evidence, quyết định, reference, effort log **nhất quán với nhau**; cách kiểm là diễn tập khôi phục. RPO/RTO: **TBD-17** (Tech Lead, trước triển khai). Công cụ sao lưu **chưa chọn**. Quy trình dưới đây là **đề xuất** để đáp ứng yêu cầu; cần duyệt và diễn tập trước khi dùng.

### Nguyên tắc nhất quán

- PostgreSQL là nguồn chuẩn của metadata. Blob trên Object Storage được ghi **trước** metadata, với khoá theo hash nội dung (NFR-06). Vì vậy một bản PostgreSQL tại thời điểm T chỉ trỏ tới blob đã tồn tại trước T.
- Hệ quả: khôi phục PostgreSQL về T, rồi khôi phục Object Storage về một thời điểm **≥ T** (versioning cho phép chọn phiên bản theo thời gian). Blob thừa (có trên storage nhưng không có metadata) là chấp nhận được; job dọn dẹp \(t_{gc}\) xử lý chúng. **Không** khôi phục storage về thời điểm sớm hơn DB, vì metadata sẽ trỏ tới blob không tồn tại.
- Không dùng job dọn dẹp blob mồ côi ngay sau khôi phục, cho tới khi kiểm xong các tiêu chí bên dưới.

### Các bước khôi phục (đề xuất)

1. Dừng ghi: tắt Gunicorn, worker, beat (hoặc chặn ghi) để không phát sinh dữ liệu mới.
2. Chọn thời điểm khôi phục T theo bản sao lưu PostgreSQL gần nhất hợp lệ. Ghi lại T và lý do.
3. Khôi phục PostgreSQL về T.
4. Khôi phục/giữ Object Storage ở phiên bản tại thời điểm ≥ T (theo versioning).
5. Chạy `manage.py migrate --check` (hoặc `showmigrations`) để xác nhận schema khớp phiên bản code đang triển khai.
6. Chạy bộ kiểm xác nhận (mục dưới) **trước khi** mở lại cho người dùng.
7. Bật lại dịch vụ. Shard/run đang chạy dở được xử lý lại nhờ task idempotent (B-10). Lease đang giữ tại T coi như hết hạn theo quy tắc lease (TBD-09).
8. Ghi audit cho sự kiện khôi phục: người thực hiện, T, phạm vi dữ liệu mất từ T đến thời điểm sự cố.

### Tiêu chí xác nhận sau khôi phục

| Đối tượng | Kiểm tra | Đạt khi |
|---|---|---|
| Snapshot | Với mỗi snapshot đã khoá: đọc JSON đã chuẩn hoá trên Object Storage, tính lại hash SHA-256 từng job và hash tổng (FR-SNP-03) | Khớp hash lưu trong PostgreSQL |
| Ảnh frame | Với ảnh mà snapshot tham chiếu: tính checksum | Mọi ảnh tồn tại và khớp checksum lưu khi snapshot (FR-SNP-05) |
| Evidence/crop | Mọi URI evidence trong metadata candidate/issue | Tồn tại và khớp hash nội dung (NFR-06) |
| Quyết định + audit | Mỗi decision có AuditEvent tương ứng; audit không có bản ghi trỏ tới đối tượng không tồn tại | Đủ cặp; số lượng không giảm so với báo cáo gần nhất trước T |
| Reference | Reference đã khoá: version, trạng thái khoá và tập item còn nguyên | Khớp với audit khoá reference |
| Effort log | Sự kiện effort liên tục theo frame/phiên tới T; không có phiên trỏ tới lease/frame không tồn tại | Không có tham chiếu hỏng |
| Report/manifest | File trên storage | Tồn tại, checksum khớp |

Kết quả xác nhận được lưu làm bằng chứng diễn tập. NFR-16 yêu cầu diễn tập khôi phục; tần suất diễn tập **chưa chốt**.

## Liên quan

- [ci-cd.md](ci-cd.md)
- [monitoring.md](monitoring.md)
- [../06-security/threat-model.md](../06-security/threat-model.md)
