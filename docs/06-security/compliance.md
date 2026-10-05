---
id: security-compliance
title: Tuân thủ và dữ liệu LabelX
type: reference
domain: security
module: repository
tags: [compliance, data-privacy, bdd100k, license, retention]
priority: 2
---
# Tuân thủ và dữ liệu LabelX

## Mục đích

Ghi các ràng buộc tuân thủ cho dữ liệu và kết quả của LabelX ở pilot M13: giấy phép dữ liệu, riêng tư ảnh, lưu trữ và bằng chứng kiểm toán. Repo **chưa có** văn bản pháp lý hay đánh giá tuân thủ nào. Những gì chưa được xác nhận được ghi rõ là TBD.

## 1. Dữ liệu BDD100K

Nguồn: SRS `03-data-errors.tex` (mục Dữ liệu BDD100K cho M13), `01-introduction.tex` (tài liệu tham khảo).

- M13 dùng phần **2D object detection** của BDD100K: ảnh camera hành trình 1280×720, Bounding box cho 10 lớp đối tượng giao thông.
- Bộ dữ liệu được trích dẫn trong SRS: F. Yu và cộng sự, *BDD100K: A Diverse Driving Dataset for Heterogeneous Multitask Learning*, CVPR 2020.
- Danh sách ảnh cụ thể (tập `val` hay `train`) và số frame của tập hiệu chỉnh/held-out: **TBD-03**.
- Nguồn annotation cần review (đội gán nhãn tạo mới trên CVAT hay nhãn gốc BDD100K): **TBD-04**.

### Giấy phép và điều khoản sử dụng — TBD-18

| Câu hỏi cần xác nhận | Trạng thái |
|---|---|
| Giấy phép/điều khoản sử dụng BDD100K có cho phép mục đích của dự án (nội bộ, thương mại hay nghiên cứu) không | **TBD-18** — chưa xác nhận (SRS `11-traceability.tex`: Data Owner, trước nạp dữ liệu) |
| Có được lưu bản sao ảnh trong Object Storage nội bộ và tạo crop evidence không | **TBD-18** (phần lưu trữ nội bộ) |
| Có được dùng ảnh để huấn luyện/hiệu chỉnh Detector và phân phối model artifact không | **TBD** — ngoài nội dung TBD-18 hiện ghi; đề xuất Data Owner xác nhận cùng TBD-18 |
| Có được đưa ảnh/crop vào báo cáo xuất (PDF, CSV, JSON) chia sẻ ngoài đội không | **TBD** — ngoài nội dung TBD-18 hiện ghi; đề xuất Data Owner xác nhận cùng TBD-18 |
| Yêu cầu ghi công/trích dẫn khi công bố kết quả | **TBD** — ngoài nội dung TBD-18 hiện ghi; đề xuất Data Owner xác nhận cùng TBD-18 |

Người chịu trách nhiệm đề xuất: **Data Owner** (SRS `00-frontmatter.tex`: "Data/Model Owner — Dữ liệu BDD100K, Detector baseline"). Hạn chốt theo SRS: **trước nạp dữ liệu** (TBD-18). Tài liệu này không diễn giải điều khoản giấy phép, vì repo chưa có văn bản giấy phép làm căn cứ.

## 2. Riêng tư dữ liệu ảnh (NFR-09)

- Ảnh BDD100K **chỉ lưu trong Object Storage nội bộ**; **không gửi ảnh ra dịch vụ ngoài** trong pilot (NFR-09). Cách kiểm: rà soát cấu hình.
- Detector chạy trong GPU worker nội bộ; không gửi ảnh ra ngoài (SRS `09-interfaces.tex`, giao diện mô hình).
- Ảnh camera hành trình có thể chứa **mặt người, biển số** (A mục 28).
- Engine thị giác – ngôn ngữ (VLM): SRS đề xuất **không bật** trong pilot M13, cần Product Owner duyệt (**TBD-08**, FR-ENG-10).
- Khác biệt nguồn: A mục 28 cho phép "chỉ gửi API ngoài khi được phép, gửi crop tối thiểu". SRS NFR-09 (bản đã duyệt) cấm gửi ảnh ra ngoài trong pilot. **Áp dụng NFR-09.** Mọi thay đổi sau pilot cần change request.
- Kiểm tra tối thiểu khi rà soát cấu hình (đề xuất): không có endpoint hay khoá API của dịch vụ suy luận bên ngoài trong biến môi trường; `OBJECT_STORAGE_ENDPOINT_URL` trỏ tới storage nội bộ; bucket không bật truy cập công khai.

## 3. Lưu trữ và kết thúc lưu (NFR-08)

- Audit, evidence, snapshot, reference được giữ chừng nào dataset còn cần quản lý hoặc đối chiếu. Kết thúc lưu do **người quản lý dữ liệu xác nhận** và được ghi audit (NFR-08; phiếu chốt R, định hướng lưu).
- Thời hạn lưu audit tối thiểu: **TBD-15**.
- Không tự đặt ngày xoá, không tự xoá dữ liệu nghiệp vụ. Chỉ dọn cache/crop tạm tái tạo được.
- Chi tiết: [security-policies.md](security-policies.md) mục 8.

## 4. Bằng chứng kiểm toán và nghiệm thu

- Mục tiêu R-05 "Phân quyền và kiểm toán mọi quyết định": backend chặn self-review/ngoài scope; audit đủ actor/revision/lý do (R, ma trận R-01…R-07; SRS AC-05, AC-11).
- Mọi số liệu hiển thị có provenance truy về run, snapshot, version (NFR-14).
- A mục 28 đề xuất export audit theo release cho nghiệm thu. Phát hành nằm ngoài phạm vi M13 (FR-GTE-04), nên đây là việc sau M13.
- Pre-registration tham số đánh giá, audit mọi thay đổi version để tránh chỉnh sau khi thấy held-out (RK-09).

## 5. Giấy phép phần mềm

- `LICENSE.agentic-sdlc-kit` ở gốc repo là giấy phép của bộ kit quy trình. Repo **chưa có** file giấy phép cho chính mã nguồn LabelX.
- Giấy phép dependency (Python trong `src/backend/uv.lock`, Node trong `src/frontend/package-lock.json`) **chưa được rà soát**. Đề xuất bổ sung bước kiểm giấy phép dependency khi có CI (xem [../08-devops/ci-cd.md](../08-devops/ci-cd.md)).

## Liên quan

- [threat-model.md](threat-model.md)
- [security-policies.md](security-policies.md)
