---
id: ai-vlm
title: Mô hình thị giác – ngôn ngữ (VLM)
type: reference
domain: ai
module: quality-control
tags: [ai, vlm, selective-check, pilot]
priority: 3
---
# Mô hình thị giác – ngôn ngữ (VLM)

## 1. Trạng thái trong pilot M13

- **Đề xuất**: VLM **không bật** trong pilot M13. Đây là đề xuất thu hẹp cho pilot, **cần Product Owner duyệt** — **TBD-08** (SRS [01-introduction.tex](../label-x_system-requirement-specification/sections/01-introduction.tex) §Phạm vi; FR-ENG-10, ưu tiên Could).
- Đề xuất này không kế thừa từ B-08 và không thay B-08. Kiến trúc B-08 vẫn là kiến trúc đã chốt nếu VLM được bật (R B-08).
- Khi tắt: engine "Mô hình thị giác – ngôn ngữ" hiển thị **Not checked** (`disabled`); không bao giờ coi là đạt (H AnalysisConfig; R B-19). Ba nhóm lỗi E1–E3 không phụ thuộc VLM.

## 2. Kiến trúc đã chốt nếu bật (B-08)

```
Candidate (từ engine khác trong run) → chọn theo policy → worker VLM kiểm chọn lọc → Evidence có cấu trúc
```

- VLM phụ thuộc candidate nên **không** chạy song song từ đầu với các engine sinh candidate (R B-08: "Chạy song song chưa giải quyết phụ thuộc candidate").
- Chỉ ghi Evidence/Candidate; không tự xác nhận lỗi; không có quyền quyết định, gate, release (R R-02; A ADR-07).
- Kết quả không rõ ⇒ uncertain/chuyển cấp cho người (T §4); lời giải thích của VLM không phải bằng chứng đã xác minh (T §3).
- Kiểm frame/revision và mapping crop về ảnh gốc trước khi dùng evidence (T §3, §9).

## 3. Hạn mức và retry (định hướng vận hành đã duyệt)

| Tham số | Giá trị | Nguồn |
|---|---|---|
| Candidate tối đa mỗi run | 400 | R cấu hình vận hành "budget"; H AnalysisConfig |
| Số lần thử mỗi lượt kiểm | Tối đa 3 lần **tổng cộng**, tính cả retry, nằm trong hạn mức lượt gọi | R B-08; H ExecutionHistory |
| Timeout mỗi lượt | Lấy từ đo pilot — **TBD-20** (Tech Lead, đội mô hình) | R cấu hình vận hành |
| Hạn mức tổng (lượt gọi, GPU, tiền) | Chưa đặt; Admin + đội mô hình đo, người phụ trách dự án duyệt | R cấu hình vận hành |

- 400 candidate không đồng nghĩa 400 lượt gọi nếu có retry (R).
- Hết hạn mức ⇒ dừng nhận lượt mới, ghi phần chưa kiểm; **không** chuyển thành đạt hay bác bỏ (R B-08; FR-ENG-10; T §6 "hết budget giữ unreviewed").
- Hết 3 lần thử ⇒ đơn vị đó Failed (lỗi thực thi), không pass, không reject annotation (SRS 05).

## 4. Coverage

- Đơn vị: candidate được trigger (R cấu hình MVP "Required units").
- Candidate không thoả điều kiện kiểm chọn lọc ⇒ Not checked `not_triggered`, **không** vào mẫu số (SRS 05 bảng trạng thái engine).
- Kiểm chọn lọc không tự thành yêu cầu quét mọi frame (R).

## 5. Điều kiện trước khi bật

| Điều kiện | Trạng thái |
|---|---|
| Product Owner bác đề xuất không bật (TBD-08) | Chưa |
| Model/provider được chọn; self-host hay API ngoài (A ưu tiên self-host; H chưa chốt) | Chưa chốt |
| Quyền xử lý ảnh: ảnh **không gửi ra ngoài** khi chưa được phép (FR-ENG-10; NFR-09) | Pilot: không gửi |
| Trigger/policy chọn candidate có version | Chưa chốt |
| Ablation chứng minh lợi ích trong budget (T §7–8; R thứ tự triển khai bước 4) | Chưa đo |

## 6. Mâu thuẫn nguồn

- H ghi VLM v0.9 "thử nghiệm"; B ghi v0.4. Không phiên bản nào được coi là model sẵn dùng (R mục 8).
- T đưa VLM + RAG vào giai đoạn D; A đưa AI Assistance vào P4. R B-13 chốt lookup trực tiếp, RAG sau MVP — RAG không đi kèm VLM trong MVP.

Liên quan: [safety-and-data.md](safety-and-data.md), [../03-domain/services.md](../03-domain/services.md#3-candidategenerationservice-engine).
