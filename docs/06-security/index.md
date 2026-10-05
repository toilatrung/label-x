---
id: security-overview
title: Security
type: reference
domain: security
module: repository
tags: [security, compliance, threat-model]
priority: 2
---
# Security

Tài liệu bảo mật của LabelX: threat model, chính sách bảo mật và tuân thủ dữ liệu. Nội dung dựa trên quyết định đã chốt (B-11, B-12, B-18 trong `docs/00-project/sources/architecture_review.html`) và SRS đã duyệt (FR-SEC, NFR-07…09). Repo hiện mới có khung dự án, nên phần lớn biện pháp là **yêu cầu phải hiện thực**. Chúng chưa phải chức năng đã có.

## Nội dung

- [threat-model.md](threat-model.md) — tài sản, ranh giới tin cậy (CVAT, Object Storage, GPU worker, trình duyệt), mối đe doạ STRIDE và biện pháp.
- [security-policies.md](security-policies.md) — RBAC theo vai trò và scope, self-review theo assignee tại snapshot, tách người yêu cầu/duyệt, waiver, Super Admin ghi đè, token CVAT, audit append-only, lưu trữ.
- [compliance.md](compliance.md) — dữ liệu BDD100K (giấy phép: TBD), không gửi ảnh ra ngoài (NFR-09), lưu trữ, bằng chứng kiểm toán.

## Nguyên tắc cứng

- Adapter CVAT **chỉ đọc**; sửa annotation bằng deep link sang CVAT (B-18).
- Quyền project/job kiểm ở API, không chỉ ẩn nút trên UI (B-12, FR-SEC-01).
- Token CVAT chỉ ở backend; secret không vào log (NFR-07).
