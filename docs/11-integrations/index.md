---
id: integrations-overview
title: Integrations
type: reference
domain: integrations
module: repository
tags: [integrations, contracts, external-systems]
priority: 3
---
# Integrations

Tài liệu về các hệ thống ngoài: chủ sở hữu, hợp đồng, xác thực, luồng dữ liệu, xử lý lỗi và cách kiểm thử.

## Contents

| Hệ thống | Tài liệu | Hướng | Trạng thái |
|---|---|---|---|
| CVAT | [cvat.md](cvat.md) | LabelX **chỉ đọc**; sửa annotation qua deep link | Phiên bản, URL và quyền: TBD-01 |
| Object Storage (S3-compatible) | [object-storage.md](object-storage.md) | Đọc/ghi blob bất biến (`labelx-snapshots`, `labelx-evidence`, `labelx-reports`) | Dev dùng SeaweedFS; môi trường thật dùng hạ tầng hiện có |

## Ngoài phạm vi MVP

- Dịch vụ VLM ngoài (B-08; TBD-08; NFR-09: không gửi ảnh ra ngoài).
- Guideline RAG / Vector Index (B-13).
- SSO OIDC dùng chung với CVAT (A §20); MVP dùng session LabelX (SRS §9.3).
- Ghi annotation hoặc issue/comment lên CVAT (B-18).

Liên quan: [system-design.md](../02-architecture/system-design.md), [rest-api.md](../04-api/rest-api.md).
