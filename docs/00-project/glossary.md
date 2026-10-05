---
id: project-glossary
title: Thuật ngữ LabelX
type: reference
domain: project
module: repository
tags: [glossary, terminology]
priority: 2
---

# Thuật ngữ LabelX

## Purpose

Thuật ngữ dùng chung trong tài liệu và giao diện LabelX, trích từ SRS M13 (bảng thuật ngữ, chương 1). Quy ước giao diện: viết đầy đủ tên (Quality Control, Intersection over Union, Ground Truth) theo Design System LabelX; viết tắt chỉ dùng trong tài liệu kỹ thuật.

Nguồn: [SRS M13](../01-business/labelX.html).



## Dữ liệu và annotation

| Thuật ngữ | Định nghĩa |
|---|---|
| Frame | Một ảnh là đơn vị review và xếp hạng. Với BDD100K detection, mỗi ảnh tĩnh là một frame. |
| Annotation | Một đối tượng được gán nhãn trên frame: Bounding box + lớp + thuộc tính. |
| Bounding box (BBox) | Hình chữ nhật song song trục $(x_1, y_1, x_2, y_2)$ theo pixel. |
| Taxonomy | Danh sách lớp và thuộc tính hợp lệ của dataset, có version. |
| Guideline | Hướng dẫn gán nhãn, chia thành rule có mã (ví dụ `VEH-03`) và version. |
| CVAT | Công cụ gán nhãn nguồn. Annotation chỉ được sửa trên CVAT (B-18). |
| Project / Task / Job | Cấp tổ chức dữ liệu trong CVAT; Job là phần việc giao cho một annotator. |
| Revision | Trạng thái annotation tại một thời điểm, nhận diện bằng hash nội dung đã chuẩn hoá. |
| Snapshot | Bản sao bất biến của annotation, metadata và ảnh tại một revision; mọi phân tích chạy trên snapshot (B-02). |
| Drift | Annotation trên CVAT thay đổi trong lúc đang export snapshot; phải phát hiện và chặn khoá. |

## Phân tích và xếp hạng

| Thuật ngữ | Định nghĩa |
|---|---|
| Engine | Thành phần kiểm tra tạo candidate. M13 dùng Schema/Taxonomy, Geometry, Duplicate/Overlap, Mô hình độc lập (Detector) và Metric. |
| QC Run | Một lần chạy các engine trên một snapshot với cấu hình, seed và version cố định. |
| Detector | Mô hình phát hiện đối tượng độc lập với người gán nhãn, dùng sinh candidate thiếu box và sai lớp. Không phải Ground Truth. |
| Matching | Ghép một-một giữa box của Detector (hoặc reference) với annotation theo IoU, hình học trước rồi mới so lớp (B-21). |
| IoU | Intersection over Union — tỉ lệ diện tích giao trên diện tích hợp của hai box. |
| Candidate | Nghi vấn do engine sinh ra, chưa được người xác nhận. Candidate không phải lỗi. |
| Issue | Đơn vị công việc review sau khi gộp các candidate trùng (B-10). Có vòng đời riêng. |
| Evidence (bằng chứng) | Dữ liệu giải thích candidate: box của Detector, confidence, IoU, rule vi phạm, guideline, case tương tự. |
| Risk score $s(f)$ | Điểm rủi ro của frame $f$, dùng để xếp hạng. Có version công thức. |
| Ranking $\pi$ | Thứ tự frame giảm dần theo $s(f)$, có quy tắc phá hoà cố định. |
| Top-$k$% | Tập $\lceil k\cdot N/100\rceil$ frame đứng đầu ranking trong tập $N$ frame. |
| Coverage ledger | Sổ ghi phần đơn vị đã kiểm/chưa kiểm theo từng engine với mẫu số áp dụng (B-04). |
| Not checked / Partial / Failed | Trạng thái công khai của engine: chưa kiểm, kiểm một phần, lỗi thực thi. Không bao giờ được coi là đạt (B-19). |

## Review và quy trình

| Thuật ngữ | Định nghĩa |
|---|---|
| Review queue | Hàng đợi issue/frame cho reviewer, tách theo nguồn (rủi ro, ngẫu nhiên). |
| Review Workspace | Màn hình xem frame, annotation, bằng chứng và ra quyết định. |
| Quyết định review | Một trong: Xác nhận lỗi, Bác bỏ, Chưa chắc chắn, Chuyển cấp trên. |
| False alarm (cảnh báo sai) | Candidate/issue bị reviewer bác bỏ hoặc phân xử là không lỗi. |
| Escalation / Adjudication | Chuyển issue chưa đủ căn cứ cho Quality Assurance Lead phân xử. |
| Guideline Gap | Ghi nhận chỗ guideline thiếu, phát sinh từ phân xử. |
| Rework | Yêu cầu annotator sửa trên CVAT; tạo revision mới. |
| Re-check / Verify | Chạy lại engine bị ảnh hưởng trên revision mới và reviewer xác minh trước khi đóng issue. |
| QC run cuối | QC Run trên snapshot của revision đã sửa; mọi báo cáo và phát hành trỏ về run này (B-03). |
| Lease | Quyền giữ tạm một issue/frame cho một reviewer, tránh hai người cùng xử lý. |
| Self-review | Reviewer review annotation do chính mình gán; backend phải chặn (B-12). |
| Waiver | Miễn trừ có thời hạn cho một điều kiện gate, cần người duyệt khác người yêu cầu (B-11). |
| Quality Gate | Tập điều kiện phải đạt trước khi một revision được coi là dùng được. |

## Đánh giá

| Thuật ngữ | Định nghĩa |
|---|---|
| Reference | Gồm annotation chuẩn (GT) của toàn bộ tập đánh giá và tập lỗi suy ra từ GT; cùng khoá version trước khi đo (B-20, mục tương ứng trong labelX.html). |
| Ground Truth | Annotation chuẩn đã được chuyên gia duyệt và khoá. Không model nào được mặc định là Ground Truth. |
| Lỗi đã xác minh | Một phần tử của tập lỗi $E$: bản ghi gắn một nhóm lỗi với một đối tượng GT (E1, E2) hoặc một annotation dư (E3), suy ra từ GT và được người xác minh duyệt. |
| Tập hiệu chỉnh / held-out | Tập dùng tinh chỉnh công thức điểm và tập chỉ dùng đo nghiệm thu; không giao nhau. |
| Recall@20% | Tỉ lệ lỗi đã xác minh nằm trong 20% frame đầu của ranking (mục tương ứng trong labelX.html). |
| Effort | Tổng thời gian thao tác có ích của reviewer/QA, gồm xử lý cảnh báo sai và kiểm lại sau sửa (mục tương ứng trong labelX.html). |
| Baseline | Quy trình review thủ công hiện tại, không có ranking và bằng chứng. |
| Assisted | Quy trình review có trợ lý M13. |
| Residual error rate | Tỉ lệ lỗi còn lại sau quy trình, đo trên reference. |
| Non-inferiority | Kiểm định chất lượng nhánh assisted không kém baseline quá biên $\delta$. |
| Bootstrap | Phương pháp lấy mẫu lại để ước lượng khoảng tin cậy. |
| Model Orchestrator | Thành phần tổng hợp kết quả đánh giá engine trên reference, kèm provenance; không dùng model làm trọng tài (B-05). Đặc tả chi tiết TBD-21. |

## Viết tắt

| Thuật ngữ | Định nghĩa |
|---|---|
| QA / QC | Quality Assurance / Quality Control. |
| SRS | Software Requirements Specification. |
| RBAC | Role-Based Access Control. |
| VLM | Vision–Language Model — mô hình thị giác – ngôn ngữ. |
| DRF | Django REST framework. |
| MVP | Minimum Viable Product. |
| KPI | Key Performance Indicator. |
