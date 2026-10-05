---
id: observability-logging
title: Logging LabelX
type: reference
domain: observability
module: repository
tags: [observability, logging, structured-logs, correlation-id]
priority: 3
---
# Logging LabelX

## Yêu cầu nguồn

- **NFR-12**: log có cấu trúc kèm `run_id`, `snapshot_id`, `request_id`; cách kiểm: kiểm tra dashboard vận hành.
- **NFR-07**: mật khẩu/secret không xuất hiện trong log; token CVAT chỉ ở backend.
- **09-interfaces, hợp đồng lỗi**: mọi phản hồi lỗi có `code`, `message`, `request_id`; lỗi 403/409 được ghi audit.
- **A mục 28**: nếu sau này bật RAG/VLM, log prompt/response gắn với evidence để truy vết. VLM đề xuất không bật trong pilot (TBD-08).

## Hiện trạng

- `src/backend/config/settings.py` **chưa có** cấu hình `LOGGING`, nên Django dùng log mặc định. Celery worker chạy `-l info` (`make dev-worker`).
- Chưa có middleware sinh `request_id`, chưa có thư viện log JSON, chưa có nơi tập trung log.
- Ba trường `run_id`, `snapshot_id`, `request_id` và yêu cầu log có cấu trúc là **đã chốt** (NFR-12); không log secret là **đã chốt** (NFR-07). Các trường khác, danh sách sự kiện và cách hiện thực là **đề xuất**. Không thêm thư viện log mới khi chưa có change request (DEC-001, `AGENT.md`). Thư viện `logging` chuẩn của Python với formatter JSON đủ cho yêu cầu này.

## Phân biệt log và audit

| | Log vận hành | Audit log |
|---|---|---|
| Mục đích | Chẩn đoán lỗi, hiệu năng | Bằng chứng nghiệp vụ (R-05) |
| Lưu ở | Hệ thống log (chưa chọn) | Bảng PostgreSQL append-only, cùng transaction với thao tác (FR-SEC-05) |
| Sửa/xoá | Theo chính sách xoay vòng log | Không có API sửa/xoá (NFR-08) |
| Thời hạn | Đề xuất ngắn (chưa chốt) | Giữ khi dataset còn cần đối chiếu; tối thiểu **TBD-15** |

Log **không thay** audit. Một quyết định review phải có AuditEvent; log chỉ ghi thêm để chẩn đoán.

## Trường log đề xuất

| Trường | Bắt buộc | Ghi chú |
|---|---|---|
| `timestamp` | Có | ISO 8601 có múi giờ (`TIME_ZONE = Asia/Ho_Chi_Minh`, `USE_TZ = True`) |
| `level` | Có | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `logger`, `message` | Có | |
| `service` | Có | `api`, `worker-cpu`, `worker-gpu`, `beat` |
| `request_id` | Có với request API | Sinh ở middleware hoặc nhận từ header; trả về trong phản hồi lỗi |
| `run_id`, `snapshot_id` | Có khi thao tác thuộc run/snapshot | NFR-12 |
| `engine`, `shard`, `attempt` | Có với task engine | Khoá idempotent `(run, engine, shard)` (A mục 20.3) |
| `task_id`, `task_name` | Có với Celery task | |
| `user_id`, `role` | Có với request đã đăng nhập | Dùng id nội bộ, không log tên/email |
| `duration_ms` | Nên có | Thời gian request/task/shard |
| `error_code` | Khi lỗi | Khớp `code` của hợp đồng lỗi |

Truyền `request_id` từ API sang Celery task qua header của task, để nối log API với log worker của cùng một thao tác (đề xuất).

## Không được log

- `CVAT_SERVICE_TOKEN`, `DJANGO_SECRET_KEY`, `OBJECT_STORAGE_SECRET_KEY`, mật khẩu, cookie phiên, header `Authorization`/`Cookie` (NFR-07).
- URL có chứa credential (ví dụ `DATABASE_URL` đầy đủ).
- Nội dung ảnh hay crop. Chỉ log URI Object Storage hoặc hash.
- Dữ liệu cá nhân không cần cho chẩn đoán.

Đề xuất: thêm filter che giá trị theo tên biến/header nhạy cảm, và một test kiểm log của luồng adapter CVAT không chứa token.

## Sự kiện nên log (đề xuất)

| Nhóm | Sự kiện | Level |
|---|---|---|
| CVAT adapter | Bắt đầu/kết thúc đọc job, số frame, thời gian; lỗi HTTP, timeout | INFO / WARNING |
| Snapshot | Khoá thành công, hash tổng; drift phát hiện (danh sách job) | INFO / WARNING |
| Orchestrator | Tạo run, chia shard, shard bắt đầu/kết thúc/retry/Failed, huỷ run | INFO / WARNING / ERROR |
| Worker | Task bị giao lại sau khi worker chết (acks late) | WARNING |
| Review | Cấp lease, lease hết hạn, xung đột 409, từ chối 403 (self-review, tách nhiệm vụ) | INFO / WARNING |
| Hệ thống | Lỗi không bắt được (500) kèm stack trace | ERROR |

## Thời hạn và nơi lưu log

**Chưa có.** Phụ thuộc hạ tầng production (TBD-02). Khi chốt, ghi lại tại đây.

## Liên quan

- [metrics.md](metrics.md)
- [alerts-and-slo.md](alerts-and-slo.md)
- [../06-security/security-policies.md](../06-security/security-policies.md)
