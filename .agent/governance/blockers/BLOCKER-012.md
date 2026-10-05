---
id: blocker-012
title: Lineage báo cáo KPI (snapshot đầu vào) và báo cáo/gate (revision cuối)
type: governance
domain: governance
module: blockers
tags: [blocker, decision, m13]
priority: 2
---
# BLOCKER-012: Lineage báo cáo KPI (snapshot đầu vào) và báo cáo/gate (revision cuối)

## Record Metadata

- **Blocker ID**: `BLOCKER-012`
- **Title**: `Lineage báo cáo KPI (snapshot đầu vào) và báo cáo/gate (revision cuối)`
- **Owner**: `unassigned (vai trò chốt: Quality Assurance Lead)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `open`
- **Blocker Type**: `decision`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

FR-RPT-06 chuyển báo cáo sang run cuối, nhưng KPI-1 phải dùng ranking và 𝓔 của snapshot đầu vào đã khoá.

Bằng chứng: docs/label-x_system-requirement-specification/sections/06-functional.tex FR-RPT-06; docs/label-x_system-requirement-specification/sections/07-evaluation.tex KPI-1.

## Impact

- **Blocked Epics or Tasks**: `E-01, E-20, E-21`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `none`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Chốt hai nguồn trong báo cáo: KPI theo snapshot đầu vào, chất lượng/gate theo run cuối.
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
