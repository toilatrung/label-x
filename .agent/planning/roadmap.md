---
id: roadmap-v1
title: Project Roadmap
type: planning
domain: governance
module: planning
tags: [roadmap, milestones, planning]
priority: 1
---
# Project Roadmap

## Purpose

Maintain the approved sequence of outcome-level roadmap items and their target windows without defining task-level implementation.

## Status Model

- **Valid Statuses**: `ROADMAP_DRAFT | ROADMAP_APPROVED | ROADMAP_ACTIVE | ROADMAP_BLOCKED | ROADMAP_DONE | ROADMAP_CANCELLED`

## Roadmap Records

| Roadmap ID | Outcome | Owner | Target Window | Status | Milestone IDs | Change Request |
|---|---|---|---|---|---|---|
| `R-001` | Hoàn thành và nghiệm thu LabelX M13 — Reviewer Prioritization Assistant: CVAT → snapshot → phân tích nghi vấn → xếp hạng frame → review/phân xử/rework → đo KPI-1, KPI-2 và báo cáo hiệu quả | `unassigned (vai trò: Product Owner M13)` | `not-set` | `ROADMAP_DRAFT` | `M-01, M-02, M-03, M-04, M-05, M-06` | `none` |

## Basis

- Nguồn: SRS M13 v1.0 (`docs/label-x_system-requirement-specification/sections/`), `docs/00-project/sources/architecture_review.html` (B-01…B-21, R-01…R-07, mục 7 — thứ tự triển khai), `docs/00-project/charter.md`, `.agent/governance/decisions/DEC-001.md`.
- Thứ tự milestone theo bản rà soát R và charter: nền tảng → kiểm xác định → review/rework → reference + discovery → kiểm chứng/gate/báo cáo → vận hành/nghiệm thu. Đây là thứ tự phụ thuộc, không phải lịch.
- Phạm vi hoàn thành: mọi yêu cầu Must và Should của SRS; FR-RNK-09 (Could) ở backlog; FR-ENG-10 theo quyết định TBD-08 (`BLOCKER-002`).
- Lập qua ba vòng thảo luận độc lập Claude ↔ Codex ngày 2026-10-05; thống nhất 24 epic, 21 blocker, 10 risk.
- Trạng thái `ROADMAP_DRAFT`: SRS chờ ký theo vai trò và owner chưa được gán (`BLOCKER-001`). Không có target window vì SRS không cung cấp mốc thời gian.
