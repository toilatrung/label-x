---
id: blocker-002
title: Chưa quyết định bật/tắt VLM trong pilot (TBD-08)
type: governance
domain: governance
module: blockers
tags: [blocker, decision, m13]
priority: 2
---
# BLOCKER-002: Chưa quyết định bật/tắt VLM trong pilot (TBD-08)

## Record Metadata

- **Blocker ID**: `BLOCKER-002`
- **Title**: `Chưa quyết định bật/tắt VLM trong pilot (TBD-08)`
- **Owner**: `unassigned (vai trò chốt: Product Owner)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `open`
- **Blocker Type**: `decision`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

SRS đề xuất không bật VLM trong pilot nhưng cần Product Owner duyệt; B-08 vẫn là kiến trúc đã chốt.

Bằng chứng: docs/label-x_system-requirement-specification/sections/06-functional.tex FR-ENG-10; docs/label-x_system-requirement-specification/sections/11-traceability.tex TBD-08.

## Impact

- **Blocked Epics or Tasks**: `E-12, E-19`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `none`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Product Owner duyệt hoặc bác đề xuất; nếu bật thì chốt model, trigger, timeout nội bộ.
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
