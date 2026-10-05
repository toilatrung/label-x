---
id: project-srs
title: Software Requirements Specification Intake
type: reference
domain: business
module: repository
tags: [srs, requirements, intake]
priority: 1
---

# Software Requirements Specification Intake

## Purpose

Track ingestion and validation of the authoritative Software Requirements Specification for project onboarding.

## Input Status

- **Status**: `provided`
- **Authority**: `accepted-by-project-owner-pending-role-signoff`
- **Source Artifact**: `docs/01-business/labelX.html`
- **Ingested Date**: `2026-10-05`
- **Validated By**: `project-owner`

## Required Content

- Project objectives and scope boundaries
- Stakeholders and user classes
- Functional requirements with stable identifiers
- Non-functional requirements with measurable criteria
- Assumptions, constraints, exclusions, and acceptance criteria

## Validation Result

SRS M13 v1.0 (05/10/2026) của LabelX — chức năng **M13 Reviewer Prioritization Assistant** (tên đề tài đăng ký: Annotation QC Studio) — đã được cung cấp. Ngày 2026-10-05 người dùng (project owner) chấp nhận nội dung trong phiên làm việc ("Ổn rồi") và yêu cầu dùng làm SRS. Bảng ký phê duyệt theo vai trò trong SRS (Product Owner, QA Lead, QC Admin, Tech Lead, Data/Model Owner) **chưa được ký**; các quyết định kiến trúc/MVP đã chốt riêng trong `docs/00-project/sources/architecture_review.html`.

| Nội dung bắt buộc | Vị trí trong SRS | Kết quả |
|---|---|---|
| Mục tiêu và ranh giới phạm vi | Chương 1.2, 2.2–2.3 | Có: phạm vi lõi/hỗ trợ/ngoài phạm vi, KPI-1, KPI-2, guardrail G-1…G-5 |
| Stakeholder và lớp người dùng | Chương 2.6, ma trận quyền chương 6 | Có |
| Yêu cầu chức năng có mã ổn định | Chương 6 (`FR-<MODULE>-xx`), use case chương 4 (`UC-01`…`UC-14`) | Có |
| Yêu cầu phi chức năng đo được | Chương 8 (`NFR-01`…`NFR-16`) | Có; ngưỡng số là đề xuất, chốt sau pilot (B-14) |
| Giả định, ràng buộc, loại trừ, nghiệm thu | Chương 2.8–2.9, 7.4 (`AC-01`…`AC-11`), 11.3 (TBD) | Có; 21 tham số TBD có người chốt và hạn chốt |

Bằng chứng kiểm tra:

- Nguồn đầu vào đã chốt: `docs/00-project/sources/architecture_review.html` (B-01…B-21, cấu hình MVP, R-01…R-07), `docs/design/` (25 màn hình), `docs/00-project/sources/QC_Engine_Review_Report.html`, `docs/00-project/sources/Quality_Control_Review_UX_Architecture.html`, `docs/00-project/sources/mermaid-diagram.png`, và stack ở `.agent/governance/decisions/DEC-001.md`.
- Từng chương được Codex CLI review độc lập; kết quả lưu ở `docs/label-x_system-requirement-specification/.review/`.
- Bản LaTeX là gốc (biên dịch XeLaTeX trên TeXPage); bản HTML sinh bằng `python3 scripts/srs_tex2html.py`.

Giới hạn: SRS chưa có kết quả đo; các ngưỡng KPI, cỡ mẫu, phiên bản CVAT và phần cứng còn TBD (xem [requirements.md](requirements.md), mục Tham số còn mở).

## Related Files

- SRS (HTML): [labelX.html](labelX.html)
- SRS (LaTeX): `docs/label-x_system-requirement-specification/main.tex`
- Requirements: [requirements.md](requirements.md)
- Use cases: [use-cases.md](use-cases.md)
- Domain model: [domain-model.md](domain-model.md)
- Decision: `.agent/governance/decisions/DEC-001.md`
- Roadmap: `.agent/planning/roadmap.md`
- Epic registry: `.agent/planning/epics.md`

## Forbidden Actions

- Do not change baselined requirements without an approved change request in `.agent/governance/change-requests/`.
- Do not edit `labelX.html` by hand; change the LaTeX source and regenerate.
- Do not record role sign-off as complete until the approval table in the SRS is signed.
- Do not treat TBD parameters or illustrative numbers as accepted thresholds.
- Do not create implementation tasks from this intake record without an approved epic.
