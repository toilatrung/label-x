---
id: testing-acceptance-pilot
title: Kế hoạch pilot và nghiệm thu
type: reference
domain: testing
module: quality-control
tags: [testing, acceptance, pilot, experiment]
priority: 1
---
# Kế hoạch pilot và nghiệm thu

Pilot chứng minh R-04 và R-07 (đo trên reference, hiệu quả review có căn cứ) và đánh giá AC-08, AC-09, AC-10. Nguồn: R [architecture_review.html](../00-project/sources/architecture_review.html) (B-14, B-15, B-20, cấu hình MVP, phân công và vận hành), SRS [07-evaluation.tex](../label-x_system-requirement-specification/sections/07-evaluation.tex), [11-traceability.tex](../label-x_system-requirement-specification/sections/11-traceability.tex), T §7 (thiết kế pilot).

> Ngưỡng H (Coverage 95%, critical 0, rework verify 100%, residual ≤ 5%, agreement ≥ 90%) là **cấu hình khởi điểm pilot**, chưa là cam kết nghiệm thu. Ngưỡng accuracy engine và năng suất review chốt từ phép đo, không tự đặt số (R B-14).

## 1. Điều kiện tiên quyết

| # | Điều kiện | Chủ trì | Mã mở |
|---|---|---|---|
| 1 | CVAT URL, phiên bản pin, quyền token, endpoint thật; adapter chứng minh hash ổn định, drift, frame mapping | Chủ CVAT, Tech Lead | TBD-01 |
| 2 | Phần cứng app server, GPU | Tech Lead | TBD-02 |
| 2a | Giấy phép và điều khoản sử dụng BDD100K cho pilot và lưu trữ nội bộ được xác nhận — **trước khi nạp dữ liệu** | Data Owner | TBD-18 |
| 3 | Danh sách ảnh BDD100K, `N` tập hiệu chỉnh và held-out (tách theo video nguồn) | Data Owner, QA Lead | TBD-03 |
| 4 | Nguồn annotation cần review; có dùng lỗi chèn không | Product Owner, QA Lead | TBD-04 |
| 4a | `a_min` và quy tắc ignore theo occlusion/truncation — **trước khi lập reference** (cùng TBD-03, TBD-04, TBD-05) | QA Lead | TBD-06 |
| 5 | Detector baseline: artifact, checksum, mapping 10 lớp, xác nhận không huấn luyện trên held-out | Data/Model Owner | AS-02, AS-03 |
| 6 | Guideline BDD100K có rule ID + version cho 10 lớp | QA Lead | AS-06; RK-08 |
| 7 | Định nghĩa mức nghiêm trọng | QA Lead | TBD-07 |
| 8 | Quyết định VLM trong pilot | Product Owner | TBD-08 |
| 9 | Người: QA Lead + ít nhất hai người xác minh; ≥ 4 reviewer tương đương; người duyệt waiver/phát hành khác người yêu cầu | Product Owner | AS-04, AS-05 |
| 10 | Lease, `r`, `t_idle` | Product Owner, QA Lead | TBD-09, TBD-10, TBD-11 |

Thứ tự theo phụ thuộc (R §7): xác minh nền backend và quyền CVAT → Dataset/shape/taxonomy → artifact/mapping/reference → policy required units → kiểm pilot/gate. Không có mốc thời gian hay ngân sách trong nguồn.

## 2. Giai đoạn pilot

### P0 — Kiểm nền trên CVAT thật

- Chạy adapter chỉ đọc trên job pilot thật; chứng minh hash ổn định, phát hiện drift (AC-03), deep link đúng.
- Chạy toàn luồng UC-01…UC-07 trên phạm vi nhỏ (kịch bản [e2e-testing.md](e2e-testing.md)); kiểm R-01, R-02, R-03, R-05, R-06 (AC-01…07, AC-11).

### P1 — Lập reference (UC-08)

- Tập hiệu chỉnh và held-out tách theo video; GT độc lập hai người, QA Lead phân xử, suy ra `E`, khoá (BR-10…BR-16).
- Báo tỉ lệ khớp hai bản GT trước phân xử (BR-11).
- Reference là phụ thuộc bắt buộc của mọi phép đo accuracy (R B-20). Chưa có reference ⇒ accuracy "chưa đánh giá".

### P2 — Pilot nhỏ trên tập hiệu chỉnh

Mục đích (SRS 07; R cấu hình vận hành):

- Chọn `τ_conf`, `τ_E1`, `τ_E2`; học và hiệu chỉnh score (FR-RNK-10), ablation (FR-RNK-11); chọn score version theo Recall@20% ngoài fold. Đủ nhãn hay dùng `score_v0` tuỳ `n_min` (TBD-16).
- Chọn `k*` theo EX-06 và `r`.
- Đo phương sai effort và residual để power analysis 80% ⇒ cỡ mẫu frame, reviewer (**TBD-12**).
- Đo thời gian để đặt timeout từng tác vụ (đọc CVAT, Detector theo lô, VLM nếu bật), số retry (**TBD-14**), mục tiêu hiệu năng (**TBD-13**), hạn mức tổng.
- Đo residual baseline nhỏ làm căn cứ chọn `δ` (**TBD-K3**).
- Chốt K1, K2 từ baseline trên tập hiệu chỉnh **trước** khi chạy held-out (SRS 02 decisionbox; B-14).

### P3 — Đăng ký trước (pre-registration)

Khoá trong LabelX (SRS 07 bảng khoá): Detector (Data/Model Owner); score version (QC Admin); reference + `τ_m`, `a_min`, `E_min` (QA Lead); K1, K2, `δ` (Product Owner); thí nghiệm — seed D1/D2 và AB/BA, `k*`, `r`, `t_idle`, cỡ mẫu, mô hình phân tích, độ nhạy, `δ`, `δ_fp` (Product Owner). Đổi sau khoá ghi lý do; kết quả bản cũ vẫn báo cáo (RK-09).

### P4 — KPI-1 trên held-out (UC-09, AC-08)

- Ranking bằng score version đã khoá; Recall@20% theo lỗi, đối chứng ngẫu nhiên/heuristic/oracle, cluster bootstrap theo video.
- Đạt khi cận dưới CI ≥ K1 và cận dưới CI của hiệu số với ngẫu nhiên và heuristic mật độ > 0. Chi tiết: [evaluation.md §3](../12-ai/evaluation.md#3-kpi-1--recall20).

### P5 — Thí nghiệm effort (UC-10, AC-09)

Thiết kế chéo AB/BA; quy tắc (SRS 07):

| Mã | Quy tắc |
|---|---|
| EX-01 | Gán reviewer ngẫu nhiên (seed khoá trước) vào AB/BA, phân tầng theo kinh nghiệm và điểm calibration; 4 reviewer là sàn, số thực tế từ power analysis (TBD-12) |
| EX-02 | D1, D2 chia ngẫu nhiên theo video, phân tầng theo slice và số lỗi reference; không giao tập hiệu chỉnh; mỗi frame đúng một reviewer |
| EX-03 | Mỗi nhánh có bản sao annotation riêng (CVAT task riêng) từ cùng snapshot đầu vào |
| EX-04 | Baseline: toàn bộ frame theo thứ tự gốc; ẩn ranking, risk score, evidence; sửa/verify như assisted |
| EX-05 | Assisted: `R = T_k*(π) ∪ U`, `U` là `⌈rN⌉` frame ngẫu nhiên ngoài `T_k*`; hết `T_k*` theo rank rồi tới `U` |
| EX-06 | `k*` nhỏ nhất trên lưới {10%, 15%, …, 100%} mà residual dự kiến của assisted (ngoài fold) không vượt baseline quá `δ/2` |
| EX-07 | Kết thúc nhánh khi mọi frame review xong, mọi issue (kể cả từ re-check và run cuối) có kết luận, mọi rework đã verify |
| EX-08 | Chống carryover: khoá guideline và kho case; case phát sinh không hiển thị cho nhánh khác tới khi kết thúc; buổi làm quen như nhau |
| EX-09 | Cùng QA Lead phân xử, cùng quy tắc verify, cùng quyền tra guideline |
| EX-10 | Reviewer không biết reference; người lập reference không tham gia trên cùng dữ liệu |

Đạt KPI-2 khi: bác H0 non-inferiority về `ρ`; cận dưới CI của `1 − T_A/T_B` ≥ K2; đạt G-2b và G-5; không đổi chiều khi chỉ dùng đợt 1. Chi tiết: [evaluation.md §4](../12-ai/evaluation.md#4-kpi-2--giảm-effort-chất-lượng-tương-đương).

### P6 — Gate và báo cáo (UC-11, UC-14, AC-10)

- Gate trên QC run cuối với ngưỡng cấu hình pilot; thiếu dữ liệu ⇒ chưa đạt; residual (G-4) từ lát ngẫu nhiên, không trộn mẫu theo rủi ro (R B-15).
- Báo cáo đủ cỡ mẫu, mẫu số, phương pháp, CI, provenance; random và risk riêng.

## 3. Phân công (định hướng đã phê duyệt — R)

| Việc | Vai trò |
|---|---|
| Reference, held-out | QA Lead chịu trách nhiệm; người có chuyên môn duyệt/khoá; reviewer/annotator được giao chuẩn bị, không tự review annotation của mình |
| Guideline | QA Lead duyệt nội dung/version; QC Admin cấu hình mapping |
| Phân xử | QA Lead |
| Waiver, duyệt phát hành | Người được cấp quyền, khác người yêu cầu; chưa có người đủ quyền thì chờ |
| Cấu hình hệ thống, timeout, hạn mức | QC Admin phối hợp backend/đội mô hình |
| Thiết kế và khoá thí nghiệm, ngưỡng KPI | Product Owner |
| Khoá artifact Detector | Data/Model Owner |

Product Owner và Data/Model Owner không thao tác review, chỉ xem báo cáo hiệu quả (UC-11) và khoá phần mình phụ trách; họ **không** được là reviewer trong thí nghiệm mình thiết kế (SRS 06, đoạn sau ma trận quyền).

Phê duyệt định hướng không chứng minh tài khoản đã được cấp quyền hay pilot đã chạy (R).

## 4. Kết quả có thể có

| Kết quả | Điều kiện |
|---|---|
| Đạt | Tiêu chí KPI tương ứng thoả trên held-out/thí nghiệm, guardrail đạt |
| Không đạt | Đủ mẫu, tiêu chí không thoả |
| Không đủ mẫu | `|E| < E_min` hoặc cỡ mẫu dưới power analysis — không kết luận |
| Chưa xác định | Ngưỡng TBD-K1/K2/K3/K4/TBD-12 chưa chốt |

R-07 và KPI-2 hiện ở mức "Không đủ dữ liệu" (R §3). Sau pilot, VLM/RAG/Classifier chỉ được xem xét nếu ablation chứng minh lợi ích và quyền/budget đáp ứng (R thứ tự triển khai bước 4–5).

## 5. Rủi ro pilot (SRS 11)

RK-01 Detector yếu ban đêm/vật nhỏ; RK-02 leakage held-out; RK-03 reference chậm/tốn công; RK-04 automation bias; RK-05 effort log sai; RK-06 CVAT không kiểm drift tin cậy; RK-07 ít lỗi E3; RK-08 guideline thiếu rule ID; RK-09 đổi tham số sau khi thấy held-out. Biện pháp giảm thiểu theo bảng rủi ro SRS.
