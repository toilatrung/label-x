---
id: observability-metrics
title: Metrics vận hành LabelX
type: reference
domain: observability
module: repository
tags: [observability, metrics, celery, shard, lease, effort]
priority: 3
---
# Metrics vận hành LabelX

## Yêu cầu nguồn

- **NFR-12**: metric hàng đợi Celery, thời gian shard, tỉ lệ lỗi.
- **NFR-01…03**: độ trễ mở frame, lưu quyết định, thời gian QC Run. Mục tiêu là **TBD-13**.
- **NFR-05**: retry shard có giới hạn với backoff (số lần **TBD-14**); lỗi còn lại ghi Failed cho đơn vị đó.
- **NFR-15**: không có hai reviewer giữ cùng lease.
- **FR-EVL-06**: effort log theo frame và hoạt động; không tính khoảng không thao tác quá \(t_{idle}\) (**TBD-11**).
- **T mục 6**: idempotency key, lưu kết quả từng chunk, retry có giới hạn rồi dead-letter và PARTIAL; budget VLM theo candidate.
- **H ExecutionHistory**: mỗi run hiển thị Coverage, trạng thái từng engine (Checked, Issue found, Partial, Failed, Not checked), thời gian chạy, số candidate trước/sau gộp.

## Hiện trạng

Repo **chưa có** hệ thống metric (không có exporter, Prometheus, StatsD hay dashboard). **Đã chốt** (NFR-12): phải có metric hàng đợi Celery, thời gian shard, tỉ lệ lỗi. Ràng buộc phía sau các metric "phải bằng 0" cũng đã chốt (NFR-15, B-10, B-18, FR-SEC-05). **Đề xuất:** tên metric, label và cách thu thập dưới đây. Chọn công cụ thu thập phụ thuộc hạ tầng (TBD-02) và cần decision nếu thêm thư viện mới (DEC-001).

Hai loại số liệu cần tách bạch:

1. **Metric vận hành** (tài liệu này): sức khoẻ hệ thống, dùng cho cảnh báo.
2. **Số liệu nghiệp vụ/KPI** (Coverage theo engine, Recall@k, effort, residual…): tính từ PostgreSQL, có provenance run/snapshot/version (NFR-14). Đây là chức năng sản phẩm (FR-RPT, FR-EVL), không phải metric giám sát. Metric vận hành có thể phản chiếu một số giá trị để cảnh báo, nhưng **không** là nguồn số liệu hiển thị cho người dùng.

## Danh mục metric đề xuất

Quy ước: tiền tố `labelx_`; label giữ số lượng giá trị thấp. Không dùng `frame_id`, `issue_id` hay `user_id` làm label.

### Hàng đợi và worker Celery (NFR-12)

| Metric | Kiểu | Label | Ý nghĩa |
|---|---|---|---|
| `labelx_celery_queue_length` | gauge | `queue` | Số message chờ trong từng queue (CPU, GPU…; tên queue chưa cấu hình) |
| `labelx_celery_task_total` | counter | `task_name`, `outcome` (`success`/`retry`/`failure`) | Số task theo kết quả |
| `labelx_celery_task_duration_seconds` | histogram | `task_name` | Thời gian chạy task |
| `labelx_celery_task_wait_seconds` | histogram | `queue` | Thời gian từ lúc enqueue đến lúc bắt đầu |
| `labelx_celery_workers_online` | gauge | `pool` (`cpu`/`gpu`) | Số worker đang sống |
| `labelx_celery_task_redelivered_total` | counter | `task_name` | Task bị giao lại (acks late, worker chết) |

### Run, shard và engine (NFR-03, NFR-05, B-10)

| Metric | Kiểu | Label | Ý nghĩa |
|---|---|---|---|
| `labelx_shard_duration_seconds` | histogram | `engine` | Thời gian xử lý một shard |
| `labelx_shard_attempts_total` | counter | `engine`, `outcome` (`checked`/`retry`/`failed`) | Số lần thử shard |
| `labelx_shard_failed_total` | counter | `engine`, `reason` (`timeout`/`media`/`mapping`/`stale`/`other`) | Shard hết retry, ghi Failed. Nhóm lý do theo T: "System / execution failure", không tính là lỗi annotation |
| `labelx_run_duration_seconds` | histogram | `final_status` | Thời gian QC Run (NFR-03, mục tiêu TBD-13) |
| `labelx_run_engine_status_total` | counter | `engine`, `status` (`checked`/`issue_found`/`partial`/`failed`/`not_checked`) | Phân bố trạng thái engine sau run |
| `labelx_candidates_total` | counter | `engine` | Candidate thô sinh ra |
| `labelx_candidates_deduplicated_total` | counter | `engine` | Candidate bị gộp vào issue có sẵn |
| `labelx_duplicate_issue_on_retry_total` | counter | — | Phải luôn bằng 0. Khác 0 nghĩa là vi phạm idempotency (B-10) |
| `labelx_detector_inference_seconds` | histogram | `model_version` | Thời gian suy luận theo lô (metadata bắt buộc của giao diện mô hình, SRS 09) |
| `labelx_vlm_budget_exhausted_total` | counter | — | Chỉ khi VLM được bật (TBD-08): candidate không kiểm do hết hạn mức (B-08) |

**Dead-letter.** T đề xuất đưa đơn vị hết retry vào dead-letter queue. SRS (NFR-05) chỉ yêu cầu ghi Failed cho đơn vị đó và không làm hỏng run. Celery + Redis không có dead-letter sẵn. Đề xuất: coi danh sách shard Failed trong ledger là "dead-letter". Gauge `labelx_shard_failed_pending` đếm shard Failed chưa được chạy lại bằng `POST /api/runs/{id}/retry-failed`.

### CVAT adapter và snapshot

| Metric | Kiểu | Label | Ý nghĩa |
|---|---|---|---|
| `labelx_cvat_request_duration_seconds` | histogram | `operation` (`list_jobs`/`annotations`/`frame_meta`/`frame_data`/`labels`) | Độ trễ gọi CVAT (chỉ đọc) |
| `labelx_cvat_request_errors_total` | counter | `operation`, `status_class` (`4xx`/`5xx`/`timeout`) | Lỗi gọi CVAT |
| `labelx_cvat_write_attempts_total` | counter | — | Phải luôn bằng 0 (B-18). Chỉ có ý nghĩa nếu adapter có lớp chặn method ghi |
| `labelx_snapshot_lock_total` | counter | `outcome` (`locked`/`drift`/`error`) | Kết quả khoá snapshot (FR-SNP-04) |
| `labelx_snapshot_drift_jobs` | histogram | — | Số job drift mỗi lần khoá thất bại |

### Review: lease, quyết định, quyền (NFR-02, NFR-15, FR-REV)

| Metric | Kiểu | Label | Ý nghĩa |
|---|---|---|---|
| `labelx_leases_active` | gauge | `queue` | Lease đang giữ |
| `labelx_lease_expired_total` | counter | `queue` | Lease hết hạn, frame về hàng đợi (thời hạn TBD-09) |
| `labelx_lease_conflict_total` | counter | — | Từ chối 409 vì lease hết hạn/thuộc người khác (FR-REV-14) |
| `labelx_lease_double_holder` | gauge | — | Số frame có hơn một lease hợp lệ. Phải bằng 0 (NFR-15) |
| `labelx_decision_save_seconds` | histogram | — | Độ trễ API lưu quyết định (NFR-02) |
| `labelx_permission_denied_total` | counter | `reason` (`self_review`/`separation_of_duties`/`out_of_scope`/`role`) | Số lần từ chối 403 |
| `labelx_review_queue_depth` | gauge | `queue` (`risk`/`random`) | Frame chưa review theo hàng đợi (FR-REV-01) |

### Effort (FR-EVL-06)

| Metric | Kiểu | Label | Ý nghĩa |
|---|---|---|---|
| `labelx_effort_events_ingested_total` | counter | `activity` | Sự kiện effort nhận qua `POST /api/effort-events` |
| `labelx_effort_events_rejected_total` | counter | `reason` | Batch effort lỗi/bị loại |
| `labelx_effort_idle_gaps_total` | counter | — | Khoảng không thao tác vượt \(t_{idle}\) bị loại (TBD-11). Tăng đột biến có thể là bỏ máy/mở nhiều tab (RK-05) |
| `labelx_frame_open_seconds` | histogram (đo ở client) | `cache` (`warm`/`cold`) | Thời gian mở frame kế tiếp (NFR-01, đo log client) |

### Dữ liệu và lưu trữ

| Metric | Kiểu | Ý nghĩa |
|---|---|---|
| `labelx_audit_write_failures_total` | counter | Phải bằng 0. Audit cùng transaction nên ghi lỗi thì thao tác cũng rollback; số này đếm số lần rollback vì audit |
| `labelx_orphan_blobs_deleted_total` | counter | Blob không có metadata được job dọn dẹp xoá sau \(t_{gc}\) (NFR-06) |
| `labelx_backup_last_success_timestamp` | gauge | Lần sao lưu thành công gần nhất (NFR-16, RPO TBD-17) |

## Liên quan

- [logging.md](logging.md)
- [alerts-and-slo.md](alerts-and-slo.md)
