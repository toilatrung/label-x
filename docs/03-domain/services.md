---
id: domain-services
title: Domain service và quy tắc nghiệp vụ
type: reference
domain: domain
module: quality-control
tags: [domain, services, business-rules, matching]
priority: 1
---
# Domain service và quy tắc nghiệp vụ

Domain service chứa logic không thuộc riêng một aggregate: matching, gộp candidate, xếp hạng, coverage ledger, đánh giá và gate. Aggregate ở [aggregates.md](aggregates.md), value object ở [value-objects.md](value-objects.md).

**Quy ước mã quy tắc**

- `BR-01…BR-17`, `EX-01…EX-10`: mã gốc của SRS ([03-data-errors.tex](../label-x_system-requirement-specification/sections/03-data-errors.tex), [07-evaluation.tex](../label-x_system-requirement-specification/sections/07-evaluation.tex)); giữ nguyên nghĩa.
- `DR-xx`: mã do tài liệu này đặt để truy vết các quy tắc rút từ FR/B-xx; **không** phải mã SRS. Mỗi DR ghi nguồn.

Mọi service phải tất định với cùng input/version/seed (R R-01; NFR-04) và không tự đặt ngưỡng: tham số chưa chốt ghi mã TBD.

## 1. MatchingService

Thuật toán matching một-một, không phụ thuộc lớp, dùng chung cho ba mục đích: GT ↔ annotation (suy ra `E`), dự đoán Detector ↔ annotation (sinh candidate E1/E2), GT ↔ GT (ghép hai bản reference, BR-11) (SRS 03 §Matching; FR-ENG-06).

**Thuật toán** (theo frame):

1. Tính IoU mọi cặp box hai tập, **không xét lớp**.
2. Loại cạnh IoU < `τ_m` trước khi tối ưu (`τ_m`: **TBD-05**, SRS đề xuất 0,5).
3. Giải bài toán gán (Hungarian): tối đa số cặp, rồi tối đa tổng IoU.
4. Phá hoà tất định: IoU lớn hơn, rồi ID đối tượng nhỏ hơn (ID ổn định trong snapshot).
5. Cặp IoU trong `[τ_amb, τ_m)` ghi **ambiguous**, đưa vào evidence (`τ_amb`: **TBD-05**).
6. Khi so với Detector: lọc dự đoán confidence ≥ `τ_conf` trước khi matching; `τ_conf` chọn trên tập hiệu chỉnh và khoá trong pre-registration (SRS 07 §Đăng ký trước).
7. Kết quả là **association**, không phải Precision/Recall của annotation (R B-21).

| Mã | Quy tắc | Nguồn |
|---|---|---|
| DR-01 | Matching là bước của engine Mô hình độc lập để sinh candidate; nó chạy được khi không có GT. Metric (accuracy) là thao tác riêng, chỉ chạy khi có GT đã khoá. | R B-21; SRS FR-EVL-15 |
| DR-02 | Agreement giữa Detector và annotation không được gọi là Precision/Recall hay accuracy. | R B-21; H Calibration |
| DR-03 | Metric engine dùng chung GT nhưng có thể có đặc tả matching riêng (ví dụ IoU theo lớp); khi đó ghi rõ định nghĩa trong evaluation run. | BR-17 |

## 2. ErrorDerivationService (suy ra tập lỗi reference)

Với `G` là tập đối tượng GT, `A` là annotation đang review trên một frame, `M ⊆ G × A` là kết quả matching:

| Mã | Quy tắc |
|---|---|
| BR-01 | Mỗi lỗi có ID, đúng một nhóm lỗi, đúng một đối tượng: đối tượng GT (E1/E2) hoặc annotation dư (E3). |
| BR-02 | E1: mỗi `g ∈ G` không thuộc cặp nào của `M`. |
| BR-03 | E2: mỗi cặp `(g, a) ∈ M` khác lớp. |
| BR-04 | E3: `a ∉ M`, IoU ≥ `τ_m` với ít nhất một `g` đã có cặp chính; chọn `g` IoU lớn nhất, phá hoà ID nhỏ; cụm `m` box sinh `m − 1` lỗi. |
| BR-05 | Lớp của annotation dư không xét (chỉ E3, không cộng E2); cặp chính sai lớp vẫn tính E2. |
| BR-06 | Box thừa không khớp GT và không thoả BR-04: ngoài E1–E3, báo cáo riêng, ngoài KPI pilot. |
| BR-07 | Đối tượng ignore (diện tích < `a_min` — **TBD-06**, hoặc che/cắt quá mức theo guideline) không tính tử số lẫn mẫu số. |
| BR-14 | Bác lỗi do matching sai ⇒ sửa mapping (có lý do) rồi suy lại; không xoá lỗi trực tiếp. |

Quy tắc lập reference BR-10…BR-17 áp dụng cho aggregate Reference ([aggregates.md §12](aggregates.md#12-reference-gt-và-tập-lỗi-e)).

## 3. CandidateGenerationService (engine)

| Mã | Quy tắc | Nguồn |
|---|---|---|
| DR-04 | Schema/Taxonomy: lớp thuộc taxonomy version; thuộc tính bắt buộc hợp lệ; sinh cảnh báo cấu trúc có rule ID, expected/actual. | FR-ENG-02 |
| DR-05 | Geometry chỉ kiểm cấu trúc/bounds/diện tích (2 px, 24 px²); G-009 Not checked khi chưa có biên tham chiếu; không suy biên vật thể. | R B-06; FR-ENG-03 |
| DR-06 | Duplicate/Overlap sinh candidate E3 cho cặp annotation IoU ≥ 0,85 (D-002), kèm IoU và lớp hai box; chỉ là nghi vấn — hai đối tượng thật chồng lấp không là lỗi. | FR-ENG-04; SRS 03 |
| DR-07 | Detector chạy trên mọi frame trong phạm vi áp dụng với artifact đã freeze (version, checksum, mapping 10 lớp). | R B-07; FR-ENG-05 |
| DR-08 | Dự đoán không ghép, confidence ≥ `τ_E1` ⇒ candidate E1; cặp ghép khác lớp, confidence lớp dự đoán ≥ `τ_E2` ⇒ candidate E2. Ngưỡng có version, chọn trên tập hiệu chỉnh. | FR-ENG-07 |
| DR-09 | Không có Detector khả dụng ⇒ engine Mô hình độc lập Not checked (`no_model`); không sinh ranking giả từ engine thiếu. | FR-ENG-09 |
| DR-10 | Evidence candidate gồm: box và lớp dự đoán, confidence, IoU, cặp ambiguous, crop ảnh, rule liên quan. | FR-ENG-08 |
| DR-11 | Blob upload trước (khoá hash nội dung), rồi commit metadata candidate + evidence + ledger của shard trong một transaction. | NFR-06; FR-AGG-06 |
| DR-12 | VLM không bật trong pilot (đề xuất, cần Product Owner duyệt — **TBD-08**). Nếu bật: theo B-08, tối đa 400 candidate/run, tối đa 3 lần thử mỗi lượt kiểm. | R B-08; FR-ENG-10 |

## 4. AggregationService (Candidate → Issue)

| Mã | Quy tắc | Nguồn |
|---|---|---|
| BR-08 | Nhiều candidate từ nhiều engine trỏ cùng (đối tượng, nhóm) gộp thành một issue; gộp không thay đổi `E`. | SRS 03 |
| DR-13 | Upsert issue theo `dedup_key` = (snapshot, frame, đối tượng tham chiếu, nhóm lỗi) với version policy gộp; giữ toàn bộ provenance candidate. | FR-AGG-03; R B-10 |
| DR-14 | Retry cùng khoá idempotent `(snapshot, engine, config, model, shard)` không tạo candidate/issue trùng. | FR-AGG-02; AC-02 |
| DR-15 | Mỗi issue lưu neo và `n_i` (E1 = 1, E2 = 1, E3 = `m − 1`); quy tắc neo có version cùng policy gộp. | FR-RNK-12 |
| DR-16 | Không tự đóng issue theo confidence; mọi issue cần quyết định của người. Không nhân confidence của các nguồn có lỗi tương quan để tạo mức chắc chắn giả. | R R-02; T §3 Aggregation |

## 5. RankingService

Chi tiết mô hình điểm ở [../12-ai/risk-scoring.md](../12-ai/risk-scoring.md).

| Mã | Quy tắc | Nguồn |
|---|---|---|
| DR-17 | Tính `s(f)` cho **mọi** frame của snapshot trong phạm vi run, kể cả frame không có candidate. | FR-RNK-01 |
| DR-18 | Công thức điểm có version, lưu kèm mỗi ranking, không đổi sau khoá. | FR-RNK-02 |
| DR-19 | Phá hoà theo `SHA256(frame_key ‖ seed)`. Cùng snapshot/config/score version/seed ⇒ ranking giống hệt. | FR-RNK-03, FR-RNK-04 |
| DR-20 | Lưu đóng góp `n_i·q_i` từng issue và `h(f)` để giải thích "vì sao frame được xếp cao". | FR-RNK-05 |
| DR-21 | Frame có engine bắt buộc Not checked/Failed mang cờ "thiếu bằng chứng", hiển thị riêng, không coi là điểm thấp an toàn. | FR-RNK-06; R B-19 |
| DR-22 | Lát kiểm tra ngẫu nhiên `r%` frame (**TBD-10**) bằng seed cố định, độc lập ranking, hàng đợi và báo cáo riêng; item ngẫu nhiên không được chấm điểm hay trộn vào hàng đợi rủi ro. | FR-RNK-07; H AuditSampling |
| DR-23 | Tạo được ranking đối chứng trên cùng snapshot: ngẫu nhiên (nhiều seed), heuristic mật độ, heuristic max confidence. | FR-RNK-08 |

## 6. ReviewWorkflowService (lease, quyết định, phân xử, rework)

| Mã | Quy tắc | Nguồn |
|---|---|---|
| DR-24 | "Bắt đầu review" cấp lease frame kế tiếp chưa có người giữ, bỏ qua frame mà reviewer là assignee tại snapshot; cấp nguyên tử. | FR-REV-03; UC-04 |
| DR-25 | Lease có thời hạn **TBD-09**, gia hạn khi có thao tác; hết hạn ⇒ frame về hàng đợi. | FR-REV-04 |
| DR-26 | Chuyển trạng thái issue chỉ theo bảng transition/event/actor/guard; ngoài bảng ⇒ 409. | R B-17; SRS 05 |
| DR-27 | Lưu quyết định: lease còn hạn và thuộc actor (409 nếu không), actor không là assignee tại snapshot (403); quyết định + audit cùng transaction. | FR-REV-10, FR-REV-14; R B-12 |
| DR-28 | Xác nhận bắt buộc nhóm lỗi và mức độ; bác bỏ/chuyển cấp bắt buộc lý do (400 nếu thiếu). | FR-REV-08; SRS 09 |
| DR-29 | "Đã review xong" chỉ khi mọi issue của frame đã có quyết định hoặc đang chờ phân xử; trả lease, dừng ghi effort. | FR-REV-13 |
| DR-30 | Người phân xử khác người chuyển cấp; kết luận bắt buộc rule áp dụng và lý do; lưu Decision Case có version. | FR-ESC-02…04 |
| DR-31 | Guideline còn thiếu ⇒ Guideline Gap gắn rule, issue chờ guideline version mới; không ép annotator sửa theo rule tự suy. | FR-ESC-05; R phân công MVP |
| DR-32 | "Đã sửa" yêu cầu revision mới khác revision gốc; re-check engine liên quan; verify bởi người khác annotator đã sửa. | FR-RWK-03…05 |
| DR-33 | Mọi yêu cầu sửa trong phạm vi đã đóng ⇒ snapshot toàn phạm vi + QC run cuối `is_final`, liên kết verification trước đó; run gốc giữ nguyên. | FR-RWK-06; R B-03 |
| DR-34 | Super Admin ghi đè phải có lý do, audit gắn nhãn, vẫn chịu self-review và tách nhiệm vụ; không là người duyệt mặc định. | FR-SEC-06; R B-12 |

## 7. CoverageLedgerService

| Mã | Quy tắc | Nguồn |
|---|---|---|
| DR-35 | Ledger riêng từng engine với policy version: đơn vị áp dụng theo [CoverageUnit](value-objects.md#coverageunit); chốt applicability **trước** chạy. | R B-04, cấu hình MVP |
| DR-36 | Không loại đơn vị lỗi khỏi mẫu số để tăng coverage. | R B-04; FR-AGG-04 |
| DR-37 | `not_triggered` (VLM, nếu bật) không vào mẫu số kiểm chọn lọc; các lý do Not checked khác vẫn làm coverage engine bắt buộc chưa đạt. | SRS 05 bảng trạng thái engine |
| DR-38 | Kiểm chọn lọc không tự thành yêu cầu quét mọi frame; coverage frame chung chỉ là tiến độ, gate kiểm ledger riêng từng engine bắt buộc. | R cấu hình MVP; FR-RPT-04 |
| DR-39 | Engine bắt buộc trong MVP: kiểm xác định (Schema/Taxonomy, Geometry, Duplicate/Overlap) trong scope; Detector bắt buộc trong pilot đánh giá discovery. Thiếu reference ⇒ Metric Not checked, accuracy "chưa đánh giá". | R cấu hình MVP |

## 8. EvaluationService

Chi tiết phương pháp ở [../12-ai/evaluation.md](../12-ai/evaluation.md).

| Mã | Quy tắc | Nguồn |
|---|---|---|
| DR-40 | Recall@k theo **lỗi**, `n_k = ⌈kN⌉`, `k` mặc định 0,2; chỉ tính khi `|E| ≥ E_min` (**TBD-K4**). | FR-EVL-07, FR-EVL-10 |
| DR-41 | Khoảng tin cậy 95% bằng cluster bootstrap theo video nguồn, `B ≥ 1000`, kèm hiệu số với từng ranking đối chứng. | FR-EVL-09 |
| DR-42 | Chống rò rỉ: tập hiệu chỉnh và held-out không giao theo video; không học tham số trên held-out; Detector không huấn luyện trên ảnh held-out (AS-03); loại case hiệu chỉnh khỏi GT held-out. | FR-EVL-05; BR-16 |
| DR-43 | Ở nhánh baseline, Workspace ẩn ranking, risk score, evidence engine. | FR-EVL-12; EX-04 |
| DR-44 | Chỉ số thiếu dữ liệu hiển thị Not checked / không đủ mẫu; không hiển thị 0% hay đạt. Random và risk báo cáo riêng. | FR-RPT-02, FR-RPT-03; R B-05 |
| EX-01…EX-10 | Quy tắc thí nghiệm effort (gán ngẫu nhiên, chia D1/D2, bản sao annotation riêng, điểm kết thúc, chống carryover…). | SRS 07 |

## 9. GateService

| Mã | Quy tắc | Nguồn |
|---|---|---|
| DR-45 | Gate tính trên QC run cuối (hoặc run gốc nếu chưa có rework, ghi rõ) với điều kiện cấu hình pilot: coverage engine bắt buộc ≥ 95%, critical chưa đóng = 0, rework bắt buộc verify 100%, residual ≤ 5%, đồng thuận reviewer ≥ 90%. | FR-GTE-01; R cấu hình MVP; H RulesThresholds |
| DR-46 | Mỗi điều kiện có nguồn, scope, mẫu số, cỡ mẫu; thiếu dữ liệu ⇒ chưa đạt, không tự đạt. | FR-GTE-02; R B-15 |
| DR-47 | Residual (G-4) ước lượng từ lát kiểm tra ngẫu nhiên, không từ mẫu theo rủi ro; tiêu chí đủ mẫu và cách dùng khoảng tin cậy chưa chốt (R B-15). | H AuditSampling; SRS 02 G-4 |
| DR-48 | Đồng thuận reviewer (G-3) tách khỏi accuracy engine; "Chưa chắc chắn" tính là không trùng. | SRS 02 G-3; R B-15 |
| DR-49 | Waiver theo policy từng điều kiện; người duyệt khác người yêu cầu; hiệu lực sau duyệt; hết hạn ⇒ chưa đạt; không đổi Not checked thành pass. Danh sách điều kiện được miễn và policy từng điều kiện: **TBD-19**. | R B-11; FR-GTE-03, FR-SEC-04 |
| DR-50 | Không phát hành khi thiếu toàn vẹn revision, approval, rework bắt buộc chưa verify, hoặc critical chưa xử lý mà không có waiver hợp lệ. Hệ thống/AI không tự quyết định phát hành. | R cấu hình MVP; H QualityGate |

## 10. GuidelineLookupService

- Tra mapping (nhóm lỗi, lớp, cặp lớp) → rule ID; hiển thị trích đoạn, version áp dụng cho snapshot, section, Decision Case cùng rule (FR-GDL-02, FR-GDL-03; UC-12).
- Không dùng retrieval ngữ nghĩa/RAG (FR-GDL-04; R B-13). Kho case cho RAG là hướng sau MVP.

## 11. Các tham số còn mở liên quan

| Mã | Nội dung | Service |
|---|---|---|
| TBD-05 | `τ_m`, `τ_amb` | Matching |
| TBD-06 | `a_min`, quy tắc ignore | ErrorDerivation |
| TBD-07 | Định nghĩa mức độ nghiêm trọng | Review, Gate |
| TBD-08 | Duyệt đề xuất không bật VLM | CandidateGeneration |
| TBD-09 | Thời hạn lease, gia hạn | ReviewWorkflow |
| TBD-10 | Tỉ lệ lát ngẫu nhiên `r` | Ranking |
| TBD-14 | Số lần retry, backoff shard | Orchestration |
| TBD-16 | `n_min` issue dương mỗi nhóm để học score | Ranking |
| TBD-19 | Danh sách điều kiện gate được waiver, policy từng điều kiện | Gate |
| TBD-20 | Timeout mỗi lượt VLM, `t_gc`, `ε` của `score_v0`, số chữ số làm tròn toạ độ khi hash | CandidateGeneration, Ranking, Snapshot |
| TBD-21 | Đặc tả Model Orchestrator | Evaluation |
| TBD-K1…K4 | Ngưỡng KPI-1, KPI-2, `δ`/`δ_fp`, `E_min` | Evaluation |
