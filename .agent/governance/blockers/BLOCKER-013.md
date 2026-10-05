---
id: blocker-013
title: Thiết kế màn hình thiếu delta cho luồng M13
type: governance
domain: governance
module: blockers
tags: [blocker, dependency, m13]
priority: 2
---
# BLOCKER-013: Thiết kế màn hình thiếu delta cho luồng M13

## Record Metadata

- **Blocker ID**: `BLOCKER-013`
- **Title**: `Thiết kế màn hình thiếu delta cho luồng M13`
- **Owner**: `unassigned (vai trò chốt: Product Owner)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `open`
- **Blocker Type**: `dependency`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

ReviewQueues là bảng issue, chưa có rank frame/đóng góp điểm; PerformanceEvaluation chưa có KPI/crossover/CI; chưa có màn auth/audit, hai GT, leakage, preregistration.

Bằng chứng: docs/design/screens/; docs/label-x_system-requirement-specification/sections/09-interfaces.tex bảng màn hình.

## Impact

- **Blocked Epics or Tasks**: `E-02, E-06, E-13, E-14, E-19, E-21, E-22`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `none`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Bổ sung thiết kế (skill labelx-design) cho các delta trước khi nghiệm thu UI tương ứng.
- **Responsible Owner**: `unassigned (vai trò: Product Owner)`
- **Dependency or Approval**: `Product Owner`
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
