---
id: blocker-015
title: Tham số khoa học và nguồn lực cho các cổng đo
type: governance
domain: governance
module: blockers
tags: [blocker, decision, m13]
priority: 2
---
# BLOCKER-015: Tham số khoa học và nguồn lực cho các cổng đo

## Record Metadata

- **Blocker ID**: `BLOCKER-015`
- **Title**: `Tham số khoa học và nguồn lực cho các cổng đo`
- **Owner**: `unassigned (vai trò chốt: Quality Assurance Lead)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `open`
- **Blocker Type**: `decision`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

TBD-03…07, 10…12, 16, K1…K4 và nguồn lực AS-04 (QA Lead + 2 người xác minh), AS-05 (≥ 4 reviewer) chưa chốt.

Bằng chứng: docs/label-x_system-requirement-specification/sections/11-traceability.tex; docs/label-x_system-requirement-specification/sections/02-overview.tex AS-04, AS-05; docs/label-x_system-requirement-specification/sections/07-evaluation.tex §7.3.

## Impact

- **Blocked Epics or Tasks**: `E-05, E-07, E-17, E-18, E-19, E-20`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `none`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Chốt từng TBD theo người chốt và hạn chốt trong SRS bảng TBD.
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
