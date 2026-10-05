---
id: domain-value-objects
title: Value object của module Quality Control
type: reference
domain: domain
module: quality-control
tags: [domain, value-objects, bbox, risk-score]
priority: 2
---
# Value object của module Quality Control

Value object là giá trị bất biến, so sánh theo nội dung, không có định danh riêng. Các aggregate dùng chúng ở [aggregates.md](aggregates.md); quy tắc tính toán ở [services.md](services.md).

Nguồn chính: SRS [03-data-errors.tex](../label-x_system-requirement-specification/sections/03-data-errors.tex), [06-functional.tex](../label-x_system-requirement-specification/sections/06-functional.tex), [07-evaluation.tex](../label-x_system-requirement-specification/sections/07-evaluation.tex); R [architecture_review.html](../00-project/sources/architecture_review.html). Giá trị chưa chốt ghi mã TBD của SRS [11-traceability.tex](../label-x_system-requirement-specification/sections/11-traceability.tex).

## BBox

- **Biểu diễn**: `(x1, y1, x2, y2)` theo hệ toạ độ pixel ảnh gốc (SRS 09 §Giao diện mô hình). Ảnh BDD100K 1280×720 (SRS 03).
- **Hợp lệ cấu trúc** (Geometry, FR-ENG-03; R B-06):
  - `x1 < x2` và `y1 < y2`.
  - Nằm trong ảnh với dung sai 2 px.
  - Diện tích ≥ 24 px² (rule G-014). Dưới ngưỡng là **cảnh báo cấu trúc**, không tự là lỗi (SRS 03).
- **Không** kiểm độ khít biên (G-009 giữ Not checked khi chưa có biên tham chiếu) (R B-06).
- **Phép toán**: `area()`, `iou(other)`. IoU tính **không xét lớp** khi matching (SRS 03 §Matching).
- Chuẩn hoá toạ độ để hash: làm tròn cố định (FR-SNP-03); số chữ số làm tròn là **TBD-20** — chốt trước khi build adapter, ghi vào version thuật toán chuẩn hoá.

## LabelClass

- Một trong 10 lớp BDD100K: `car`, `truck`, `bus`, `train`, `motorcycle`, `bicycle`, `pedestrian`, `rider`, `traffic light`, `traffic sign` (SRS 03).
- Lớp ngoài taxonomy version của dataset ⇒ cảnh báo Schema/Taxonomy (FR-ENG-02).
- Lớp của Detector phải ánh xạ qua bảng mapping có version; lớp chưa map hiện thiếu coverage, không tự suy tên lớp (R cấu hình MVP "Model artifact/class mapping").

## RevisionHash

- **Định nghĩa**: SHA-256 của JSON annotation đã chuẩn hoá (sắp xếp khoá, toạ độ làm tròn cố định), tính cho từng job và hash tổng của snapshot (FR-SNP-03; R B-02).
- CVAT không có "annotation revision" chính thức; revision là hash do LabelX tính (A §21).
- **Bất biến dùng**: revision CVAT mới phải khác revision gốc mới được nhận "Đã sửa" (FR-RWK-03); quyết định và verification gắn revision cụ thể (FR-REV-10).

## SnapshotScope

- Tập (project, task, job) đã chọn; mapping frame sang job/task/frame nguồn (FR-SNP-05). Shape không phải Bounding box bị đếm "ngoài phạm vi" (FR-SNP-07).

## ImageChecksum và ContentKey

- Checksum ảnh lưu cùng snapshot (FR-SNP-05).
- Blob (ảnh, crop evidence) dùng khoá theo hash nội dung để upload lên Object Storage là idempotent (NFR-06).

## ErrorFamily

Ba nhóm lỗi đo KPI của bản đầu (SRS 03 §Taxonomy nhóm lỗi):

| Mã | Tên | Neo (anchor) của lỗi/issue | Nguồn candidate |
|---|---|---|---|
| E1 | Thiếu box | Lỗi: đối tượng GT. Issue: vùng box dự đoán không ghép (gộp các dự đoán chồng nhau IoU ≥ `τ_m`) | Detector: dự đoán không ghép, confidence ≥ `τ_E1` |
| E2 | Sai lớp | Lỗi: đối tượng GT. Issue: annotation trong cặp ghép khác lớp | Detector: cặp IoU ≥ `τ_m`, lớp khác, confidence ≥ `τ_E2` |
| E3 | Trùng box | Lỗi: annotation dư. Issue: cụm annotation nối nhau bởi cặp IoU ≥ 0,85 | Duplicate/Overlap (D-002); Detector bổ trợ |

- Không thuộc E1–E3 (ghi nhận, ngoài KPI): box thừa không có đối tượng (BR-06), độ khít biên, box quá nhỏ, sai thuộc tính, lỗi track (SRS 03).
- Cảnh báo cấu trúc (Schema/Geometry) là một loại riêng, không phải ErrorFamily.
- Ngưỡng `τ_E1`, `τ_E2` chọn trên tập hiệu chỉnh, có version (FR-ENG-07); `τ_m` là **TBD-05** (SRS đề xuất 0,5, chưa chốt).
- **Mâu thuẫn ghi nhận**: H (AnalysisConfig, RulesThresholds D-002) ghi Duplicate "cùng lớp". SRS FR-ENG-04 sinh candidate cho cặp IoU ≥ 0,85 kèm lớp hai box và dùng "cùng lớp hay khác lớp" làm đặc trưng E3 (FR-RNK bảng đặc trưng); BR-05 không xét lớp của annotation dư. Xử lý: SRS thắng — candidate E3 không lọc theo lớp; "cùng lớp" là đặc trưng.

## Severity

- Ba mức: Nghiêm trọng / Trung bình / Nhẹ (H ReviewWorkspace, RulesThresholds; SRS BR-09).
- Định nghĩa theo lớp và kích thước do QA Lead chốt: **TBD-07**. Dùng cho gate G-2 (lỗi nghiêm trọng chưa đóng = 0) và G-2b.
- Bắt buộc khi Xác nhận lỗi (FR-REV-08).
- Tier P0–P3 của T và bucket High/Medium/Low của A không dùng làm Severity (R B-10).

## DedupKey

- `dedup_key = (snapshot, frame, đối tượng tham chiếu, nhóm lỗi)` kèm version policy gộp (FR-AGG-03; R B-10).
- Đối tượng tham chiếu: annotation ID (E2, E3 — với E3 là cụm), hoặc vùng dự đoán đã gộp (E1).
- Candidate cùng `dedup_key` gộp vào một issue; khác nhóm lỗi trên cùng object là issue riêng.

## IdempotencyKey

- Đơn vị xử lý: `(snapshot, engine, config, model, shard)` (FR-AGG-02). Retry cùng khoá không tạo candidate/issue trùng (AC-02).
- Sự kiện client (effort): `event_id` UUID (SRS 12).

## IssueAnchor và MaxErrorCount (`n_i`)

- Mỗi issue lưu neo và `n_i`: E1 → 1, E2 → 1, E3 (cụm `m` box) → `m − 1` (FR-RNK-12; SRS 06 bảng neo). Quy tắc tạo neo có version cùng policy gộp.

## RiskScore

- **Định nghĩa**: `s(f) = Σ_{i ∈ I_f} n_i·q_i + h(f)` (SRS 06 §Mô hình điểm).
  - `q_i`: xác suất issue trùng ít nhất một lỗi, học ở cấp issue (logistic theo nhóm, có thể hiệu chỉnh isotonic).
  - `h(f) ≥ 0`: điểm nền cho lỗi không có issue (hồi quy Poisson).
- **Đi kèm**: `score_version`, rank, đóng góp từng issue và điểm nền (FR-RNK-05). Phá hoà theo `SHA256(frame_key ‖ seed)` (FR-RNK-04).
- **Bất biến**: score version khoá thì không đổi (FR-RNK-02). `score_v0` dùng khi chưa đủ nhãn — báo cáo phải ghi rõ (SRS 06).
- Chi tiết: [../12-ai/risk-scoring.md](../12-ai/risk-scoring.md).

## CoverageUnit

Đơn vị áp dụng của từng engine trong ledger (R cấu hình MVP "Required units"; B-04):

| Engine | Đơn vị |
|---|---|
| Schema / Taxonomy, Geometry | annotation/shape áp dụng |
| Duplicate / Overlap | frame và cặp so được |
| Mô hình độc lập (Detector) | frame |
| Mô hình thị giác – ngôn ngữ | candidate được trigger |
| Metric | reference scope |

- Bộ đếm: eligible, completed, failed, not checked + lý do (FR-AGG-04). Coverage engine = completed / eligible; không loại đơn vị lỗi khỏi mẫu số.
- Coverage frame chung chỉ là tiến độ xem, không dùng cho gate (FR-RPT-04).

## EngineStatus và ApplicabilityReason

- `EngineStatus ∈ {Running, Checked, Partial, Failed, Not checked}` (FR-AGG-05).
- `ApplicabilityReason ∈ {disabled, no_model, no_reference, not_applicable, not_triggered}` (SRS 05 bảng trạng thái engine).

## ReviewDecisionType

- `{Xác nhận lỗi, Bác bỏ, Chưa chắc chắn, Chuyển cấp trên, Yêu cầu sửa}` (FR-REV-08). Kết luận phân xử: `{Xác nhận lỗi, Bác bỏ, Guideline còn thiếu}` (FR-ESC-02).

## GuidelineRef

- `(rule_id, guideline_version, section)` (R B-13; FR-GDL-01). Ví dụ trên H: `VEH-03 · Guideline v1.2 · mục 3.2` — chỉ minh hoạ.

## Seed

- Seed khoá trước cho: phá hoà ranking, lát kiểm tra ngẫu nhiên (`r` — **TBD-10**), ranking đối chứng ngẫu nhiên, bootstrap, chia D1/D2 và gán chuỗi AB/BA (SRS 06, 07). Seed lưu trong run/manifest (H Snapshot, RulesThresholds).

## EffortActivity

- `{view, issue, adjudicate, recheck, fix}` với `active_ms` (SRS 12). `fix` (t_fix) không cộng vào T của KPI-2, chỉ báo cáo riêng (SRS 07).

## GateThreshold

- Cặp (điều kiện, ngưỡng, nguồn, scope, mẫu số, cỡ mẫu tối thiểu). Giá trị cấu hình pilot: xem [aggregates.md](aggregates.md#15-qualitygateevaluation-gatecondition-và-waiver). Tiêu chí "đủ dữ liệu" cho residual/agreement (cỡ mẫu, khoảng tin cậy) chưa chốt (R B-15).
