---
id: api-rest
title: REST API LabelX QC
type: reference
domain: api
module: quality-control
tags: [api, rest, drf, contract, idempotency]
priority: 1
---
# REST API LabelX QC

## 1. Quy ước chung

| Mục | Quy ước | Nguồn |
|---|---|---|
| Kiểu | REST JSON qua Django REST framework; schema OpenAPI sinh bằng drf-spectacular tại `/api/schema/`, giao diện xem tại `/api/docs/` | SRS §9.3; [urls.py](../../src/backend/config/urls.py) |
| Tiền tố | `/api/…`, theo đúng bảng `tab:api` của SRS. A §25 dùng `/api/qc/v1`; tiền tố này **không** được dùng | SRS §9.3 |
| Xác thực | Session đăng nhập LabelX (`SessionAuthentication`). Request ghi phải gửi CSRF token | SRS §9.3; settings `REST_FRAMEWORK` |
| Phân quyền | Mặc định `IsAuthenticated`. Mỗi view còn kiểm vai trò **và** scope dataset; danh sách luôn được lọc theo scope | FR-SEC-01; B-12 |
| Phân trang | `CursorPagination`, `PAGE_SIZE=50` | settings |
| Thời gian | ISO 8601 có múi giờ; server dùng `USE_TZ=True` | settings |
| Tác vụ dài | Trả `202 Accepted` + `id`. Client theo dõi trạng thái bằng GET | SRS §9.3 (POST /snapshots) |
| Audit | Mọi thao tác ghi được audit trong cùng transaction. Lỗi 403 và 409 cũng được audit | FR-SEC-05; SRS §9.3.1 |

Viết tắt vai trò: AN = Annotator, RV = Reviewer, QA = QA Lead, AD = QC Admin, SA = Super Admin. Quyền theo SRS `tab:rbac` và H `WorkflowPermissions.dc.html`.

## 2. Hợp đồng lỗi

Mọi phản hồi lỗi có dạng:

```json
{ "code": "LEASE_CONFLICT", "message": "Lease đã hết hạn hoặc thuộc người khác", "request_id": "…", "details": {} }
```

| HTTP | Ý nghĩa | `code` (đề xuất) | Ví dụ |
|---|---|---|---|
| 400 | Dữ liệu không hợp lệ | `VALIDATION_ERROR` | Bác bỏ thiếu lý do; xác nhận thiếu nhóm lỗi hoặc mức độ |
| 403 | Không có quyền, ngoài scope, hoặc vi phạm tách nhiệm vụ | `FORBIDDEN`, `OUT_OF_SCOPE`, `SELF_REVIEW_FORBIDDEN`, `SAME_REQUESTER_APPROVER`, `IDENTITY_MAPPING_MISSING` | Self-review; người duyệt trùng người đề nghị; ngoài scope; thiếu identity mapping |
| 404 | Không tìm thấy | `NOT_FOUND` | Issue không thuộc snapshot đang xem |
| 409 | Xung đột trạng thái | `LEASE_CONFLICT`, `INVALID_TRANSITION`, `REVISION_UNCHANGED`, `IDEMPOTENCY_KEY_REUSED` | Lease hết hạn; chuyển trạng thái không có trong bảng; báo "Đã sửa" khi hash không đổi |
| 422 | Không đủ điều kiện nghiệp vụ | `BUSINESS_RULE_UNMET`, `INSUFFICIENT_SAMPLE` | Khoá reference khi còn bất đồng chưa phân xử; đánh giá khi số lỗi trong tập E < E_min |

(nguồn: SRS `tab:apierrors`). Giá trị `code` là đề xuất, đặt theo A §25.1 (`LEASE_CONFLICT`, `SELF_REVIEW_FORBIDDEN`). A còn có mã `412 REVISION_DRIFT`; SRS không dùng 412, nên trường hợp này được trả bằng **409** `INVALID_TRANSITION`, kèm `details.drift_jobs`.

## 3. Idempotency

- Mọi `POST` có tác dụng phụ đều nhận header `Idempotency-Key` (UUID do client sinh). Server lưu bộ `(user_id, key, method, path, request_hash, status, response_body)` với UNIQUE `(user_id, key)`.
  - Gửi lại cùng key với cùng body: trả lại đúng phản hồi cũ, không xử lý lần nữa.
  - Gửi lại cùng key với body khác: trả `409 IDEMPOTENCY_KEY_REUSED`.
- Đề xuất: header này là bắt buộc với `POST /api/issues/{id}/decisions`, `…/adjudications`, `/api/rework/*` và `/api/waivers/*`, vì client có thể thử lại sau lỗi mạng (A §27.1, "Lưu decision thất bại"). `/api/effort-events` dùng `client_event_id` thay cho header. Mức "bắt buộc" **chưa có hiệu lực** cho tới khi Tech Lead xác nhận.
- Các thao tác chạy nền (retry shard, huỷ) dựa vào khoá idempotent của `work_unit` (FR-AGG-02), nên không phụ thuộc header này. Xem [event-contracts.md](event-contracts.md).
- A §25 còn đề xuất `If-Match: version` (optimistic concurrency). Đề xuất này **chưa được áp dụng**: SRS dùng lease cùng các guard trong bảng transition. Nếu sau này cần thì phải có quyết định mới.

Ghi chú nguồn: SRS chỉ yêu cầu retry idempotent ở tầng xử lý. Header `Idempotency-Key` là đề xuất thiết kế lấy từ A §25, cần Tech Lead xác nhận.

## 4. Bảng endpoint

### 4.1 Endpoint theo SRS §9.3 (`tab:api`)

| Method | Endpoint | Mô tả | Quyền | Idempotency | Yêu cầu |
|---|---|---|---|---|---|
| POST | `/api/snapshots` | Tạo snapshot cho scope dataset/project/task/job; trả 202 + id | QA, SA (chạy) | Key; trùng scope đang `pending/exporting` → 409 | UC-01; FR-SNP |
| GET | `/api/snapshots/{id}` | Trạng thái, hash từng job, hash tổng, drift | QA, AD, SA | — | FR-SNP-03, 04 |
| POST | `/api/runs` | Tạo QC Run trên snapshot `locked` + config version đã publish | QA, SA | Key | UC-02; FR-ENG-01 |
| GET | `/api/runs/{id}` | Trạng thái run, trạng thái từng engine, `is_final` | QA, AD, RV (xem), SA | — | FR-AGG-05 |
| POST | `/api/runs/{id}/cancel` | Huỷ run ở trạng thái Queued/Running | QA, SA | Gọi lại khi đã Cancelled → 200 | State machine QC Run |
| POST | `/api/runs/{id}/retry-failed` | Chạy lại các đơn vị `failed` | QA, SA | Theo `work_unit.idempotency_key` | FR-AGG-02; NFR-05 |
| GET | `/api/runs/{id}/ledger` | Coverage theo engine: eligible/completed/failed/not checked + lý do | QA, AD, SA | — | FR-AGG-04; FR-RPT-04 |
| GET | `/api/runs/{id}/ranking` | Ranking frame (cursor); lọc theo queue, nhóm lỗi, nguồn | QA, RV, SA; **không** cho người lập GT của tập đánh giá | — | FR-RNK; FR-EVL-02 |
| POST | `/api/queues/{name}/next` | Cấp lease frame kế tiếp; `name` ∈ `risk`, `random` | RV, QA, SA | Nếu đã giữ một lease còn hạn thì trả lại chính lease đó | UC-04; FR-REV-03 |
| POST | `/api/leases/{id}/renew` | Gia hạn lease | Người đang giữ lease | Tự nhiên idempotent | FR-REV-04; TBD-09 |
| GET | `/api/frames/{id}/issues` | Issue và evidence của frame, trạng thái engine, rule áp dụng | RV, QA, SA (theo scope) | — | FR-REV-07 |
| POST | `/api/frames/{id}/complete` | "Đã review xong": kiểm FR-REV-13, trả lease, dừng effort | Người giữ lease | Gọi lại → 200 | FR-REV-13 |
| POST | `/api/issues` | Tạo issue thủ công (`origin=reviewer`) | RV, QA, SA (có lease frame) | Key | FR-REV-09 |
| POST | `/api/issues/{id}/decisions` | Lưu quyết định | RV, QA, SA (ghi đè có lý do) | Key (đề xuất) | UC-05; FR-REV-08, 10, 14 |
| POST | `/api/issues/{id}/adjudications` | Phân xử | QA, SA; khác người đã chuyển cấp | Key (đề xuất) | UC-06; FR-ESC-02, 03 |
| POST | `/api/rework` | Tạo yêu cầu sửa | RV, QA, SA | Key (đề xuất) | FR-RWK-01 |
| POST | `/api/rework/{id}/submitted` | Annotator báo đã sửa; tạo snapshot gia tăng | AN là assignee của yêu cầu, SA | Key (đề xuất); hash không đổi → 409 | FR-RWK-02, 03 |
| POST | `/api/rework/{id}/verify` | Verify đạt hoặc chưa đạt | RV, SA; khác annotator đã sửa | Key (đề xuất) | FR-RWK-05 |
| GET | `/api/guidelines/rules/{rule_id}?version=` | Rule theo guideline version của snapshot, kèm Decision Case | RV, QA, AD, SA | — | FR-GDL-03; UC-12 |
| POST | `/api/references` | Tạo phiên reference; nhập GT (hai bản độc lập) | QA, SA; RV khi được giao lập GT | Key | UC-08; FR-EVL-01 |
| POST | `/api/references/{id}/lock` | Khoá reference | QA, SA; khác người lập GT | Gọi lại khi đã khoá → 200 | FR-EVL-04; FR-SEC-04 |
| POST | `/api/effort-events` | Ghi sự kiện effort theo lô | Người dùng đang review | `client_event_id` UNIQUE | FR-EVL-06 |
| POST | `/api/evaluations` | Chạy đánh giá KPI; trả 202 | QA, SA (UC-09); Product Owner (UC-10) | Key | UC-09, UC-10 |
| GET | `/api/evaluations/{id}` | Kết quả và provenance | QA, AD, SA, Product Owner | — | FR-EVL-14 |
| GET | `/api/runs/{id}/gate` | Kết quả từng điều kiện gate | QA, AD, SA, RV (xem) | — | UC-14; FR-GTE-01, 02 |
| POST | `/api/waivers` | Đề nghị waiver cho một điều kiện gate | RV, QA | Key | FR-GTE-03 |
| POST | `/api/waivers/{id}/approve` | Duyệt hoặc từ chối waiver | QA được cấp quyền, khác người đề nghị | Key | B-11; FR-SEC-04 |
| GET | `/api/reports/{id}?format=` | Xuất báo cáo; `format` ∈ pdf, csv, json | QA, AD, SA đầy đủ; RV xem; AN giới hạn; Product Owner, Data/Model Owner xem | — | FR-RPT-05 |

Ghi chú về Product Owner và Data/Model Owner (SRS ch.6, đoạn dưới `tab:rbac`): hai vai trò này không thao tác review. Quyền của họ: xem báo cáo hiệu quả (UC-11); Product Owner tạo và khoá thiết kế thí nghiệm effort (UC-10, FR-EVL-11); Data/Model Owner khoá artifact Detector. Họ không được làm reviewer trong thí nghiệm do chính mình thiết kế. Hai vai trò này cần được thêm vào `role_assignment` ([schema.md](../05-database/schema.md)).

### 4.2 Endpoint bổ sung (lấy từ A, khớp yêu cầu SRS)

Đây là các endpoint đọc hoặc cấu hình mà SRS yêu cầu chức năng nhưng không liệt kê đường dẫn. Đường dẫn là đề xuất.

| Method | Endpoint | Mục đích | Quyền | Căn cứ |
|---|---|---|---|---|
| GET | `/api/datasets` | Danh sách dataset (CVAT project + version) theo scope | Mọi vai trò có scope | H `Main.dc.html`; A §25; UC-01 |
| GET | `/api/datasets/{id}/tasks?include=jobs` | Cây task/job để chọn scope snapshot | QA, AD, SA | A §25; H `Snapshot.dc.html` |
| GET | `/api/runs?dataset=` | Lịch sử run | QA, AD, SA | H `ExecutionHistory.dc.html` |
| GET | `/api/issues/{id}` | Chi tiết issue, lịch sử quyết định | RV, QA, SA | A §25 |
| GET | `/api/escalations` | Issue Chờ phân xử, kèm quyết định từng reviewer | QA, SA | FR-ESC-01 |
| GET | `/api/rework?assignee=me` | Yêu cầu sửa của tôi | AN | FR-RWK-02; A §25 |
| GET/POST | `/api/config-versions`, `POST /api/config-versions/{id}/publish` | Cấu hình engine, ngưỡng, model có version; bản đã publish không sửa được | AD (sửa), QA (xem) | FR-ENG-01; A §25 |
| GET | `/api/audit?actor=&object=&from=&to=` | Xem audit | AD, SA | FR-SEC-07 |

**Không** triển khai: `/releases*`, `/assistant/query`, `/sample-manifests`, `/calibration-sessions`, `/review-context`, SSE events (A §25). Lý do: ngoài phạm vi M13, hoặc đã bị B-13/FR-GTE-04 loại. Xem [decisions.md](../02-architecture/decisions.md).

## 5. Request/response chính

### 5.1 `POST /api/snapshots`

```json
// request
{ "dataset_id": 3, "scope": { "cvat_task_ids": [118], "cvat_job_ids": [2272, 2273] }, "note": "pilot M13" }
// 202
{ "id": 14, "status": "pending" }
// GET /api/snapshots/14 sau khi xong
{ "id": 14, "status": "locked", "revision_hash": "sha256:…", "parent_snapshot_id": null,
  "jobs": [{ "cvat_job_id": 2272, "job_hash": "sha256:…", "assignee_user_id": 41 }],
  "taxonomy_version": "v3", "guideline_version": "1.2", "out_of_scope_shapes": 0,
  "drift_jobs": [], "locked_at": "2026-10-04T06:50:00+07:00" }
```

Snapshot `failed` trả `failure_reason: "drift_detected"` và danh sách `drift_jobs` (FR-SNP-04).

### 5.2 `POST /api/runs`

```json
// request
{ "snapshot_id": 14, "config_version_id": 7, "seed": 20261004 }
// 201
{ "id": 91, "status": "queued", "is_final": false }
// GET /api/runs/91
{ "id": 91, "status": "partial", "is_final": false, "config_version_id": 7, "seed": 20261004,
  "model_artifact": { "name": "detector", "version": "…", "checksum": "sha256:…" },
  "engines": [
    { "engine": "schema", "status": "checked" },
    { "engine": "detector", "status": "partial", "failed_units": 12 },
    { "engine": "metric", "status": "not_checked", "reason": "no_reference" } ] }
```

Trả 422 nếu snapshot chưa `locked` hoặc config chưa publish.

### 5.3 `POST /api/queues/risk/next`

```json
// request
{ "run_id": 91 }
// 200
{ "lease": { "id": 5512, "frame_id": 428, "expires_at": "…" }, "frame": { "id": 428, "rank": 12, "missing_evidence": false } }
// 204 khi hàng đợi đã hết frame phù hợp
```

### 5.4 `POST /api/issues/{id}/decisions`

```json
// headers: Idempotency-Key: 6f1c…
{ "lease_id": 5512, "decision": "confirm", "family": "E2", "severity": "medium",
  "reason": "Xe tải nhỏ có thùng hàng rời", "rule_id": "VEH-03", "override_reason": null }
// 201
{ "decision_id": 9001, "issue": { "id": 128, "state": "confirmed" }, "audit_id": 77120 }
```

Giá trị `decision` ∈ `confirm`, `reject`, `uncertain`, `escalate`, `request_fix` (FR-REV-08).

| Điều kiện | Mã lỗi |
|---|---|
| `confirm` thiếu `family` hoặc `severity` | 400 |
| `reject`, `uncertain` hoặc `escalate` thiếu `reason` | 400 |
| Reviewer là assignee của job tại snapshot | 403 `SELF_REVIEW_FORBIDDEN` |
| Lease hết hạn hoặc thuộc người khác | 409 `LEASE_CONFLICT` |
| Chuyển trạng thái không có trong bảng | 409 `INVALID_TRANSITION` |

### 5.5 `POST /api/waivers/{id}/approve`

```json
{ "approve": true, "reason": "…" }
```

Trả 403 `SAME_REQUESTER_APPROVER` nếu người duyệt trùng người đề nghị. Waiver phải có `reason`, `evidence_uri` và `expires_at` khi tạo (400 nếu thiếu). Danh sách điều kiện gate được phép waiver và policy từng điều kiện: **TBD-19**. Điều kiện không nằm trong danh sách thì trả 422.

## 6. Bất biến backend kiểm ở mọi endpoint

1. Scope dataset của người gọi. Đối tượng ngoài scope trả **403** `OUT_OF_SCOPE`, theo bảng mã lỗi SRS §9.3.1. Danh sách luôn được lọc theo scope nên không liệt kê đối tượng ngoài scope.
2. Thiếu identity mapping (FR-SEC-02) thì backend **từ chối** (fail closed) mọi thao tác review, phân xử và verify với 403 `IDENTITY_MAPPING_MISSING`, kèm thông báo lỗi cấu hình cho QC Admin. Không ngầm cho qua.
3. Self-review được xác định theo `snapshot_job.assignee_user_id`, thông qua identity mapping (FR-SEC-02, 03).
4. Tách nhiệm vụ: người duyệt khác người yêu cầu (FR-SEC-04).
5. Super Admin ghi đè phải gửi `override_reason`. Audit được gắn nhãn ghi đè, và SA **vẫn** chịu self-review (FR-SEC-06).
6. Người lập GT của tập đánh giá không đọc được ranking, risk score hay candidate của tập đó (FR-EVL-02).
7. Worker Detector không có quyền gọi API ghi quyết định (A ADR-07).
