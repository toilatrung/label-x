---
id: observability-overview
title: Observability
type: reference
domain: observability
module: repository
tags: [observability, telemetry, operations]
priority: 3
---
# Observability

Log, metric, SLO và cảnh báo cho LabelX. Căn cứ chính: NFR-12 (log có cấu trúc kèm `run_id`, `snapshot_id`, `request_id`; metric hàng đợi Celery, thời gian shard, tỉ lệ lỗi), NFR-01…03, NFR-05, NFR-15 trong SRS `08-nonfunctional.tex`, và phần độ tin cậy vận hành của `docs/00-project/sources/QC_Engine_Review_Report.html` (mục 6).

## Hiện trạng

Repo **chưa có** thành phần observability nào: không có cấu hình `LOGGING` trong Django, không có exporter metric, dashboard hay cảnh báo. Phân biệt hai loại nội dung trong mục này:

- **Đã chốt (yêu cầu bắt buộc):**
  - log có cấu trúc kèm `run_id`, `snapshot_id`, `request_id`; metric hàng đợi Celery, thời gian shard, tỉ lệ lỗi (NFR-12);
  - không có lease trùng (NFR-15);
  - adapter không ghi CVAT (FR-SNP-01, B-18);
  - audit mọi quyết định cùng transaction (FR-SEC-05, B-12);
  - retry không tạo issue trùng (B-10).
- **Đề xuất/TBD:** tên metric cụ thể, trường log bổ sung, công cụ và cách thu thập, kênh cảnh báo, và mọi ngưỡng hiệu năng (**TBD-13**, **TBD-14**).

## Nội dung

- [logging.md](logging.md) — trường log bắt buộc, phân biệt log và audit, danh sách không được log (secret, token CVAT, ảnh).
- [metrics.md](metrics.md) — metric hàng đợi Celery, shard/engine, CVAT adapter, lease, quyết định, quyền, effort, lưu trữ.
- [alerts-and-slo.md](alerts-and-slo.md) — ràng buộc đã chốt, SLO hiệu năng đề xuất (TBD-13) và cảnh báo.

## Liên quan

- [../08-devops/monitoring.md](../08-devops/monitoring.md)
- [../06-security/security-policies.md](../06-security/security-policies.md)
