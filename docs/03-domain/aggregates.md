---
id: domain-aggregates
title: Aggregate của module Quality Control
type: reference
domain: domain
module: quality-control
tags: [domain, aggregates, invariants, state-machine]
priority: 1
---
# Aggregate của module Quality Control

Tài liệu mô tả các aggregate (gốc nhất quán) của LabelX — module Quality Control quanh CVAT, phạm vi M13 (Reviewer Prioritization) trên ảnh BDD100K, Bounding box. Mỗi aggregate có: trách nhiệm, thuộc tính chính, invariant, vòng đời và trạng thái công khai.

Ký hiệu nguồn:

- **R**: [architecture_review.html](../00-project/sources/architecture_review.html) — quyết định B-01…B-21, cấu hình MVP, mục tiêu R-01…R-07 (đã chốt).
- **SRS**: [sections/](../label-x_system-requirement-specification/sections/) — đặc biệt [03-data-errors.tex](../label-x_system-requirement-specification/sections/03-data-errors.tex), [05-dynamics.tex](../label-x_system-requirement-specification/sections/05-dynamics.tex), [06-functional.tex](../label-x_system-requirement-specification/sections/06-functional.tex).
- **H**: màn hình chuẩn hành vi trong [docs/design/screens/](../design/screens/).
- **A/T**: [Quality_Control_Review_UX_Architecture.html](../00-project/sources/Quality_Control_Review_UX_Architecture.html), [QC_Engine_Review_Report.html](../00-project/sources/QC_Engine_Review_Report.html) — chỉ dùng khi không mâu thuẫn R/SRS/H.

Thứ tự ưu tiên khi mâu thuẫn: R và SRS > H > A/T > B. Value object dùng trong các aggregate ở [value-objects.md](value-objects.md); quy tắc tính toán liên aggregate ở [services.md](services.md).

## 1. Nguyên tắc chung

| Mã | Nguyên tắc | Nguồn |
|---|---|---|
| P-01 | CVAT là hệ thống nguồn annotation và là editor duy nhất. Không aggregate nào của LabelX ghi annotation ngược vào CVAT. | R B-18; SRS FR-SNP-01 |
| P-02 | Mọi kết quả phân tích gắn với một `Snapshot` và một `QualityControlRun`; mọi quyết định gắn actor, revision, lý do. | SRS 03 §Mô hình dữ liệu khái niệm |
| P-03 | `Candidate` (phát hiện thô của engine) và `Issue` (đơn vị công việc review) là hai aggregate riêng; quyết định không ghi đè candidate. | R B-10; SRS FR-AGG-01 |
| P-04 | Trạng thái công khai giữ theo H; lý do áp dụng (applicability) lưu riêng. Not checked / Partial / Failed không bao giờ được hiển thị hay tính là đạt. | R B-19; SRS FR-AGG-05 |
| P-05 | AI (Detector, VLM nếu bật) chỉ được ghi `Candidate` và `Evidence`; không có đường ghi `ReviewDecision`, phân xử, gate hay waiver. | R R-02; A ADR-07 |
| P-06 | Bản ghi lịch sử (snapshot đã khoá, candidate, decision, audit, reference đã khoá, evaluation run) là bất biến; thay đổi tạo bản ghi/version mới. | SRS FR-SNP-06, BR-13, FR-SEC-05 |

## 2. Bản đồ aggregate

```
Dataset 1─* Snapshot 1─* QualityControlRun 1─* EngineResult (ledger)
                │                 │
                │                 ├─* Candidate *─1 Issue 1─* ReviewDecision
                │                 │                   │
                │                 │                   ├─0..1 ReworkRequest ─▶ Snapshot (revision đã sửa)
                │                 │                   └─0..1 Lease
                │                 └─* FrameRisk (1 / frame / run)
                └─* Reference (GT + tập lỗi E) ─▶ EvaluationRun
QualityGateEvaluation 1─* GateCondition 1─0..1 Waiver
Experiment 1─* EffortLog          GuidelineVersion 1─* DecisionCase, GuidelineGap
AuditLog (append-only) ─▶ mọi aggregate trên
```

## 3. Dataset

- **Trách nhiệm**: ngữ cảnh làm việc chung. Dataset = CVAT Project + Version (nguồn: H Main.dc.html).
- **Thuộc tính**: `cvat_project_id`, `taxonomy_version`, `guideline_version`, scope quyền theo dataset (SRS 03; FR-SEC-01).
- **Invariant**:
  - LabelX chỉ đọc cấu trúc Project/Task/Job/Frame từ CVAT (H Main; R B-18).
  - Taxonomy phạm vi M13 là 10 lớp 2D detection của BDD100K (`car`, `truck`, `bus`, `train`, `motorcycle`, `bicycle`, `pedestrian`, `rider`, `traffic light`, `traffic sign`) (SRS 03 bảng lớp). Con số "12 lớp" và "Project #31" trên mockup H không phải dữ liệu thật (R cấu hình MVP).
- **Vòng đời**: đồng bộ từ CVAT; không có trạng thái nghiệp vụ riêng trong MVP.

## 4. Snapshot

- **Trách nhiệm**: khoá một phiên bản annotation để kiểm tra và tái lập (R B-02; SRS FR-SNP-03…07).
- **Thuộc tính**: `revision_hash` (hash tổng) và hash từng job ([Revision hash](value-objects.md#revisionhash)), ảnh + checksum, mapping frame (job/task/frame nguồn), `assignee_map` từng job tại thời điểm snapshot, taxonomy version, guideline version, `created_by`, `locked_at`, `parent_snapshot`, seed lấy mẫu (H Snapshot.dc.html).
- **Invariant**:
  - Snapshot đã khoá là bất biến; annotation đổi tạo snapshot mới có `parent_snapshot` (FR-SNP-06; H Snapshot).
  - Chỉ khoá khi không có drift: đọc lại thông tin cập nhật của từng job trước khi khoá; khác lần đọc đầu thì không khoá, không tạo snapshot một phần (FR-SNP-04; UC-01 4a).
  - Shape không phải Bounding box bị bỏ qua và đếm là "ngoài phạm vi" (FR-SNP-07).
  - `assignee_map` là căn cứ kiểm self-review cho mọi quyết định trên snapshot (R B-12; FR-SNP-05).
- **Vòng đời** (SD-1, SRS 05):

| Trạng thái | Ý nghĩa | Chuyển tiếp |
|---|---|---|
| Pending | Đã tạo bản ghi, worker đang export/hash | → Locked (không drift) · → Failed (drift hoặc CVAT lỗi) |
| Locked | Bất biến, dùng được cho QC Run | Không chuyển tiếp; thay đổi tạo snapshot mới |
| Failed | `DriftDetected` hoặc CVAT không phản hồi/từ chối quyền; không ảnh hưởng snapshot cũ | Thử lại bằng snapshot mới |

- **Biến thể**: snapshot gia tăng chỉ cho job bị ảnh hưởng bởi rework (FR-SNP-09, Should); snapshot toàn phạm vi trên revision đã sửa trước QC run cuối (FR-RWK-06; R B-03).

## 5. QualityControlRun (QC Run)

- **Trách nhiệm**: một lần chạy các engine trên một snapshot với cấu hình có version (UC-02).
- **Thuộc tính**: snapshot, config version, seed, version từng engine, model artifact + checksum, người chạy, thời điểm (FR-ENG-01); `status`, `is_final`; tập `EngineResult` (ledger từng engine).
- **Invariant**:
  - Run chỉ tham chiếu snapshot đã khoá và cấu hình có version; engine đọc snapshot đã export, không đọc CVAT live (R B-01/B-02; A ADR-02).
  - Cùng snapshot, config, score version, seed ⇒ candidate, issue, ranking giống hệt (FR-RNK-03; R R-01).
  - Ghi candidate, evidence và cập nhật ledger của một shard trong cùng transaction (FR-AGG-06).
  - Run gốc giữ nguyên để kiểm toán khi có run cuối; không sửa kết quả lịch sử (R B-03; FR-RWK-06).
  - Chỉ một run được đánh dấu `is_final` cho phạm vi đang dùng cho báo cáo/gate; báo cáo/gate chỉ trỏ run cuối khi run cuối Completed và coverage engine bắt buộc đạt (FR-RWK-08).
- **Vòng đời** (SRS 05 §Trạng thái QC Run):

| Từ | Đến | Sự kiện |
|---|---|---|
| — | Queued | Tạo run |
| Queued | Running | Worker nhận |
| Running | Completed | Mọi shard ok |
| Running | Partial | Có shard lỗi sau retry |
| Running | Failed | Lỗi toàn cục |
| Queued / Running | Cancelled | Huỷ: dừng nhận shard mới, giữ kết quả đã xong (UC-02) |
| Partial | Running | Chạy lại shard lỗi |

- **Hiển thị**: H (ExecutionHistory, Main) gắn nhãn "Checked" cho run hoàn tất; domain dùng tên SRS `Completed`, UI ánh xạ nhãn theo H (B-19). Các trạng thái `Draft/Snapshotting/Published/Archived` của A không thuộc MVP.

## 6. EngineResult và Coverage ledger (thuộc QC Run)

- **Trách nhiệm**: ghi theo từng engine: đơn vị áp dụng, số đơn vị eligible, completed, failed, not checked, kèm lý do ([CoverageUnit](value-objects.md#coverageunit)) (FR-AGG-04; R B-04).
- **Sáu engine giữ đúng tên H** (R B-16): Schema / Taxonomy, Geometry, Duplicate / Overlap, Mô hình độc lập (Detector), Mô hình thị giác – ngôn ngữ (VLM), Metric.
- **Trạng thái công khai** (SRS 05 §Trạng thái engine; FR-AGG-05): `Running`, `Checked`, `Partial`, `Failed`, `Not checked`.

| Trạng thái | Lý do lưu trong ledger | Ảnh hưởng |
|---|---|---|
| Checked | Mọi đơn vị áp dụng đã xong | Dùng cho ranking, coverage |
| Partial | Một số đơn vị Failed/chưa xong | Frame thiếu kết quả mang cờ "thiếu bằng chứng" (FR-RNK-06) |
| Failed | Lỗi thực thi (timeout, ảnh hỏng, worker lỗi) sau retry | Không pass, không reject annotation; cho chạy lại |
| Not checked | `disabled`, `no_model`, `no_reference`, `not_applicable` | Không pass; coverage engine bắt buộc chưa đạt |
| Not checked | `not_triggered` (candidate không thoả điều kiện kiểm chọn lọc) | Khác lỗi thực thi; không vào mẫu số kiểm chọn lọc |

- **Invariant**: không loại đơn vị lỗi khỏi mẫu số (B-04); `NOT_REQUIRED`, `abstain`, `EXCEPTION_APPROVED` của T không là trạng thái công khai — chỉ là lý do trong ledger hoặc gắn waiver (B-19).
- **Mâu thuẫn ghi nhận**: H ExecutionHistory hiện nhãn "Issue found" cho Geometry/Duplicate. SRS FR-AGG-05 không có trạng thái này. Xử lý: domain coi là `Checked` có số candidate > 0; nhãn hiển thị "Issue found" là lựa chọn UI, không phải trạng thái riêng (SRS > H).

## 7. Candidate

- **Trách nhiệm**: phát hiện thô, bất biến của một engine (FR-AGG-01).
- **Thuộc tính**: run, engine + version, frame, đối tượng tham chiếu (annotation, hoặc vùng dự đoán với E1), nhóm lỗi dự kiến ([ErrorFamily](value-objects.md#errorfamily)), đặc trưng, score, [`dedup_key`](value-objects.md#dedupkey), evidence (FR-ENG-08: box và lớp dự đoán, confidence, IoU, cặp ambiguous, crop, rule liên quan).
- **Invariant**:
  - Không bao giờ bị sửa sau khi ghi (FR-AGG-01).
  - Retry cùng khoá idempotent không tạo candidate trùng (FR-AGG-02).
  - Candidate chỉ là nghi vấn; không tự trở thành lỗi đã xác nhận (R R-02; H ModelsGuidelines).
  - Cảnh báo cấu trúc (Schema/Geometry) vào hàng đợi và có thể đóng góp điểm rủi ro, nhưng không phải nhóm lỗi đo KPI (SRS 03).
- **Vòng đời**: chỉ có tạo; không có trạng thái.

## 8. Issue

- **Trách nhiệm**: đơn vị công việc review, gom một hay nhiều candidate cùng `dedup_key`, hoặc tạo thủ công từ Frame Review (nguồn = "reviewer") (FR-AGG-03, FR-REV-09).
- **Thuộc tính**: nhóm lỗi, [mức độ](value-objects.md#severity), trạng thái, `lease_owner`, ưu tiên, neo và `n_i` (FR-RNK-12), danh sách candidate, nguồn.
- **Invariant**:
  - Một issue = một (snapshot, frame, đối tượng tham chiếu, nhóm lỗi) theo version policy gộp (FR-AGG-03; BR-08). Gộp không thay đổi tập lỗi reference.
  - Không issue nào được xác nhận hoặc đóng mà không có quyết định của người (AC-04).
  - Mọi chuyển trạng thái phải có trong bảng transition; chuyển ngoài bảng bị từ chối (409) (R B-17; SRS 05 §Bảng chuyển trạng thái).
  - Chỉ chuyển Đã đóng sau verify đạt trên revision đã sửa, người verify khác annotator đã sửa (FR-RWK-05).
- **Trạng thái công khai** (theo H, SRS 05 Hình State machine Issue):

| Từ | Đến | Event | Actor | Guard chính |
|---|---|---|---|---|
| Chờ review | Đang review | claim | Reviewer | Quyền Review trong scope; không là assignee tại snapshot; chưa có lease khác còn hạn |
| Đang review | Chờ review | lease_expired | Hệ thống | Hết hạn lease (TBD-09); chưa có quyết định |
| Đang review | Đã xác nhận | confirm | Reviewer | Có nhóm lỗi, mức độ; lease còn hạn; không self-review |
| Đang review | Bác bỏ | reject | Reviewer | Có lý do; lease còn hạn; không self-review |
| Đang review | Chờ phân xử | uncertain / escalate | Reviewer | Có lý do; lease còn hạn; không self-review |
| Chờ phân xử | Đã xác nhận / Bác bỏ | adjudicate | QA Lead | Khác người chuyển cấp; có rule và lý do |
| Chờ phân xử | Chờ phân xử | guideline_gap | QA Lead | Tạo Guideline Gap; chờ guideline version mới |
| Đã xác nhận | Chờ sửa | request_fix | Reviewer, QA Lead | Có annotator, việc cần sửa, hạn |
| Chờ sửa | Chờ kiểm lại | fix_submitted | Annotator | Là assignee yêu cầu; revision CVAT mới khác revision gốc |
| Chờ kiểm lại | Đã đóng | verify_pass | Reviewer | Re-check xong; người verify ≠ annotator đã sửa |
| Chờ kiểm lại | Mở lại | verify_fail | Reviewer | Có lý do; người verify ≠ annotator đã sửa |
| Mở lại | Chờ sửa | request_fix | Hệ thống | Tự động |
| (như trên) | (như trên) | override | Super Admin | Bắt buộc lý do, audit gắn nhãn ghi đè; vẫn chịu self-review và tách nhiệm vụ |

- **Ngoài phạm vi MVP**: trạng thái `Known defect`, `Superseded`, `On Hold (Guideline)` của A và lifecycle `OPEN…ESCALATED` / `FIX_SUBMITTED…REOPENED` của T không dùng làm trạng thái công khai; khi cần, ánh xạ về bảng trên (B-17, B-19).

## 9. Lease (thuộc Issue/Frame)

- **Invariant**: tại mọi thời điểm, một frame có tối đa một lease còn hạn; cấp lease nguyên tử (một transaction, khoá dòng) (UC-04 3c; NFR-15). Lease có thời hạn và gia hạn khi có thao tác — giá trị **TBD-09** (A đề xuất 15 phút, chưa chốt; không dùng).
- **Trạng thái review của frame** (SRS 05): Chưa review → Đang review (có lease) → Đã review → (Còn issue chờ phân xử/sửa) → Hoàn tất (run cuối). Lease hết hạn đưa frame về Chưa review.

## 10. ReviewDecision

- **Trách nhiệm**: quyết định của người trên một issue (FR-REV-08).
- **Giá trị**: Xác nhận lỗi, Bác bỏ, Chưa chắc chắn, Chuyển cấp trên, Yêu cầu sửa (H ReviewWorkspace).
- **Thuộc tính**: actor, quyết định, nhóm lỗi + mức độ (khi xác nhận), lý do, rule ID, revision, `started_at`, `ended_at` (SRS 03 ERD; FR-REV-10).
- **Invariant**:
  - Ghi cùng audit trong một transaction (FR-REV-10; B-12).
  - Từ chối khi lease hết hạn/thuộc người khác (409) hoặc reviewer là assignee tại snapshot (403), kể cả mở trực tiếp bằng URL (FR-REV-14).
  - Bất biến: quyết định mới là bản ghi mới, không sửa bản cũ (A §22; P-06).
  - Snapshot bị thay bởi revision mới trong lúc review: quyết định vẫn gắn revision cũ, hệ thống cảnh báo (UC-05).
- **Phân xử (Adjudication)** là một ReviewDecision của QA Lead, kết luận Xác nhận lỗi / Bác bỏ / Guideline còn thiếu; được lưu thành `DecisionCase` có version để tra cứu (FR-ESC-02…04).

## 11. ReworkRequest

- **Trách nhiệm**: yêu cầu sửa lỗi đã xác nhận trên CVAT (UC-07).
- **Thuộc tính**: issue, việc cần sửa, annotator (assignee), hạn, mức độ, deep link, revision gốc, `fixed_revision`, `verified_by` (FR-RWK-01; SRS 03 ERD).
- **Invariant**:
  - Annotator chỉ thấy yêu cầu của mình; sửa trên CVAT, bấm "Đã sửa" trên LabelX (FR-RWK-02).
  - "Đã sửa" tạo snapshot mới cho job bị ảnh hưởng; revision không đổi thì từ chối "chưa có thay đổi" (FR-RWK-03).
  - Re-check engine liên quan trên frame đã sửa trước khi verify (FR-RWK-04).
  - Snapshot gốc giữ nguyên (H ReworkTracking).
- **Trạng thái công khai** (H ReworkTracking): Chờ sửa → Chờ xác minh → Đã đóng; verify chưa đạt → Mở lại → Chờ sửa.
- **Kết thúc phạm vi**: khi mọi yêu cầu trong phạm vi đã đóng, tạo snapshot toàn phạm vi và QC run cuối (`is_final`) liên kết các verification trước đó (FR-RWK-06; R B-03). Run cuối Partial/Failed/Cancelled hoặc có issue mới ⇒ gate chưa đạt (FR-RWK-08).

## 12. Reference (GT và tập lỗi E)

- **Trách nhiệm**: đáp án đúng độc lập để đo KPI và Metric engine (R B-05, B-20; SRS 03 §Reference).
- **Thành phần**: (1) annotation chuẩn (GT) cho **toàn bộ** tập đánh giá; (2) tập lỗi `E` suy ra tất định từ GT so với annotation đang review (BR-01…BR-07), rồi được duyệt.
- **Thuộc tính**: `ref_version`, GT version, snapshot đầu vào, mapping GT–annotation (`mapping_ver`), `τ_m`, `a_min`, version thuật toán matching, tỉ lệ khớp hai bản GT trước phân xử (BR-11, BR-13).
- **Invariant**:
  - Người xác minh mù với công cụ: không xem ranking, risk score, candidate của tập đánh giá (BR-10; FR-EVL-02).
  - Hai người gán GT độc lập toàn bộ frame; không khớp thì QA Lead phân xử (BR-11). Người xác minh không xác minh annotation của mình (BR-12).
  - Khoá cùng nhau GT, snapshot, mapping, ngưỡng, version thuật toán; sửa sau khoá tạo version mới có lý do (BR-13).
  - Bác lỗi do matching sai ⇒ sửa mapping rồi suy lại `E`, không xoá lỗi trực tiếp (BR-14).
  - Lỗi chèn có kiểm soát (nếu dùng — **TBD-04**) chỉ là bổ sung, gắn cờ riêng và báo cáo tách khỏi lỗi tự nhiên (BR-15).
  - Case phân xử dùng hiệu chỉnh guideline tách khỏi GT held-out (BR-16).
  - Detector **không** phải Ground Truth, không làm trọng tài (BR-17; B-05).
  - Khoá reference khi còn bất đồng chưa phân xử bị từ chối (422) (SRS 09 bảng mã lỗi).
- **Vòng đời**: Đang lập (hai bản GT) → Phân xử phần không khớp → Suy ra `E` → Duyệt (có thể suy lại) → Đã khoá (H Benchmark: "Đã khoá", "Đang duyệt", "Đã thay thế"). Tên trạng thái nội bộ chi tiết chưa chốt trong SRS; dùng nhãn H.
- **Còn mở**: TBD-03 (danh sách ảnh, N), TBD-04 (nguồn annotation, lỗi chèn), TBD-05 (`τ_m`, `τ_amb`), TBD-06 (`a_min`, quy tắc ignore). Reference thực tế **chưa có** (R B-05).

## 13. EvaluationRun

- **Trách nhiệm**: một lần đo KPI/metric có provenance (UC-09, UC-10; FR-EVL-14).
- **Thuộc tính**: snapshot, run, score version, reference version, thí nghiệm (nếu có), tham số (`k`, B bootstrap, seed), thời điểm, người chạy, kết quả kiểm chống rò rỉ (FR-EVL-05).
- **Invariant**:
  - Chỉ chạy trên reference đã khoá; `|E| < E_min` ⇒ "không đủ mẫu", không kết luận (FR-EVL-10; TBD-K4).
  - Từ chối dùng held-out để học tham số điểm; Detector có ảnh huấn luyện giao với held-out ⇒ chặn đánh giá (FR-EVL-05; AS-03).
  - Kết quả bất biến; đổi tham số tạo evaluation run mới, kết quả cũ vẫn được báo cáo (SRS 07 §Đăng ký trước).
- Chi tiết phép đo: [../12-ai/evaluation.md](../12-ai/evaluation.md).

## 14. Experiment và EffortLog

- **Experiment**: thí nghiệm effort baseline/assisted theo thiết kế chéo AB/BA; khoá trước seed chia D1/D2, gán chuỗi, `k*`, `r`, `t_idle`, cỡ mẫu, `δ`, `δ_fp` (FR-EVL-11; SRS 07 §Đăng ký trước). Không đổi sau khi bắt đầu.
- **EffortLog**: sự kiện effort `event_id` (UUID, idempotent), actor, `experiment_id`, `arm`, frame, issue, `activity` (`view`, `issue`, `adjudicate`, `recheck`, `fix`), `started_at`/`ended_at` theo đồng hồ server, `active_ms`, `outcome` (SRS 12 Phụ lục effort log).
- **Invariant**: thời gian gán đúng một hoạt động; khoảng không thao tác quá `t_idle` (TBD-11) không tính; issue chỉ được xếp `t_tp`/`t_fa` sau khi có kết luận cuối (SRS 07, 12).

## 15. QualityGateEvaluation, GateCondition và Waiver

- **Trách nhiệm**: tính từng điều kiện gate trên QC run cuối; M13 chỉ hiển thị kết quả gate, không phát hành dataset (FR-GTE-01…04).
- **Điều kiện cấu hình khởi điểm pilot** (R cấu hình MVP; H RulesThresholds): coverage engine bắt buộc ≥ 95% (mẫu số theo ledger), lỗi nghiêm trọng chưa đóng = 0, rework bắt buộc verify 100%, residual ≤ 5%, đồng thuận reviewer ≥ 90%. Đây là cấu hình pilot, **chưa** là cam kết nghiệm thu.
- **Invariant GateCondition**: mỗi điều kiện có nguồn, scope, mẫu số, cỡ mẫu; thiếu dữ liệu hoặc engine bắt buộc Not checked/Partial/Failed ⇒ "chưa đạt" (FR-GTE-02; B-15). Hệ thống không tự quyết định phát hành (H QualityGate).
- **Waiver** (R B-11; FR-GTE-03, Should):
  - Phạm vi theo H: Coverage, Lỗi nghiêm trọng, Rework — nhưng được miễn hay không do **policy từng điều kiện**. Danh sách điều kiện được miễn và policy từng điều kiện: **TBD-19** (Product Owner, QA Lead; trước pilot).
  - Bắt buộc lý do, evidence, người chịu trách nhiệm, hạn hiệu lực; người duyệt khác người yêu cầu, không dùng tài khoản khác của cùng người (FR-SEC-04).
  - Chỉ hiệu lực sau duyệt; hết hạn ⇒ điều kiện trở lại chưa đạt; waiver không đổi trạng thái engine, chỉ gate ghi "miễn có điều kiện" kèm hạn (SRS 05 bảng trạng thái engine).
  - Vòng đời khái niệm: Đã đề nghị → Đã duyệt / Bị từ chối → Hết hạn. Tên trạng thái chưa chốt trong H/SRS.

## 16. Guideline, DecisionCase và GuidelineGap

- **GuidelineVersion**: rule ID, section, nội dung trích; soạn và duyệt ở nơi khác, LabelX chỉ lưu version (FR-GDL-01; H ModelsGuidelines). Mapping (nhóm lỗi, lớp, cặp lớp) → rule ID do QC Admin cấu hình (FR-GDL-02).
- **DecisionCase**: phân xử đã duyệt, có version, tra cứu theo rule (FR-ESC-04; B-13).
- **GuidelineGap**: gắn rule; issue liên quan chờ đến khi có guideline version mới (FR-ESC-05).
- **Invariant**: tra cứu trực tiếp rule ID + version + section + case; không RAG (FR-GDL-04; B-13).

## 17. AuditLog

- **Invariant**: append-only (không API sửa/xoá), ghi trong cùng transaction với thao tác: actor, hành động, đối tượng, trước/sau, revision, lý do (FR-SEC-05; NFR-08). Lỗi 403/409 cũng được ghi audit (SRS 09). Ghi đè Super Admin gắn nhãn (FR-SEC-06). Thời hạn lưu tối thiểu **TBD-15**.

## 18. Nội dung ngoài phạm vi MVP

| Nội dung (nguồn A/T) | Lý do | Nguồn quyết định |
|---|---|---|
| Release / ReleaseManifest đầy đủ, Published/Revoked | M13 chỉ hiển thị gate | SRS FR-GTE-04 |
| Temporal / track issue có frame range | Ngoài tự động giai đoạn đầu | R B-09 |
| Diff/pre-label (change events), vehicle profile | Không tự mở rộng | R B-16 |
| Classifier thứ hai mặc định | Chỉ Detector baseline | R B-07 |
| Guideline RAG, vector index | Tra cứu trực tiếp | R B-13 |
| Annotation writeback vào CVAT | Adapter chỉ đọc | R B-18 |
| Công thức priority `S × (0.5·C + 0.3·A + 0.2·R)` của A, tier P0–P3 của T | Thay bằng điểm rủi ro có version của SRS | R B-10; SRS FR-RNK |
