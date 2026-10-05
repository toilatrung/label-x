---
id: project-contract
title: Project Contract Intake
type: reference
domain: api
module: repository
tags: [contract, interface, intake]
priority: 1
---
# Project Contract Intake

## Purpose

Theo dõi việc tiếp nhận và kiểm tra hợp đồng giao diện có thẩm quyền của LabelX QC: REST API nội bộ, Celery task, và giao diện với CVAT và mô hình.

## Input Status

- **Status**: `ingested`
- **Authority**: `established` — SRS §9 (Giao diện ngoài) đã duyệt; quyết định B-10, B-12, B-17, B-18 trong nguồn R
- **Source Artifact**:
  - SRS: [09-interfaces.tex](../label-x_system-requirement-specification/sections/09-interfaces.tex) (bảng `tab:api`, `tab:apierrors`, `tab:cvatapi`, giao diện mô hình), [05-dynamics.tex](../label-x_system-requirement-specification/sections/05-dynamics.tex) (bảng transition), [06-functional.tex](../label-x_system-requirement-specification/sections/06-functional.tex)
  - R: [architecture_review.html](../00-project/sources/architecture_review.html)
  - A §25 (API & Event Contract), chỉ dùng phần khớp SRS: [Quality_Control_Review_UX_Architecture.html](../00-project/sources/Quality_Control_Review_UX_Architecture.html)
  - T §6 (idempotency, chunk, retry): [QC_Engine_Review_Report.html](../00-project/sources/QC_Engine_Review_Report.html)
  - Cấu hình hiện có: [settings.py](../../src/backend/config/settings.py), [urls.py](../../src/backend/config/urls.py)
- **Ingested Date**: `2026-10-05`
- **Validated By**: `claude-agent (đối chiếu nguồn); cần Tech Lead xác nhận`

## Required Content

| Nội dung | Tài liệu |
|---|---|
| Phạm vi, các bên, nghĩa vụ, loại trừ | [rest-api.md](rest-api.md) mục 1, 4.2 (endpoint không triển khai) |
| Hợp đồng interface có mã ổn định | [rest-api.md](rest-api.md); [event-contracts.md](event-contracts.md) |
| Dữ liệu, bảo mật, tuân thủ | [rest-api.md](rest-api.md) mục 6; [CVAT](../11-integrations/cvat.md) |
| Mức dịch vụ, điều kiện nghiệm thu | NFR-01…03 là đề xuất, chưa chốt: **TBD-13** |
| Version, ownership, hiệu lực | OpenAPI do drf-spectacular sinh, `VERSION 0.1.0` (settings) |

## Validation Result

- Toàn bộ 28 endpoint trong `tab:api` của SRS đã được đưa vào [rest-api.md](rest-api.md), kèm quyền, idempotency và mã lỗi 400/403/404/409/422.
- Endpoint của A chỉ được nhận khi khớp một FR của SRS. Các endpoint release, assistant, calibration session và SSE bị loại (B-13, FR-GTE-04).
- Mâu thuẫn đã xử lý:
  - Tiền tố `/api/qc/v1` (A) đổi thành `/api/` (SRS).
  - Mã lỗi 412 `REVISION_DRIFT` (A) đổi thành 409.
  - Lease theo issue (A) đổi thành lease theo frame (SRS).
  - Header `Idempotency-Key` (kể cả mức "bắt buộc" cho các POST quyết định) là **đề xuất thiết kế**, cần Tech Lead xác nhận.
- Blocker hợp đồng trước đây: **resolved by source artifacts**.
- Còn mở: endpoint CVAT thật và phiên bản (TBD-01); thời hạn lease (TBD-09); retry/backoff (TBD-14); vai trò Product Owner và Data/Model Owner trong `role_assignment` (SRS ch.6 đã nêu quyền, schema cần bổ sung); danh sách điều kiện được waiver (TBD-19).

## Related Files

- [REST API](rest-api.md)
- [Celery task và sự kiện](event-contracts.md)
- [Kiến trúc hệ thống](../02-architecture/system-design.md)
- [Roadmap](../../.agent/planning/roadmap.md)

## Forbidden Actions

- Không thêm trường, endpoint hay mức dịch vụ ngoài SRS khi chưa có quyết định mới.
- Không thêm endpoint ghi annotation lên CVAT (B-18).
- Không gán số cho các mục TBD.
