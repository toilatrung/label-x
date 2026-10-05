---
id: business-domain-model
title: Mô hình nghiệp vụ — dữ liệu, nhóm lỗi, quy tắc
type: reference
domain: business
module: domain
tags: [domain, errors, business-rules, bdd100k]
priority: 2
---

# Mô hình nghiệp vụ — dữ liệu, nhóm lỗi, quy tắc

## Purpose

Khái niệm nghiệp vụ cốt lõi của M13: dữ liệu BDD100K, ba nhóm lỗi, quy tắc đếm lỗi và lập reference. Thiết kế aggregate/value object kỹ thuật ở `docs/03-domain/`.

Nguồn chuẩn: [labelX.html](labelX.html) (bản HTML) và `docs/label-x_system-requirement-specification/` (bản LaTeX), SRS M13 v1.0, 05/10/2026. Khi có khác biệt, bản LaTeX là gốc; HTML được sinh lại bằng `python3 scripts/srs_tex2html.py`.

## Dữ liệu

BDD100K 2D detection, ảnh 1280×720, 10 lớp: `car`, `truck`, `bus`, `train`, `motorcycle`, `bicycle`, `pedestrian`, `rider`, `traffic light`, `traffic sign`. Thuộc tính cảnh (thời tiết, loại cảnh, thời điểm) và cờ `occluded`/`truncated` dùng để phân tầng và báo cáo theo slice. Tập hiệu chỉnh và held-out tách theo video nguồn.

## Nhóm lỗi

| Nhóm | Định nghĩa | Nguồn candidate | Tiêu chí xác minh |
|---|---|---|---|
| **E1** Thiếu box | Đối tượng thuộc 10 lớp, đủ điều kiện gán nhãn theo guideline, nhưng không có annotation nào ghép được. | Detector: box dự đoán không ghép được với annotation nào (unmatched prediction) và confidence $\ge \tau_{E1}$. | Reviewer thấy đối tượng thật, thuộc lớp trong phạm vi, không thuộc vùng/kích thước được bỏ qua (mục tương ứng trong labelX.html). |
| **E2** Sai lớp | Annotation ghép được với đối tượng thật nhưng lớp khác lớp đúng theo guideline. | Detector: cặp ghép được về hình học (IoU $\ge \tau_m$) nhưng lớp dự đoán khác lớp annotation, confidence $\ge \tau_{E2}$. | Reviewer xác định lớp đúng theo rule guideline (ví dụ `VEH-03`); nếu guideline không đủ thì chuyển phân xử. |
| **E3** Trùng box | Hai hay nhiều annotation cho cùng một đối tượng. | Duplicate/Overlap: cặp annotation có IoU $\ge 0,85$ (D-002) *chỉ sinh nghi vấn*; Detector bổ trợ khi chỉ có một dự đoán phủ cả hai. | Reviewer xác nhận các box cùng trỏ một đối tượng. Hai đối tượng thật chồng lấp (xe đỗ sát nhau) *không* là lỗi. Trong reference, E3 suy ra theo BR-04. |

Hoãn trong bản đầu: box lệch/lỏng (B-06), box quá nhỏ (chỉ là cảnh báo cấu trúc), sai thuộc tính, lỗi track.

## Quy tắc nghiệp vụ

| Mã | Quy tắc |
|---|---|
| BR-01 | Mỗi lỗi là một bản ghi có ID, gắn đúng một nhóm lỗi và đúng một đối tượng: *đối tượng GT* với E1/E2, hoặc *annotation dư* với E3. |
| BR-02 | **E1:** mỗi $g \in G$ không nằm trong cặp nào của $M$ sinh một lỗi E1 (gắn với $g$). |
| BR-03 | **E2:** mỗi cặp $(g, a) \in M$ có lớp khác nhau sinh một lỗi E2 (gắn với $g$). |
| BR-04 | **E3:** annotation $a$ không nằm trong $M$, có IoU $\ge \tau_m$ với ít nhất một $g$ *đã có cặp chính* trong $M$, sinh một lỗi E3 gắn với $a$. Nếu $a$ thoả với nhiều $g$, chọn $g$ có IoU lớn nhất, phá hoà theo ID nhỏ hơn. Một cụm $m$ box cho cùng đối tượng sinh $m-1$ lỗi E3. |
| BR-05 | Lớp của annotation dư không xét: annotation dư chỉ tính E3, không tính thêm E2. Cặp chính sai lớp vẫn tính E2 theo BR-03. |
| BR-06 | Annotation không khớp GT nào và không thoả BR-04 (box thừa trên vùng không có đối tượng) *không thuộc E1–E3*. Nó được ghi nhận và báo cáo riêng nhưng nằm ngoài KPI của pilot. |
| BR-07 | Vùng/đối tượng được bỏ qua (*ignore*): đối tượng GT có diện tích dưới $a_{min}$ TBD-06, hoặc bị che/cắt mép quá mức theo guideline. Lỗi gắn với đối tượng ignore không tính vào cả tử số lẫn mẫu số. |
| BR-08 | Nhiều candidate từ nhiều engine trỏ cùng một (đối tượng, nhóm) được gộp thành một issue (B-10). Gộp candidate không thay đổi $E$. |
| BR-09 | Mức độ nghiêm trọng (Nghiêm trọng / Trung bình / Nhẹ) do QA Lead định nghĩa theo lớp và kích thước TBD-07; dùng cho guardrail G-2. |
| BR-10 | Người xác minh *không* được xem ranking, risk score hay candidate của tập đánh giá (mù với công cụ). |
| BR-11 | Hai người gán GT độc lập trên toàn bộ frame; hai bản được ghép theo matching ở mục tương ứng trong labelX.html, phần không khớp do QA Lead phân xử. Tỉ lệ khớp trước phân xử được báo cáo. |
| BR-12 | Người xác minh không xác minh annotation do chính mình gán (self-review, B-12). |
| BR-13 | GT, snapshot annotation đầu vào, mapping GT–annotation, các ngưỡng ($\tau_m$, $a_{min}$) và version thuật toán matching được khoá cùng nhau. Mọi chỉnh sửa sau khoá tạo version mới, ghi lý do; kết quả đo trỏ đúng version. |
| BR-14 | Khi người duyệt bác một lỗi do matching sai, phải sửa mapping (ghi lý do) rồi *suy lại* $E$; không được xoá lỗi trực tiếp khỏi danh sách. |
| BR-15 | Lỗi chèn có kiểm soát (nếu dùng, TBD-04) chỉ là bổ sung, được gắn cờ riêng và báo cáo tách khỏi lỗi tự nhiên. |
| BR-16 | Kho case phân xử dùng cho guideline (hiệu chỉnh) và GT của tập held-out phải tách riêng, tránh đánh giá trên dữ liệu đã dùng để hiệu chỉnh. |
| BR-17 | Metric engine dùng chung GT nhưng có đặc tả matching riêng nếu phép đo yêu cầu (ví dụ ngưỡng IoU theo lớp); không dùng Detector làm trọng tài (B-05). |

## Khái niệm chính

| Khái niệm | Ý nghĩa |
|---|---|
| Revision | Trạng thái annotation tại một thời điểm, nhận diện bằng hash nội dung đã chuẩn hoá. |
| Snapshot | Bản sao bất biến của annotation, metadata và ảnh tại một revision; mọi phân tích chạy trên snapshot (B-02). |
| QC Run | Một lần chạy các engine trên một snapshot với cấu hình, seed và version cố định. |
| Candidate | Nghi vấn do engine sinh ra, chưa được người xác nhận. Candidate không phải lỗi. |
| Issue | Đơn vị công việc review sau khi gộp các candidate trùng (B-10). Có vòng đời riêng. |
| Evidence (bằng chứng) | Dữ liệu giải thích candidate: box của Detector, confidence, IoU, rule vi phạm, guideline, case tương tự. |
| Risk score $s(f)$ | Điểm rủi ro của frame $f$, dùng để xếp hạng. Có version công thức. |
| Coverage ledger | Sổ ghi phần đơn vị đã kiểm/chưa kiểm theo từng engine với mẫu số áp dụng (B-04). |
| Rework | Yêu cầu annotator sửa trên CVAT; tạo revision mới. |
| QC run cuối | QC Run trên snapshot của revision đã sửa; mọi báo cáo và phát hành trỏ về run này (B-03). |
| Lease | Quyền giữ tạm một issue/frame cho một reviewer, tránh hai người cùng xử lý. |
| Waiver | Miễn trừ có thời hạn cho một điều kiện gate, cần người duyệt khác người yêu cầu (B-11). |
| Quality Gate | Tập điều kiện phải đạt trước khi một revision được coi là dùng được. |
| Reference | Gồm annotation chuẩn (GT) của toàn bộ tập đánh giá và tập lỗi suy ra từ GT; cùng khoá version trước khi đo (B-20, mục tương ứng trong labelX.html). |
| Lỗi đã xác minh | Một phần tử của tập lỗi $E$: bản ghi gắn một nhóm lỗi với một đối tượng GT (E1, E2) hoặc một annotation dư (E3), suy ra từ GT và được người xác minh duyệt. |
