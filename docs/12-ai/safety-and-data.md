---
id: ai-safety-and-data
title: An toàn AI và xử lý dữ liệu
type: reference
domain: ai
module: quality-control
tags: [ai, safety, data-handling, human-in-the-loop]
priority: 1
---
# An toàn AI và xử lý dữ liệu

Các ràng buộc bắt buộc với mọi thành phần AI (Detector, ranking, VLM nếu bật) trong LabelX. Nguồn: R [architecture_review.html](../00-project/sources/architecture_review.html) (R-02, B-05, B-08, B-12, B-18, cấu hình vận hành), SRS [08-nonfunctional.tex](../label-x_system-requirement-specification/sections/08-nonfunctional.tex), [06-functional.tex](../label-x_system-requirement-specification/sections/06-functional.tex), H ReviewWorkspace/ModelsGuidelines/QualityGate.

## 1. Con người quyết định

| Mã | Quy tắc | Nguồn |
|---|---|---|
| S-01 | Candidate là nghi vấn; chỉ người (Reviewer, QA Lead) xác nhận, bác bỏ, phân xử. Trợ lý chỉ cung cấp bằng chứng. | R R-02; H ReviewWorkspace; SRS 02 §Bối cảnh |
| S-02 | Không có đường API nào để AI ghi `ReviewDecision`, phân xử, waiver, gate hay phê duyệt. Service account của worker AI chỉ ghi Candidate/Evidence. | A ADR-07; R R-02 |
| S-03 | Không tự đóng/xác nhận issue theo confidence; mọi issue cần quyết định của người (AC-04). | A §24.3; SRS AC-04 |
| S-04 | Mô hình chưa xác minh không tự biến candidate thành lỗi đã xác nhận. | H ModelsGuidelines |
| S-05 | Hệ thống không tự quyết định phát hành; gate chỉ tính điều kiện, người có quyền duyệt. | H QualityGate; R F-08 |
| S-06 | Model không dùng làm Ground Truth hay trọng tài; accuracy chỉ đo trên reference đã duyệt. | R B-05; SRS BR-17 |
| S-07 | Confidence không phải xác suất lỗi hay độ chính xác; agreement không gọi là accuracy. | R B-07, B-21 |

## 2. Giảm thiên lệch do tự động hoá (automation bias)

- Lát kiểm tra ngẫu nhiên độc lập ranking để thấy lỗi không có candidate (FR-RNK-07; RK-04).
- Frame Review luôn hiển thị toàn ảnh; reviewer tạo được issue thủ công cho lỗi không có candidate (FR-REV-06, FR-REV-09).
- Đo KPI-2b (recall phát hiện thực tế) và residual ở cả hai nhánh thí nghiệm (SRS 07).
- Nhánh baseline ẩn ranking/score/evidence (FR-EVL-12). T gợi ý hạn chế gợi ý AI ở vòng đầu random audit — chưa là yêu cầu SRS.

## 3. Dữ liệu không gửi ra ngoài

| Mã | Quy tắc | Nguồn |
|---|---|---|
| D-00 | Giấy phép và điều khoản sử dụng BDD100K cho pilot và lưu trữ nội bộ phải được Data Owner xác nhận trước khi nạp dữ liệu (**TBD-18**). | SRS 11 |
| D-01 | Ảnh BDD100K chỉ lưu trong Object Storage nội bộ (S3-compatible hiện có); không gửi ảnh ra dịch vụ ngoài trong pilot. | NFR-09 |
| D-02 | Detector chạy trong GPU worker nội bộ. | SRS 09 §Giao diện mô hình |
| D-03 | VLM (nếu bật): ảnh không gửi ra ngoài khi chưa được phép; self-host hay API ngoài chưa chốt. | FR-ENG-10; R B-08 |
| D-04 | Token CVAT chỉ ở backend (secret store), không xuống client, không xuất hiện trong log. | FR-SNP-02; NFR-07 |
| D-05 | Adapter CVAT chỉ dùng thao tác đọc; không ghi annotation. Service account CVAT chỉ đọc. | FR-SNP-01; R B-18 |
| D-06 | Truy cập media theo quyền dự án; backend kiểm quyền mọi request và lọc danh sách theo scope. | FR-SEC-01; R B-12 |

Dev local dùng SeaweedFS thay Object Storage (xem [DEC-001](../../.agent/governance/decisions/DEC-001.md)); không đưa ảnh dữ liệu thật lên dịch vụ ngoài.

## 4. Tách tập dữ liệu và chống rò rỉ

- Tập hiệu chỉnh ↔ held-out không giao theo video; Detector không huấn luyện trên held-out (AS-03); case phân xử dùng hiệu chỉnh tách khỏi GT held-out (FR-EVL-05; BR-16). Chi tiết: [detector.md §7](detector.md#7-chống-leakage-as-03), [evaluation.md §2](evaluation.md#2-phân-chia-dữ-liệu-và-chống-rò-rỉ).
- Người xác minh reference mù với ranking/candidate (BR-10).
- Pre-registration: khoá tham số trước khi chạy held-out; không chỉnh sau khi thấy kết quả (RK-09).

## 5. Provenance và kiểm toán

- Mọi candidate truy về engine/model version, artifact checksum, config, run, snapshot (FR-ENG-01).
- Mọi số liệu hiển thị có provenance; số liệu chưa đủ dữ liệu hiển thị Not checked / không đủ mẫu (NFR-14; FR-RPT-03).
- Audit append-only, cùng transaction, cho quyết định, phân xử, waiver, khoá reference, thay đổi cấu hình/version (FR-SEC-05; AC-11).

## 6. Lưu giữ dữ liệu

- Giữ snapshot, reference version, evidence nguồn, quyết định/audit, report khi dataset còn cần quản lý/đối chiếu; kết thúc lưu do người quản lý dữ liệu xác nhận và ghi audit (R cấu hình vận hành "retention"; NFR-08).
- Cache/crop tạm chỉ dọn khi không còn công việc dùng và tái tạo được từ nguồn giữ nguyên; blob không có metadata trỏ tới sau `t_gc` được job dọn (NFR-06; `t_gc`: **TBD-20**).
- Thời hạn lưu tối thiểu audit: **TBD-15**. RPO/RTO sao lưu: **TBD-17**. Chưa tự đặt số ngày/tháng.

## 7. Phân quyền liên quan AI và đánh giá

- Self-review bị chặn ở backend theo assignee tại snapshot (FR-SEC-03; AC-05).
- Người duyệt (waiver, khoá reference, phân xử) khác người yêu cầu; không dùng tài khoản khác của cùng người (FR-SEC-04).
- Super Admin không là người duyệt mặc định; ghi đè có lý do, gắn nhãn audit (FR-SEC-06).

## 8. Ngoài phạm vi MVP

Guideline RAG/LLM trả lời câu hỏi (A "AI Assistant Panel", `assistant/query`) không thuộc MVP (R B-13; FR-GDL-04). Annotation writeback từ AI hay từ QC không thuộc MVP (R B-18).
