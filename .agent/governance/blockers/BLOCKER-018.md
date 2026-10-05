---
id: blocker-018
title: Quy trình ngoài LabelX tạo task GT và bản sao annotation hai nhánh
type: governance
domain: governance
module: blockers
tags: [blocker, dependency, m13]
priority: 2
---
# BLOCKER-018: Quy trình ngoài LabelX tạo task GT và bản sao annotation hai nhánh

## Record Metadata

- **Blocker ID**: `BLOCKER-018`
- **Title**: `Quy trình ngoài LabelX tạo task GT và bản sao annotation hai nhánh`
- **Owner**: `unassigned (vai trò chốt: Quality Assurance Lead)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `open`
- **Blocker Type**: `dependency`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

UC-08 cần task CVAT riêng cho người xác minh; EX-03 cần bản sao annotation riêng mỗi nhánh; adapter chỉ đọc (B-18) nên việc chuẩn bị nằm ngoài LabelX và chưa có quy trình/người thực hiện.

Bằng chứng: docs/label-x_system-requirement-specification/sections/04-usecases.tex UC-08; docs/label-x_system-requirement-specification/sections/07-evaluation.tex EX-03; FR-SNP-01.

## Impact

- **Blocked Epics or Tasks**: `E-06, E-07, E-18, E-19`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `none`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: QA Lead, QC Admin và chủ CVAT duyệt quy trình provisioning và cách adapter đọc các task này làm nguồn GT/nhánh.
- **Responsible Owner**: `unassigned (vai trò: Quality Assurance Lead)`
- **Dependency or Approval**: `Quality Assurance Lead`
- **Workaround**: `none`
- **Verification Method**: Quyết định/bằng chứng được ghi thành decision record hoặc cập nhật SRS có version, liên kết vào đây.

## Completion Criteria

- [ ] The blocking condition no longer prevents affected work.
- [ ] Resolution evidence is linked.
- [ ] Affected epic and task statuses are updated.
- [ ] Workaround removal is tracked when applicable.

## Forbidden Actions

- Do not mark status `resolved` based only on a proposed action.
- Do not continue blocked work through an unauthorized workaround.
- Do not omit affected epic or task links.
- Do not fabricate resolution evidence.

## Output Requirements

- Save as `.agent/governance/blockers/BLOCKER-<number>.md`.
- Preserve every heading in this template.
- Use repository-relative links and exact enum values.
