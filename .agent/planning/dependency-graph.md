---
id: dep-graph-v1
title: Dependency Graph
type: planning
domain: architecture
module: planning
tags: [dependencies, epics, milestones]
priority: 2
---
# Dependency Graph

## Purpose

Maintain the authoritative directed relationships that constrain roadmap items, milestones, epics, and tasks.

## Status Model

- **Valid Edge Statuses**: `active | satisfied | blocked | removed`

## Dependency Records

| Edge ID | Dependent ID | Prerequisite ID | Type | Owner | Status | Evidence | Governance Link |
|---|---|---|---|---|---|---|---|
| `EDGE-001` | `E-02` | `E-01` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-002` | `E-03` | `E-02` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-003` | `E-04` | `E-02` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-004` | `E-04` | `E-03` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-005` | `E-05` | `E-02` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-006` | `E-06` | `E-04` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-007` | `E-06` | `E-05` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-008` | `E-07` | `E-06` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-009` | `E-08` | `E-04` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-010` | `E-09` | `E-08` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-011` | `E-10` | `E-05` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-012` | `E-10` | `E-08` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-013` | `E-10` | `E-07` | `acceptance-gate` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-014` | `E-11` | `E-09` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-015` | `E-12` | `E-09` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-016` | `E-12` | `E-10` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-017` | `E-13` | `E-11` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-018` | `E-14` | `E-13` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-019` | `E-14` | `E-03` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-020` | `E-15` | `E-14` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-021` | `E-16` | `E-15` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-022` | `E-16` | `E-08` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-023` | `E-17` | `E-07` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-024` | `E-17` | `E-10` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-025` | `E-17` | `E-11` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-026` | `E-17` | `E-16` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-027` | `E-18` | `E-17` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-028` | `E-19` | `E-18` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-029` | `E-19` | `E-16` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-030` | `E-20` | `E-19` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-031` | `E-21` | `E-20` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-032` | `E-21` | `E-16` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-033` | `E-22` | `E-20` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-034` | `E-22` | `E-16` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-035` | `E-23` | `E-20` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-036` | `E-24` | `E-12` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-037` | `E-24` | `E-21` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-038` | `E-24` | `E-22` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-039` | `E-24` | `E-23` | `finish-to-finish` | `unassigned` | `active` | Thảo luận Claude–Codex 2026-10-05 | `none` |
| `EDGE-040` | `M-02` | `M-01` | `milestone-order` | `unassigned` | `active` | docs/00-project/sources/architecture_review.html mục 7; charter | `none` |
| `EDGE-041` | `M-03` | `M-02` | `milestone-order` | `unassigned` | `active` | docs/00-project/sources/architecture_review.html mục 7; charter | `none` |
| `EDGE-042` | `M-04` | `M-03` | `milestone-order` | `unassigned` | `active` | docs/00-project/sources/architecture_review.html mục 7; charter | `none` |
| `EDGE-043` | `M-05` | `M-04` | `milestone-order` | `unassigned` | `active` | docs/00-project/sources/architecture_review.html mục 7; charter | `none` |
| `EDGE-044` | `M-06` | `M-05` | `milestone-order` | `unassigned` | `active` | docs/00-project/sources/architecture_review.html mục 7; charter | `none` |

## Critical Path

Chưa tính được theo thời gian (không có ước lượng hay lịch sẵn sàng đầu vào). Chuỗi chi phối hoàn thành:

`E-01 → E-02 → E-03 → E-04 → E-08 → E-09 → E-11 → E-13 → E-14 → E-15 → E-16 → E-17 → E-18 → E-19 → E-20 → E-23 → E-24`

Nhánh có thể thành đường găng thực tế:

- **Reference (nhân lực):** `E-06 → E-07 → E-17 → E-18` — RK-03/`RISK-003`; chuẩn bị dữ liệu bắt đầu song song M-02/M-03.
- **Detector:** `BLOCKER-005 → E-10 → E-17`.
- **Quyết định trước thí nghiệm:** `BLOCKER-015/016/017/019 → E-18 → E-19`.

## Notes

- Cạnh là cổng hoàn tất outcome, không cấm chuẩn bị hay prototype song song.
- `EDGE` loại `acceptance-gate` (E-10 → E-07): code Detector làm được sau E-05/E-08; chỉ nghiệm thu ngưỡng cần reference hiệu chỉnh.
