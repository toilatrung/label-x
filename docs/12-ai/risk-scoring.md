---
id: ai-risk-scoring
title: Mô hình điểm rủi ro frame
type: reference
domain: ai
module: quality-control
tags: [ai, ranking, risk-score, calibration]
priority: 1
---
# Mô hình điểm rủi ro frame

Điểm rủi ro `s(f)` xếp hạng frame để reviewer xem trước frame có nhiều lỗi kỳ vọng nhất trong ngân sách review hữu hạn (KPI-1). Nguồn chính: SRS [06-functional.tex](../label-x_system-requirement-specification/sections/06-functional.tex) §Module RNK, [02-overview.tex](../label-x_system-requirement-specification/sections/02-overview.tex) §Phát biểu bài toán.

## 1. Lập luận

KPI-1 đếm **lỗi** trong ngân sách tính bằng **số frame**. Nếu mỗi lỗi chỉ tính một lần và điểm frame là kỳ vọng số lỗi đã hiệu chỉnh tốt, thì sắp frame theo kỳ vọng số lỗi tối đa kỳ vọng Recall@k. Hai điều kiện này không tự đúng; chúng được kiểm bằng hiệu chỉnh ngoài fold và ablation trên tập hiệu chỉnh, và chỉ kết luận trên held-out (SRS 06; FR-RNK-10, FR-RNK-11).

## 2. Công thức

### Bước 1 — Neo và số lỗi tối đa `n_i`

| Nhóm | Neo issue | `n_i` |
|---|---|---|
| E1 | Vùng box dự đoán không ghép; dự đoán chồng nhau IoU ≥ `τ_m` gộp một vùng | 1 |
| E2 | Annotation trong cặp ghép khác lớp | 1 |
| E3 | Cụm annotation nối bởi cặp IoU ≥ 0,85; cụm `m` box | `m − 1` |

### Bước 2 — Xác suất cấp issue `q_i`

```
q_i = σ(w_g · x_i + b_g)
```

- Học trực tiếp ở cấp issue theo nhóm `g ∈ {E1, E2, E3}`; **không** gộp noisy-OR từ candidate (các candidate cùng issue dùng chung bằng chứng, phụ thuộc nhau).
- `x_i` tổng hợp đặc trưng candidate của issue (giá trị lớn nhất, số engine cùng chỉ ra, có cặp ambiguous…).
- Nhãn học: "issue trùng ít nhất một lỗi trong `E`" trên tập hiệu chỉnh. Với E3, `q_i` là xác suất cụm là trùng thật; kỳ vọng số lỗi `n_i·q_i`.
- Sau logistic có thể hiệu chỉnh isotonic nếu đường reliability lệch.

### Bước 3 — Điểm nền `h(f)`

- `h(f) ≥ 0` ước lượng số lỗi trong frame **không** khớp issue nào; hồi quy Poisson trên đặc trưng frame.
- Nhãn chỉ đếm lỗi chưa có issue ⇒ không đếm lại lỗi đã có issue.

### Bước 4 — Điểm frame

```
s(f) = Σ_{i ∈ I_f} n_i · q_i + h(f)
```

Hoà điểm phá theo `SHA256(frame_key ‖ seed)` (FR-RNK-04).

## 3. Đặc trưng gợi ý (chốt trên tập hiệu chỉnh)

| Nhóm | Đặc trưng |
|---|---|
| E1 | Confidence lớn nhất trong vùng; lớp dự đoán; log diện tích; IoU lớn nhất với annotation bất kỳ; có cặp ambiguous; vị trí mép ảnh |
| E2 | Confidence lớp dự đoán; chênh confidence lớp dự đoán và lớp annotation; cặp lớp (ví dụ `car`/`truck`); IoU cặp ghép; diện tích |
| E3 | IoU lớn nhất trong cụm; cùng lớp hay khác lớp; số dự đoán Detector phủ cụm; `m` |
| `h(f)` | Số annotation; số đối tượng nhỏ; ngày/đêm; thời tiết; số cảnh báo cấu trúc; cờ engine bắt buộc chưa kiểm |

Thuộc tính cảnh (thời tiết, loại cảnh, thời điểm) dùng phân tầng/báo cáo slice và làm đặc trưng nền, không phải nhãn cần kiểm (SRS 03).

## 4. Phiên bản 0 (`score_v0`)

Mỗi nhóm cần ít nhất `n_min` issue dương trên tập hiệu chỉnh để học `w_g` (`n_min`: **TBD-16**). Chưa đủ thì dùng `score_v0`:

- `q_i` = confidence lớn nhất của Detector (E1, E2); `q_i = 0,5` (E3).
- `h(f) = ε · số annotation`, `ε` nhỏ — chỉ để frame không có issue được sắp theo mật độ thay vì theo hash. Giá trị `ε`: **TBD-20** (Tech Lead, đội mô hình); ghi vào score version khi chốt.
- Báo cáo phải ghi rõ đang dùng `score_v0`; confidence không phải xác suất annotation sai.

## 5. Hiệu chỉnh và ablation (trước khi khoá score version)

| Yêu cầu | Nội dung | Nguồn |
|---|---|---|
| Hiệu chỉnh ngoài fold | Cross-validation **theo video** trên tập hiệu chỉnh; báo Brier score và đường reliability theo E1/E2/E3; lưu cùng score version | FR-RNK-10 |
| Ablation | Bỏ điểm nền; bỏ từng nhóm đặc trưng; so với `score_v0` và heuristic; chọn version theo Recall@20% ngoài fold | FR-RNK-11; R B-14 |
| Biến thể effort | `s(f) / t̂(f)` (kỳ vọng lỗi trên thời gian review ước lượng) để tối ưu KPI-2 — Could | FR-RNK-09 |

- Không dùng held-out để học hay chọn tham số (FR-EVL-05a). Thay đổi sau khi thấy kết quả held-out bị cấm (RK-09; pre-registration).
- Mục khoá trước khi đo (SRS 07 bảng khoá, dòng Score version): đặc trưng, tham số `w_g`, `b_g`, mô hình điểm nền `h(f)`, `τ_E1`, `τ_E2`, seed phá hoà — người khoá: QC Admin.

## 6. Quy tắc vận hành

- Tính cho mọi frame của snapshot, kể cả frame không có candidate (FR-RNK-01).
- Score version bất biến sau khoá, lưu kèm mỗi ranking (FR-RNK-02); tái lập giống hệt (FR-RNK-03).
- Lưu đóng góp `n_i·q_i` và `h(f)` để giải thích (FR-RNK-05).
- Frame có engine bắt buộc Not checked/Failed mang cờ "thiếu bằng chứng", hàng đợi riêng (FR-RNK-06).
- Lát ngẫu nhiên `r%` (**TBD-10**) độc lập ranking (FR-RNK-07).
- Ranking đối chứng: ngẫu nhiên nhiều seed, heuristic mật độ, heuristic max confidence (FR-RNK-08).

## 7. Không dùng trong MVP

- Công thức priority của A `S × (0.5·C + 0.3·A + 0.2·R)` và bucket High/Medium/Low; tier P0–P3 của T. R B-10 yêu cầu không lấy công thức cũ làm chuẩn; SRS thay bằng mô hình trên.

Liên quan: [evaluation.md](evaluation.md), [detector.md](detector.md), [../03-domain/value-objects.md](../03-domain/value-objects.md#riskscore).
