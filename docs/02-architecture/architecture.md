---
id: project-architecture
title: Architecture Document Intake
type: reference
domain: architecture
module: repository
tags: [architecture, design, intake]
priority: 1
---
# Architecture Document Intake

## Purpose

Theo dõi việc tiếp nhận và kiểm tra các tài liệu kiến trúc có thẩm quyền của LabelX (module Quality Control quanh CVAT).

## Input Status

- **Status**: `ingested`
- **Authority**: `established` — các quyết định B-01…B-21 và cấu hình MVP do người dùng chốt ngày 05/10/2026; stack đã chốt trong DEC-001
- **Source Artifact**:
  - R (quyết định chốt, ưu tiên cao nhất): [architecture_review.html](../00-project/sources/architecture_review.html)
  - SRS đã duyệt (ưu tiên ngang R): [main.tex](../label-x_system-requirement-specification/main.tex), các chương [03](../label-x_system-requirement-specification/sections/03-data-errors.tex), [05](../label-x_system-requirement-specification/sections/05-dynamics.tex), [06](../label-x_system-requirement-specification/sections/06-functional.tex), [09](../label-x_system-requirement-specification/sections/09-interfaces.tex), [10](../label-x_system-requirement-specification/sections/10-architecture.tex), [11](../label-x_system-requirement-specification/sections/11-traceability.tex)
  - H (chuẩn hành vi màn hình): [docs/design/screens](../design/screens/Main.dc.html)
  - A (kiến trúc UX, ADR, entity, API): [Quality_Control_Review_UX_Architecture.html](../00-project/sources/Quality_Control_Review_UX_Architecture.html)
  - T (engine, contract xử lý, pilot): [QC_Engine_Review_Report.html](../00-project/sources/QC_Engine_Review_Report.html)
  - L (sơ đồ thành phần): [mermaid-diagram.png](../00-project/sources/mermaid-diagram.png)
  - Stack: [DEC-001](../../.agent/governance/decisions/DEC-001.md), [docker-compose.dev.yml](../../infrastructure/docker-compose.dev.yml), [pyproject.toml](../../src/backend/pyproject.toml)
- **Ingested Date**: `2026-10-05`
- **Validated By**: `claude-agent (đối chiếu nguồn); cần project-owner xác nhận lần cuối`

Thứ tự ưu tiên khi các nguồn mâu thuẫn: R và SRS > H > A/T > L.

## Required Content

| Nội dung | Tài liệu |
|---|---|
| Bối cảnh, ranh giới, thành phần, trách nhiệm | [system-design.md](system-design.md) mục 1–3 |
| Topology triển khai, phụ thuộc runtime | [system-design.md](system-design.md) mục 9; [diagrams/deployment.md](diagrams/deployment.md) |
| Luồng dữ liệu, lưu trữ, ranh giới tích hợp | [diagrams/data-flow.md](diagrams/data-flow.md); [schema](../05-database/schema.md); [CVAT](../11-integrations/cvat.md); [Object Storage](../11-integrations/object-storage.md) |
| Bảo mật, độ tin cậy, khả năng vận hành | [system-design.md](system-design.md) mục 6–9 |
| Ràng buộc, đánh đổi, quyết định, truy vết | [decisions.md](decisions.md) |

## Validation Result

- Đã đối chiếu 21 quyết định trong R với SRS (ch.5, 6, 9, 10) và DEC-001. Không có quyết định nào trong R bị SRS phủ định.
- Một số nội dung của A/T đã bị R thay đổi hoặc loại bỏ: FastAPI, RAG/pgvector, temporal, Diff, writeback, Release/Manifest, OIDC, các trạng thái Known Defect/Superseded/NOT_REQUIRED. Các nội dung này được ghi là ngoài phạm vi MVP trong [decisions.md](decisions.md).
- Các điểm mâu thuẫn còn lại giữa nguồn (lease, khoá idempotent, trạng thái engine, đường dẫn API) đã được xử lý theo SRS; xem [system-design.md](system-design.md) mục 10.
- Các tham số chưa chốt giữ nguyên mã TBD của SRS: TBD-01, 02, 05, 08, 09, 10, 13, 14, 15, 17.
- Blocker kiến trúc trước đây: **resolved by source artifacts** (không còn file blocker riêng trong repository).

## Related Files

- [Kiến trúc hệ thống](system-design.md)
- [Quyết định](decisions.md)
- [Roadmap](../../.agent/planning/roadmap.md)
- [Epic registry](../../.agent/planning/epics.md)

## Forbidden Actions

- Không thêm thành phần, công nghệ hay tích hợp ngoài các nguồn trên khi chưa có quyết định mới (DEC hoặc change request).
- Không coi một quyết định "đã chốt" là bằng chứng rằng tính năng đã được triển khai hay đã đạt nghiệm thu.
- Không tự gán giá trị cho các mục TBD.
