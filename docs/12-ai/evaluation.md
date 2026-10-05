---
id: ai-evaluation
title: Đánh giá engine, ranking và hiệu quả review
type: reference
domain: ai
module: quality-control
tags: [ai, evaluation, kpi, reference]
priority: 1
---
# Đánh giá engine, ranking và hiệu quả review

Tài liệu mô tả cách đo: (1) KPI-1 Recall@20% của ranking; (2) KPI-2 giảm effort với chất lượng tương đương (non-inferiority); (3) Metric engine — accuracy của Detector trên reference. Nguồn chính: SRS [07-evaluation.tex](../label-x_system-requirement-specification/sections/07-evaluation.tex), [02-overview.tex](../label-x_system-requirement-specification/sections/02-overview.tex) §KPI, [03-data-errors.tex](../label-x_system-requirement-specification/sections/03-data-errors.tex) §Reference; R B-05, B-14, B-15, B-20, R-04, R-07.

> Hiện chưa có reference, chưa có phép đo. Mọi con số trên H (ví dụ Precision 91.2%, agreement 94.1%, residual 4.0%) và đồ thị trong SRS là **minh hoạ**, không phải kết quả (R B-05, B-14).

## 1. Reference — điều kiện tiên quyết

- Reference = GT cho **toàn bộ** tập đánh giá + tập lỗi `E` suy ra tất định (BR-01…BR-07), duyệt và khoá version (SRS 03; R B-20).
- GT lập độc lập với công cụ: người xác minh mù với ranking/candidate (BR-10); hai người gán độc lập, QA Lead phân xử phần không khớp (BR-11). Nếu chỉ xác minh candidate công cụ đưa ra, mẫu số thiếu lỗi công cụ bỏ sót và KPI-1 bị thổi phồng.
- Khoá cùng: GT version, snapshot, mapping, `τ_m`, `a_min`, version thuật toán (BR-13; FR-EVL-04).
- Phân công (R phân công MVP): QA Lead chịu trách nhiệm reference và held-out; người có chuyên môn duyệt/khoá; reviewer/annotator được giao chuẩn bị nhưng không review annotation của mình. Tỉ lệ chia tập chưa đặt (**TBD-03**).
- Phụ thuộc AS-04: QA Lead và ít nhất hai người xác minh độc lập sẵn sàng trước khi đo.

**Thứ tự (R B-20)**: build discovery có thể đi trước, nhưng **acceptance** recall/precision chỉ sau khi reference đúng scope được khoá. Tách "hoàn thành build" khỏi "hoàn thành đánh giá".

## 2. Phân chia dữ liệu và chống rò rỉ

- Ảnh BDD100K nhóm theo video nguồn, chia **tập hiệu chỉnh** (chọn trọng số, ngưỡng, `k*`) và **tập held-out** (chỉ đo nghiệm thu), không giao nhau theo video (SRS 03 Hình phân chia).
- Kiểm bắt buộc, lưu cùng evaluation run (FR-EVL-05): (a) không giao video; từ chối dùng held-out học tham số; (b) đối chiếu danh sách ảnh huấn luyện Detector — giao ⇒ chặn (AS-03, xem [detector.md §7](detector.md#7-chống-leakage-as-03)); (c) loại case guideline/hiệu chỉnh khỏi GT held-out (BR-16).

## 3. KPI-1 — Recall@20%

```
n_20 = ⌈0,2 · N⌉
Recall@20% = |{e ∈ E : rank_π(φ(e)) ≤ n_20}| / |E|
```

- Đơn vị đếm: **lỗi** (BR-01), chỉ E1–E3, đã loại ignore (BR-07). Recall theo frame có lỗi là chỉ số phụ.
- Điều kiện tính: `|E| ≥ E_min` (**TBD-K4**); dưới ngưỡng ghi "không đủ mẫu". Nhóm lỗi có ít hơn `E_min,g` chỉ báo cáo.
- Ý nghĩa: đo khả năng xếp hạng, độc lập việc reviewer có tìm thấy lỗi; không thay accuracy engine.

**Đối chứng** (FR-RNK-08; SRS 07): ngẫu nhiên (`S ≥ 1000` seed, báo trung bình và phân vị 2,5–97,5%), heuristic mật độ (số annotation giảm dần), heuristic Detector (`score_v0`), oracle (cận trên, tham khảo).

**Khoảng tin cậy**: cluster bootstrap theo video nguồn (frame cùng video tương quan), `B ≥ 1000`, seed khoá trước (FR-EVL-09; SRS 07 mục KPI-1). Mỗi lần lặp:

1. Lấy lại **toàn bộ video**, có hoàn lại.
2. Frame của video bị lấy lặp được nhân bản, mỗi bản có **khoá phá hoà riêng**.
3. Tính lại `N` và `n_20 = ⌈0,2·N⌉` của mẫu.
4. Sắp lại theo `s(f)` đã có — **không** học lại điểm; tính lại các ranking đối chứng trên cùng mẫu.
5. Recall của ranking ngẫu nhiên lấy theo kỳ vọng `n_20/N` của từng mẫu.
6. Tính hiệu số `Δ = Recall@20%_π − Recall@20%_đối chứng` trên cùng mẫu bootstrap.

**Đạt KPI-1** khi đồng thời: (i) cận dưới CI của Recall@20% ≥ ngưỡng **TBD-K1**; (ii) cận dưới CI của `Δ` so với ngẫu nhiên và với heuristic mật độ đều > 0. Báo cáo thêm theo E1/E2/E3, slice (ngày/đêm, thời tiết, kích thước), đường Recall@k với k từ 5% tới 100% (FR-EVL-08).

## 4. KPI-2 — Giảm effort, chất lượng tương đương

**Effort** = thời gian thao tác hoạt động ghi tự động, loại khoảng không thao tác > `t_idle` (**TBD-11**):

```
T = Σ (t_view + t_tp + t_fa + t_adj + t_rc)        KPI-2 = 1 − T_A / T_B
```

`t_fix` (annotator sửa trên CVAT) báo cáo riêng và trong phân tích độ nhạy, không cộng vào `T`. Chỉ số phụ: lỗi xác nhận/giờ review, `t_fa/T`, KPI-2b (recall phát hiện thực tế, không có ngưỡng).

**Thiết kế**: crossover AB/BA, D1/D2 chia theo video và phân tầng; quy tắc EX-01…EX-10 (xem [../09-testing/acceptance-pilot.md](../09-testing/acceptance-pilot.md)).

**Phân tích effort** (SRS 07 §Phân tích effort):

- **Estimand chính**: tỉ số `T_A/T_B` của tổng effort trên cùng khối lượng dữ liệu; KPI-2 = `1 − T_A/T_B`.
- **Mô hình**: hồi quy hỗn hợp trên `log T_{r,p}` — effort của reviewer `r` ở đợt `p`, **chuẩn hoá theo số frame của tập**:
  `log T_{r,p} = μ + τ·arm + γ·period + η·dataset + u_r + ε`, với `u_r` là hiệu ứng ngẫu nhiên của reviewer; `exp(τ)` ước lượng `T_A/T_B`.
- **Khoảng tin cậy**: từ mô hình trên, kiểm lại bằng **bootstrap hai tầng** (lấy lại reviewer trong từng chuỗi, rồi lấy lại khối video trong từng tập), giữ nguyên cặp hai điều kiện của mỗi reviewer.
- **Phân tích độ nhạy định trước**: (i) chỉ dùng đợt 1 (so sánh song song, không carryover); (ii) hai giá trị `t_idle`; (iii) cộng `t_fix` vào `T`.

**Chất lượng tương đương (G-1, non-inferiority)**:

```
ρ = số lỗi E1–E3 còn lại sau quy trình / số đối tượng GT không ignore
H0: ρ_A − ρ_B ≥ δ    vs    H1: ρ_A − ρ_B < δ,   α = 0,025 (một phía)
```

- `ρ` đo **trực tiếp trên toàn tập** (reference phủ toàn bộ) sau khi mỗi nhánh kết thúc, so annotation cuối của nhánh với GT theo cùng quy tắc matching/đếm lỗi.
- Lỗi còn lại gồm **lỗi ban đầu chưa sửa và lỗi mới phát sinh do sửa**. `ρ` có thể vượt 100% trong trường hợp cực đoan (nhiều box trùng).
- **Mẫu số (số đối tượng GT không ignore) bằng 0 thì không tính** `ρ`.
- `ρ` khác G-4 (residual vận hành ước lượng từ lát ngẫu nhiên khi không có reference toàn tập).
- Bác H0 khi cận trên CI 95% hai phía của `ρ_A − ρ_B` < `δ`. CI bằng bootstrap theo khối video trong từng tập, giữ cặp hai nhánh trên cùng dữ liệu. `δ`: **TBD-K3**, Product Owner và QA Lead chốt trước thí nghiệm.

**Guardrail của thí nghiệm** (SRS 07):

- **G-2b — lỗi nghiêm trọng**: số lỗi nghiêm trọng của reference còn lại trong annotation cuối, **kể cả lỗi chưa từng có issue**, ở nhánh assisted không lớn hơn nhánh baseline. G-2b khác G-2 (gate: issue nghiêm trọng đã xác nhận còn mở = 0).
- **G-5 — box thừa**: số box thừa (BR-06) trong annotation cuối, kể cả box phát sinh do sửa, báo cáo theo nhánh; nhánh assisted không được nhiều hơn baseline quá `δ_fp` (**TBD-K3**).
- Ngưỡng residual ≤ 5% và đồng thuận ≥ 90% là guardrail khởi điểm, không thay kiểm định trên.

**Đạt KPI-2** khi đồng thời: (i) bác H0 non-inferiority; (ii) cận dưới CI 95% của `1 − T_A/T_B` ≥ **TBD-K2**; (iii) đạt G-2b và G-5; (iv) kết luận không đổi chiều khi chỉ dùng đợt 1. Cỡ mẫu từ power analysis 80% trên pilot nhỏ (**TBD-12**).

## 5. Metric engine — accuracy Detector (B-05)

- **Quyết định B-05 (chọn B)**: khối đánh giá engine riêng tính metric trên reference theo B-20; Model Orchestrator tổng hợp kết quả có provenance; không dùng model làm Ground Truth (R B-05).
- Precision/Recall Detector theo lớp chỉ tính trên GT đã khoá; thiếu GT ⇒ Metric Not checked, accuracy "chưa đánh giá" — không 0%, không pass (FR-EVL-15; FR-RPT-03).
- Provenance bắt buộc: engine/model/config version, evaluation run, snapshot/revision, reference version, scope, định nghĩa metric/matching, cỡ mẫu, status (R B-05; FR-EVL-14).
- Đặc tả matching của Metric có thể riêng (ví dụ IoU theo lớp), ghi rõ trong evaluation run (BR-17).
- "Model Orchestrator" là vai trò điều phối/tổng hợp phép đo; đặc tả chi tiết (đầu vào, đầu ra, provenance) là **TBD-21** (đội mô hình, trước khi đo Metric engine). Cài đặt nằm trong module Evaluation (SRS 10).

## 6. Chỉ số vận hành và guardrail

| Mã | Chỉ số | Ngưỡng | Ghi chú |
|---|---|---|---|
| G-2 | Issue nghiêm trọng đã xác nhận còn mở trên run cuối | 0 (cấu hình pilot) | Mức nghiêm trọng TBD-07 |
| G-3 | Đồng thuận reviewer với adjudicator trên tập case chuẩn | ≥ 90% (cấu hình pilot) | "Chưa chắc chắn" = không trùng; tính từng reviewer + trung vị; không thay accuracy engine |
| G-4 | Residual vận hành từ lát ngẫu nhiên | ≤ 5% (cấu hình pilot) | Không dùng mẫu theo rủi ro; tiêu chí đủ mẫu chưa chốt (R B-15) |
| — | Candidate precision | Báo cáo | Confirmed / (confirmed + rejected) trong tập đã phân xử; báo kèm uncertain/unreviewed (T §7) |

Ngưỡng G-2/G-3/G-4 là cấu hình khởi điểm pilot đã chốt trong R, **chưa** là bằng chứng đạt và không thay kiểm định non-inferiority (SRS 02, 07).

## 7. Đăng ký trước (pre-registration)

Khoá version trong LabelX trước khi chạy held-out hoặc bắt đầu thí nghiệm (SRS 07 bảng khoá):

| Mục | Nội dung | Người khoá |
|---|---|---|
| Detector | Artifact, checksum, mapping, `τ_conf`, xác nhận không huấn luyện trên held-out | Data/Model Owner |
| Score version | Đặc trưng, tham số `w_g`, `b_g`, mô hình điểm nền `h(f)`, `τ_E1`, `τ_E2`, seed phá hoà | QC Admin |
| Reference | GT version, mapping, `τ_m`, `a_min`, `E_min` | QA Lead |
| Ngưỡng KPI | K1, K2, `δ` | Product Owner |
| Thí nghiệm | Seed D1/D2 và AB/BA, `k*`, `r`, `t_idle`, cỡ mẫu, mô hình phân tích, độ nhạy, `δ`, `δ_fp` | Product Owner |

Thay đổi sau khoá ghi lý do; kết quả dùng phiên bản cũ vẫn được báo cáo.

## 8. Báo cáo

- Mỗi chỉ số có cỡ mẫu, mẫu số, phương pháp, khoảng tin cậy, provenance (FR-RPT-01; NFR-14).
- Random và risk báo cáo riêng (FR-RPT-02; H AuditSampling, PerformanceEvaluation).
- Coverage theo từng engine; coverage chung chỉ là tiến độ (FR-RPT-04).
- Xuất PDF/CSV/JSON ghi version snapshot, run, score, reference (FR-RPT-05, Should).

## 9. Ngoài phạm vi MVP

Ablation VLM/RAG/temporal/classifier (T §7–8) chỉ thực hiện khi các thành phần đó được đưa vào scope (R B-07, B-08, B-09, B-13). Reviewer calibration (honeypot, blind anchor) có trên H Calibration/Benchmark nhưng SRS chỉ yêu cầu G-3 (FR-EVL-16, Should).
