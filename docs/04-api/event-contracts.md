---
id: api-event-contracts
title: Hợp đồng Celery task và sự kiện
type: reference
domain: api
module: quality-control
tags: [api, events, celery, idempotency, retry]
priority: 2
---
# Hợp đồng Celery task và sự kiện

## 1. Nguyên tắc

| Nguyên tắc | Nội dung | Nguồn |
|---|---|---|
| Payload chỉ chứa ID | Task chỉ nhận ID và khoá (`snapshot_id`, `run_id`, `work_unit_id`…). Dữ liệu thật đọc từ PostgreSQL hoặc Object Storage. Payload không bao giờ chứa token CVAT hay ảnh | NFR-07; DEC-001 |
| Idempotent | Celery chạy với `acks_late` và `reject_on_worker_lost`, nên một task có thể chạy nhiều lần. Mỗi task kiểm trạng thái trong DB, hoặc ghi với ràng buộc UNIQUE, trước khi tạo tác dụng phụ | settings; FR-AGG-02 |
| Ghi nguyên tử | Candidate, evidence và ledger của một đơn vị nằm trong **một** transaction | FR-AGG-06 |
| Blob trước, metadata sau | Upload lên Object Storage với khoá theo hash nội dung, sau đó mới commit | NFR-06 |
| Retry | `autoretry_for` chỉ áp dụng cho lỗi tạm thời (mạng, timeout CVAT/storage). Số lần thử và backoff: **TBD-14**. Hết lượt thì đơn vị ghi `failed`, không làm hỏng run | NFR-05 |
| Timeout | `soft_time_limit`/`time_limit` đặt riêng cho từng loại task: đọc CVAT, Detector theo lô, VLM. Giá trị cụ thể: đọc CVAT và Detector là **TBD-13** (đo pilot); timeout mỗi lượt VLM (nếu bật) là **TBD-20** | R "Cấu hình vận hành"; SRS `tab:tbd` |
| Huỷ | Task đọc `qc_run.cancel_requested_at` trước khi nhận đơn vị mới. Không dùng `revoke(terminate=True)` để huỷ giữa transaction | SRS state machine QC Run |
| Enqueue sau commit | Mọi chuyển trạng thái trong DB đều được commit trước, rồi mới enqueue task kế tiếp bằng `transaction.on_commit(...)`. Như vậy task không bao giờ chạy khi transaction tạo ra nó đã bị rollback | Yêu cầu thiết kế; R-01 |
| Hoàn tất run | Không dùng chord của Celery. Sau mỗi lần commit đơn vị, task khoá dòng `qc_run` (`SELECT … FOR UPDATE`) và kiểm xem mọi `work_unit` đã ở trạng thái kết thúc chưa. Nếu rồi thì đặt cờ `next_step_enqueued_at` trong cùng transaction và enqueue bước kế tiếp qua `on_commit` | Thiết kế; R-01 |

### An toàn khi worker chết giữa chừng (yêu cầu thiết kế)

Có một khoảng hở: worker có thể chết *sau* khi commit chuyển trạng thái nhưng *trước* khi enqueue xong. Khi đó `on_commit` không chạy, và đối tượng bị kẹt ở trạng thái trung gian (ví dụ snapshot nằm mãi ở `exporting`). Yêu cầu là không để kẹt như vậy. Có hai phương án:

1. **Claim bằng cập nhật có điều kiện + sweeper.** Task nhận cả trạng thái `pending` lẫn trạng thái trung gian (ví dụ `exporting`). Task claim bằng `UPDATE … SET status='exporting', claimed_at=now() WHERE id=:id AND status IN ('pending','exporting')`, rồi xử lý idempotent theo các khoá UNIQUE. Một task beat định kỳ re-enqueue các đối tượng đứng ở trạng thái trung gian quá ngưỡng.
2. **Transactional outbox** (A ADR-04). Lệnh enqueue được ghi vào bảng outbox trong cùng transaction; một relay đọc outbox và gửi sang Celery.

Phương án nào được chọn **cần một decision mới** (DEC). Trong lúc chờ, các task dưới đây được viết theo phương án 1, tức đều chấp nhận chạy lại từ trạng thái trung gian.

Tên task và tên queue dưới đây là **đề xuất đặt tên**. SRS chỉ nêu bước và loại worker, không quy định tên.

## 2. Danh sách task

### 2.1 Snapshot (queue `snapshot`)

| Task | Payload | Khoá idempotent | Hành vi | Retry |
|---|---|---|---|---|
| `snapshots.build_snapshot` | `{snapshot_id}` | `snapshot_id`; claim bằng `UPDATE … WHERE status IN ('pending','exporting')` | Chuyển status sang `exporting`; tạo các dòng `snapshot_job` còn thiếu (`ON CONFLICT DO NOTHING`); enqueue `export_job` qua `on_commit` cho từng job chưa export xong | Không retry; lỗi thì snapshot `failed` (`export_error`) |
| `snapshots.export_job` | `{snapshot_id, cvat_job_id}` | UNIQUE `(snapshot_id, cvat_job_id)` trên `snapshot_job` | Đọc annotation và meta, chuẩn hoá, tính SHA-256; tải ảnh lên `labelx-snapshots` (khoá theo sha256); ghi `frame`, `annotation`; bỏ shape không phải rectangle và đếm `out_of_scope_shapes` | Lỗi tạm thời: TBD-14 |
| `snapshots.verify_and_lock` | `{snapshot_id}` | Chỉ khi mọi `snapshot_job` đã export xong và status = `exporting` | Đọc lại `updated_date` của từng job. Không drift thì `locked` + hash tổng. Có drift thì `failed`/`drift_detected` | Lỗi tạm thời: TBD-14 |

### 2.2 QC Run (queue `cpu`/`gpu`)

| Task | Payload | Khoá idempotent | Hành vi |
|---|---|---|---|
| `qc.start_run` | `{run_id}` | Claim bằng `UPDATE … WHERE status IN ('queued','running')` | Tạo `work_unit` cho mỗi (engine, shard) bằng `INSERT … ON CONFLICT DO NOTHING`; ghi các engine Not checked (`disabled`, `no_model`…) vào ledger; chuyển run sang `running` |
| `engines.run_cpu_unit` | `{work_unit_id}` | `work_unit.idempotency_key` = sha256(snapshot_id, engine, engine_version, config_version, model_checksum, shard_key) | Schema / Geometry / Duplicate trên shard; ghi candidate, evidence và ledger trong 1 transaction. Đơn vị đã `completed` thì bỏ qua |
| `engines.detect_unit` (queue `gpu`) | `{work_unit_id}` | Như trên | Detector theo lô; lưu `prediction` (để tái dùng, NFR-04); xong thì enqueue `engines.match_unit` |
| `engines.match_unit` | `{work_unit_id}` | Như trên (engine = `matching`) | Matching một-một không xét lớp; sinh candidate E1/E2 kèm evidence (crop lên `labelx-evidence`) |
| `qc.finalize_engines` | `{run_id}` | `qc_run.next_step_enqueued_at` | Tổng hợp `engine_result` từ ledger; xác định Completed hoặc Partial |
| `issues.aggregate_run` | `{run_id, policy_version}` | UNIQUE `(run_id, dedup_key)` trên `issue`; UNIQUE `candidate_id` trên `issue_candidate` | Gộp candidate thành issue, tính neo và `n_i` |
| `ranking.score_run` | `{run_id, score_version_id}` | UNIQUE `(run_id, score_version_id, frame_id)` trên `frame_risk` | Tính `s(f)` cho **mọi** frame; phá hoà bằng SHA256(frame_key‖seed); tạo `review_item` cho queue `risk` |
| `ranking.build_random_slice` | `{run_id, seed, rate}` | UNIQUE `(run_id, queue, frame_id)` | Lát ngẫu nhiên `r%` (TBD-10), độc lập với ranking; queue `random` |
| `ranking.build_control_rankings` | `{run_id, kinds, seeds}` | UNIQUE `(run_id, kind, seed, frame_id)` | Ranking đối chứng: ngẫu nhiên và heuristic (FR-RNK-08) |
| `qc.retry_failed` | `{run_id}` | Đặt lại các `work_unit` có status `failed` thành `pending` và tăng `attempt`; giữ nguyên `idempotency_key` | Gọi từ `POST /runs/{id}/retry-failed` |

### 2.3 Rework, đánh giá, báo cáo

| Task | Payload | Khoá idempotent | Hành vi |
|---|---|---|---|
| `review.recheck_rework` | `{rework_id, new_snapshot_id}` | UNIQUE `(rework_id, snapshot_id)` trên `rework_recheck` | Tạo run re-check giới hạn ở frame bị ảnh hưởng (FR-RWK-04) |
| `qc.build_final_run` | `{dataset_id, scope_hash}` | Partial UNIQUE `(dataset_id, scope_hash) WHERE is_final AND status IN ('queued','running')` trên `qc_run` ([schema.md](../05-database/schema.md)) | Snapshot toàn scope, sau đó run `is_final=true`, liên kết các verification (FR-RWK-06) |
| `evaluation.run_evaluation` | `{evaluation_id}` | Status `queued` → `running` | Kiểm rò rỉ dữ liệu (FR-EVL-05); số lỗi trong tập E ≥ E_min; Recall@k, bootstrap ≥ 1000 lần; lưu provenance |
| `reports.export_report` | `{report_id, format}` | Khoá object = sha256 nội dung trong `labelx-reports` | Xuất PDF/CSV/JSON, ghi version snapshot, run, score, reference (FR-RPT-05) |

### 2.4 Định kỳ (django-celery-beat)

| Task | Lịch | Hành vi |
|---|---|---|
| `review.expire_leases` | Đề xuất mỗi phút | Lease quá `expires_at` → `expired`, frame về hàng đợi. Nếu chỉ dựa vào truy vấn cấp lease thì đã đủ đúng; task này chỉ dọn dẹp |
| `gate.expire_waivers` | Đề xuất hằng ngày | Waiver quá `expires_at` → `expired`; điều kiện trở lại chưa đạt (FR-GTE-03) |
| `storage.gc_orphan_blobs` | Đề xuất hằng ngày | Xoá blob không có metadata nào trỏ tới sau `t_gc` (NFR-06). `t_gc`: **TBD-20** |

## 3. Sự kiện domain

SRS **không** quy định event bus hay SSE. A §20 (ADR-04) đề xuất transactional outbox và §25.2 liệt kê domain event (`snapshot.created`, `run.completed`, `issue.decided`, `rework.submitted`…). Trong MVP:

- Thông tin trạng thái được ghi vào bảng nghiệp vụ và `audit_log` trong cùng transaction. Client đọc lại bằng polling GET (`/api/snapshots/{id}`, `/api/runs/{id}`).
- Outbox, SSE và thông báo đẩy **chưa chốt**. Khi cần, phải có quyết định mới. Lúc đó tên event của A có thể được dùng làm điểm khởi đầu.

## 4. Lỗi và trạng thái

| Tình huống | Kết quả |
|---|---|
| Worker chết giữa task | Message được giao lại (`acks_late`); transaction chưa commit thì bị rollback; task chạy lại với cùng khoá |
| Hết retry trên một đơn vị | `work_unit.status=failed`; ledger ghi `failed` cho các đơn vị áp dụng; run Partial; frame mang cờ `missing_evidence` |
| Ảnh hỏng hoặc không đọc được | Ledger ghi `failed` với lý do `media_error`; không reject annotation (SRS `tab:enginestates`) |
| Không có Detector | Engine Mô hình độc lập là Not checked (`no_model`); không sinh ranking giả (FR-ENG-09) |
