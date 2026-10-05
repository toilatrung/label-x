---
id: observability-alerts-slo
title: Cảnh báo và SLO LabelX
type: reference
domain: observability
module: repository
tags: [observability, slo, alerts, nfr, tbd]
priority: 3
---
# Cảnh báo và SLO LabelX

## Trạng thái

- **Đã chốt (bắt buộc, không phải đề xuất):** các ràng buộc đúng/sai sau:
  - không có hai reviewer giữ cùng lease (NFR-15);
  - adapter không ghi CVAT (FR-SNP-01, B-18);
  - mọi quyết định có audit ghi cùng transaction (FR-SEC-05, B-12);
  - retry không tạo issue trùng (B-10);
  - log có cấu trúc kèm `run_id`, `snapshot_id`, `request_id`, cùng metric hàng đợi Celery, thời gian shard, tỉ lệ lỗi (NFR-12).
- **Đề xuất/TBD:** tên metric, cách thu thập, kênh cảnh báo và mọi **ngưỡng hiệu năng** (SLO-01…04, SLO-09). SRS `08-nonfunctional.tex` ghi rõ: các con số trong bảng NFR là đề xuất khởi điểm, chưa có phép đo làm căn cứ. Theo B-14, ngưỡng nghiệm thu chỉ được chốt sau khi đo pilot trên phần cứng và mạng thật, với điều kiện đo ghi rõ (ảnh 1280×720 JPEG, mạng nội bộ, cache nguội/ấm, số người dùng đồng thời).
- Mục tiêu thời gian QC Run và độ trễ UI: **TBD-13** (Tech Lead, sau đo pilot). Số lần retry/backoff: **TBD-14**. RPO/RTO: **TBD-17**. Thời hạn lease: **TBD-09**.
- Repo **chưa có** hệ thống cảnh báo. Kênh nhận cảnh báo và người trực **chưa xác định**.

## SLO và ràng buộc

| Mã | Chỉ số (SLI) | Mục tiêu | Nguồn | Trạng thái |
|---|---|---|---|---|
| SLO-01 | p95 thời gian mở frame kế tiếp trong Workspace (ảnh + annotation + issue), cache ấm | ≤ 1,5 s | NFR-01 | Đề xuất, TBD-13 |
| SLO-02 | p95 độ trễ API lưu quyết định review | ≤ 500 ms | NFR-02; A (bảng NFR: "Lưu decision p95 ≤ 500 ms") | Đề xuất, TBD-13 |
| SLO-03 | Thời gian QC Run cho 10.000 frame (CPU engine + Detector + xếp hạng) | **TBD-13**, trên phần cứng TBD-02 | NFR-03 | Chưa có số |
| SLO-04 | Tỉ lệ shard kết thúc Failed sau khi hết retry | Chưa có số; đặt sau pilot | NFR-05 | Chưa có số |
| SLO-05 | Số frame có hơn một lease hợp lệ | = 0 mọi lúc | NFR-15 | **Đã chốt** — ràng buộc đúng/sai |
| SLO-06 | Retry tạo issue trùng | = 0 | B-10; R-01 | **Đã chốt** — ràng buộc đúng/sai |
| SLO-07 | Lời gọi ghi tới CVAT | = 0 | B-18; FR-SNP-01 | **Đã chốt** — ràng buộc đúng/sai |
| SLO-08 | Decision/waiver/approval/config publish có AuditEvent | 100% | FR-SEC-05, B-12; A (bảng NFR: "Audit 100%") | **Đã chốt** — ràng buộc đúng/sai |
| SLO-09 | Tuổi của bản sao lưu thành công gần nhất | ≤ RPO (**TBD-17**) | NFR-16 | Chưa có số |

Khả dụng (uptime) của API: SRS **không có** yêu cầu. Không đặt SLO uptime khi chưa có căn cứ.

## Cảnh báo đề xuất

Cảnh báo cho các ràng buộc đã chốt (idempotency, CVAT, lease, audit) là cách **giám sát** yêu cầu đã chốt; tên metric và cơ chế cảnh báo là đề xuất.

Tên metric theo [metrics.md](metrics.md). Ngưỡng ghi "TBD" sẽ được đặt sau khi đo pilot. Không tự đặt số khi chưa có baseline (phiếu chốt B-10: "Chưa đặt số giây/phút khi chưa đo").

| Cảnh báo | Điều kiện | Mức | Hành động gợi ý |
|---|---|---|---|
| Vi phạm idempotency | `labelx_duplicate_issue_on_retry_total` tăng | Nghiêm trọng | Dừng chạy lại; kiểm khoá dedup (B-10) |
| Vi phạm ranh giới CVAT | `labelx_cvat_write_attempts_total` > 0 | Nghiêm trọng | Chặn ngay; rà soát code adapter (B-18) |
| Lease trùng | `labelx_lease_double_holder` > 0 | Nghiêm trọng | Kiểm khoá dòng PostgreSQL cấp lease (NFR-15) |
| Ghi audit lỗi | `labelx_audit_write_failures_total` tăng | Nghiêm trọng | Thao tác đã rollback; kiểm DB/quyền bảng audit |
| Không có worker | `labelx_celery_workers_online{pool}` = 0 trong khi queue tương ứng > 0 | Cao | Khởi động lại worker; task acks late sẽ được giao lại |
| Hàng đợi ứ | `labelx_celery_queue_length` hoặc `labelx_celery_task_wait_seconds` vượt ngưỡng trong N phút | Cảnh báo | Ngưỡng **TBD** sau pilot |
| Shard Failed tăng | Tỉ lệ `labelx_shard_failed_total` / tổng shard vượt ngưỡng | Cảnh báo | Xem `reason`; chạy lại bằng `retry-failed` sau khi sửa nguyên nhân. Ngưỡng **TBD** |
| CVAT lỗi/chậm | `labelx_cvat_request_errors_total` tăng liên tục hoặc p95 độ trễ vượt ngưỡng | Cảnh báo | Kiểm instance CVAT, token (TBD-01) |
| Snapshot drift lặp lại | `labelx_snapshot_lock_total{outcome="drift"}` lặp lại trên cùng scope | Thông tin | Báo QA Lead; xem xét phương án tạm khoá sửa khi export (RK-06) |
| Lưu quyết định chậm | p95 `labelx_decision_save_seconds` vượt SLO-02 | Cảnh báo | Chỉ bật sau khi SLO-02 được chốt |
| Effort bất thường | `labelx_effort_idle_gaps_total` hoặc `labelx_effort_events_rejected_total` tăng đột biến | Thông tin | Báo người phụ trách thí nghiệm effort (RK-05) |
| Sao lưu quá hạn | `time() - labelx_backup_last_success_timestamp` > RPO | Cao | Kiểm job sao lưu (TBD-17) |

## Việc cần làm để chốt

1. Chọn công cụ metric/log/cảnh báo phù hợp hạ tầng (TBD-02), ghi decision.
2. Chạy pilot với điều kiện đo theo B-14, lấy baseline p50/p95.
3. Tech Lead chốt TBD-13, TBD-14; Product Owner chốt TBD-09; Tech Lead chốt TBD-17.
4. Cập nhật bảng SLO và ngưỡng cảnh báo tại đây, kèm link phép đo.

## Liên quan

- [metrics.md](metrics.md)
- [logging.md](logging.md)
- [../08-devops/monitoring.md](../08-devops/monitoring.md)
