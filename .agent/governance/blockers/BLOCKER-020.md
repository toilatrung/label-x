---
id: blocker-020
title: Điều khoản sử dụng BDD100K chưa xác nhận (TBD-18)
type: governance
domain: governance
module: blockers
tags: [blocker, approval, m13]
priority: 2
---
# BLOCKER-020: Điều khoản sử dụng BDD100K chưa xác nhận (TBD-18)

## Record Metadata

- **Blocker ID**: `BLOCKER-020`
- **Title**: `Điều khoản sử dụng BDD100K chưa xác nhận (TBD-18)`
- **Owner**: `unassigned (vai trò chốt: Data/Model Owner)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `open`
- **Blocker Type**: `approval`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

Chưa xác nhận giấy phép BDD100K cho pilot và lưu trữ nội bộ.

Bằng chứng: docs/label-x_system-requirement-specification/sections/11-traceability.tex TBD-18.

## Impact

- **Blocked Epics or Tasks**: `E-04, E-07, E-18`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `none`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Data Owner xác nhận điều khoản trước khi nạp dữ liệu.
- **Responsible Owner**: `unassigned (vai trò: Data/Model Owner)`
- **Dependency or Approval**: `Data/Model Owner`
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
