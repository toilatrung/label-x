---
id: ai-detector
title: Detector baseline (engine Mô hình độc lập)
type: reference
domain: ai
module: quality-control
tags: [ai, detector, model, bdd100k]
priority: 1
---
# Detector baseline (engine Mô hình độc lập)

Engine "Mô hình độc lập" của MVP dùng **một Detector baseline** để sinh candidate E1 (thiếu box) và E2 (sai lớp). Classifier thứ hai chưa bật mặc định (nguồn: R B-07; SRS FR-ENG-05).

Nguồn: [architecture_review.html](../00-project/sources/architecture_review.html) (B-05, B-07, B-21, cấu hình MVP "Model artifact/class mapping"); SRS [03-data-errors.tex](../label-x_system-requirement-specification/sections/03-data-errors.tex), [06-functional.tex](../label-x_system-requirement-specification/sections/06-functional.tex), [09-interfaces.tex](../label-x_system-requirement-specification/sections/09-interfaces.tex) §Giao diện mô hình, [02-overview.tex](../label-x_system-requirement-specification/sections/02-overview.tex) AS-02/AS-03.

## 1. Vai trò và giới hạn

- Detector là **nguồn candidate**, không phải Ground Truth và không phải trọng tài (R B-05; SRS BR-17).
- Confidence của Detector không phải xác suất annotation sai và không phải độ chính xác (R B-07; SRS 06 `score_v0`).
- Candidate từ Detector luôn cần người review quyết định (R R-02).
- Agreement Detector–annotation không gọi là Precision/Recall (R B-21).

## 2. Artifact và freeze

Trước khi chạy pilot/held-out, Detector phải được freeze và ghi vào QC Run (FR-ENG-01, FR-ENG-05; SRS 07 bảng khoá trước khi đo):

| Mục | Yêu cầu | Người khoá |
|---|---|---|
| Artifact | Tên model, version, file/endpoint cố định | Data/Model Owner |
| Checksum | Checksum artifact, lưu trong mỗi QC Run | Data/Model Owner |
| Mapping lớp | Bảng lớp model → 10 lớp BDD100K, có version | Data/Model Owner |
| Transform toạ độ | Toạ độ pixel ảnh gốc `(x1, y1, x2, y2)` | Data/Model Owner |
| `τ_conf` | Lọc dự đoán trước matching; chọn trên tập hiệu chỉnh | Data/Model Owner |
| Không leakage | Xác nhận không huấn luyện trên ảnh held-out | Data/Model Owner |

**Chưa có**: artifact/endpoint thực. Model nào, phiên bản nào: chưa chốt (R mục 10 "Đã chốt cấu hình, còn đầu vào thực"). Phần cứng GPU: **TBD-02**.

> Mâu thuẫn nguồn: H (AnalysisConfig, ModelsGuidelines) ghi "Detector v2.3 · ngưỡng 0.60 · Taxonomy v3 · 12 lớp". R nói không sao chép giá trị model demo và không coi 12 lớp là dữ liệu thật. Xử lý: dùng 10 lớp BDD100K của SRS; ngưỡng hiệu chỉnh từ tập hiệu chỉnh, không dùng 0.60.

## 3. Mapping 10 lớp BDD100K

| Lớp đích | Ghi chú review |
|---|---|
| `car` | Đa số; hay nhầm với `truck` |
| `truck` | Dễ nhầm `car`, `bus` |
| `bus` | Xe buýt mini cần guideline rõ |
| `train` | Hiếm; khoảng tin cậy recall theo lớp rộng |
| `motorcycle` | Phân biệt với `bicycle`; người lái là `rider` |
| `bicycle` | Như trên |
| `pedestrian` | Người đi bộ |
| `rider` | Dễ nhầm `pedestrian` |
| `traffic light` | Nhỏ; màu đèn ngoài phạm vi kiểm |
| `traffic sign` | Nhỏ, dễ bỏ sót |

(Nguồn: SRS 03 bảng lớp.) Quy tắc mapping:

- Lớp model không ánh xạ được ⇒ dự đoán bị loại khỏi candidate và ledger ghi thiếu coverage; không tự suy tên lớp (R cấu hình MVP).
- Mapping là một phần của version Detector; đổi mapping ⇒ version mới.

## 4. Giao diện suy luận

- **Đầu vào**: lô ảnh (URI Object Storage), kích thước ảnh.
- **Đầu ra**: danh sách `(x1, y1, x2, y2, lớp, confidence)` theo pixel gốc, lớp đã ánh xạ.
- **Metadata bắt buộc**: model name, version, checksum artifact, mapping lớp version, thiết bị, batch size, thời gian suy luận.
- Chạy trong GPU worker nội bộ (Celery, hàng đợi riêng); không gửi ảnh ra ngoài (NFR-09).

(Nguồn: SRS 09 §Giao diện mô hình; SRS 10.)

## 5. Từ dự đoán tới candidate

1. Lọc dự đoán theo `τ_conf`.
2. Matching một-một không phụ thuộc lớp với annotation (xem [../03-domain/services.md §1](../03-domain/services.md#1-matchingservice)).
3. Dự đoán không ghép, confidence ≥ `τ_E1` ⇒ candidate E1; cặp ghép khác lớp, confidence lớp dự đoán ≥ `τ_E2` ⇒ candidate E2 (FR-ENG-07).
4. Evidence: box/lớp dự đoán, confidence, IoU, cặp ambiguous, crop, rule liên quan (FR-ENG-08).

`τ_m`, `τ_amb`: **TBD-05**. `τ_E1`, `τ_E2`: chọn trên tập hiệu chỉnh, khoá trong score version (SRS 07).

## 6. Trạng thái và coverage

- Đơn vị coverage: frame (R cấu hình MVP).
- Không có Detector khả dụng ⇒ Not checked (`no_model`), không sinh ranking giả (FR-ENG-09).
- Lỗi trên một số frame ⇒ retry tối đa theo cấu hình (**TBD-14**); còn lỗi ⇒ frame Failed cho engine này, run Partial (UC-02 4a).
- Tái lập: chế độ suy luận tất định hoặc lưu prediction để tái dùng (NFR-04).

## 7. Chống leakage (AS-03)

- **Giả định AS-03**: Detector không được huấn luyện trên ảnh của tập held-out. Nếu sai, recall bị thổi phồng, kết quả không hợp lệ (SRS 02; rủi ro RK-02).
- **Kiểm tra bắt buộc** (FR-EVL-05b): đối chiếu danh sách ảnh huấn luyện của Detector với held-out; có giao nhau thì **chặn** đánh giá. Kết quả kiểm lưu cùng evaluation run.
- Nếu không có danh sách ảnh huấn luyện của model, coi như không chứng minh được AS-03: chọn held-out từ phần chắc chắn không dùng huấn luyện (RK-02). Phần nào của BDD100K được dùng: **TBD-03**.
- Tập hiệu chỉnh và held-out tách theo video nguồn (FR-EVL-05a).

## 8. Đánh giá Detector (Metric engine)

- Precision/Recall của Detector theo lớp chỉ tính trên GT đã khoá; thiếu GT ⇒ Metric Not checked (FR-EVL-15; R B-05).
- Lớp không đủ mẫu ghi "không đủ mẫu" (H Calibration "Không đủ mẫu để đánh giá").
- Hiệu chỉnh mô hình tách khỏi hiệu chỉnh reviewer (H Calibration).
- Xem [evaluation.md](evaluation.md).

## 9. Ngoài phạm vi MVP

- Classifier thứ hai / Specialized Classifier, vehicle profile (R B-07, B-16).
- M1 pre-label và Diff (R B-16).
- Đổi Detector khác sau pilot chỉ khi held-out/audit chỉ ra slice thiếu recall (SRS RK-01; T §8).
