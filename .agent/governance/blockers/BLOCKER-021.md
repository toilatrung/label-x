---
id: blocker-021
title: Đặc tả Model Orchestrator chưa chốt (TBD-21)
type: governance
domain: governance
module: blockers
tags: [blocker, decision, m13]
priority: 2
---
# BLOCKER-021: Đặc tả Model Orchestrator chưa chốt (TBD-21)

## Record Metadata

- **Blocker ID**: `BLOCKER-021`
- **Title**: `Đặc tả Model Orchestrator chưa chốt (TBD-21)`
- **Owner**: `unassigned (vai trò chốt: Data/Model Owner)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `open`
- **Blocker Type**: `decision`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

B-05 cần Model Orchestrator tổng hợp kết quả đánh giá engine nhưng đầu vào/đầu ra/provenance chưa đặc tả.

Bằng chứng: docs/label-x_system-requirement-specification/sections/11-traceability.tex TBD-21; docs/00-project/sources/architecture_review.html B-05.

## Impact

- **Blocked Epics or Tasks**: `E-17, E-20`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `none`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Đội mô hình đặc tả trước khi đo Metric engine.
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
