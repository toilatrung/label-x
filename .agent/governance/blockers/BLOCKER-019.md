---
id: blocker-019
title: Người biết GT tham gia phân xử thí nghiệm
type: governance
domain: governance
module: blockers
tags: [blocker, decision, m13]
priority: 2
---
# BLOCKER-019: Người biết GT tham gia phân xử thí nghiệm

## Record Metadata

- **Blocker ID**: `BLOCKER-019`
- **Title**: `Người biết GT tham gia phân xử thí nghiệm`
- **Owner**: `unassigned (vai trò chốt: Product Owner)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `resolved`
- **Blocker Type**: `decision`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

QA Lead phân xử bất đồng GT (BR-11) đã biết đáp án; EX-09 dùng cùng QA Lead phân xử hai nhánh; EX-10 loại người lập reference khỏi thí nghiệm.

Bằng chứng: docs/label-x_system-requirement-specification/sections/03-data-errors.tex BR-11; docs/label-x_system-requirement-specification/sections/07-evaluation.tex EX-09, EX-10.

## Impact

- **Blocked Epics or Tasks**: `E-18, E-19`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `.agent/governance/decisions/DEC-002.md`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Product Owner chốt phân tách vai trò người phân xử GT và người phân xử thí nghiệm.
- **Responsible Owner**: `unassigned (vai trò: Product Owner)`
- **Dependency or Approval**: `Product Owner`
- **Workaround**: `none`
- **Verification Method**: Quyết định/bằng chứng được ghi thành decision record hoặc cập nhật SRS có version, liên kết vào đây.

## Resolution Record

- **Resolved Date**: `2026-10-06`
- **Evidence**: `.agent/governance/decisions/DEC-002.md` — phiếu chốt của Product Owner ngày 2026-10-06.
- **Note**: Phương án A: QA Lead phân xử bất đồng GT; một người khác (QA Lead thứ hai hoặc senior reviewer được cấp quyền) phân xử cả hai nhánh thí nghiệm. Người bổ sung được gán cùng nguồn lực AS-05 (BLOCKER-015).

## Completion Criteria

- [x] The blocking condition no longer prevents affected work.
- [x] Resolution evidence is linked.
- [x] Affected epic and task statuses are updated.
- [x] Workaround removal is tracked when applicable.

## Forbidden Actions

- Do not mark status `resolved` based only on a proposed action.
- Do not continue blocked work through an unauthorized workaround.
- Do not omit affected epic or task links.
- Do not fabricate resolution evidence.

## Output Requirements

- Save as `.agent/governance/blockers/BLOCKER-<number>.md`.
- Preserve every heading in this template.
- Use repository-relative links and exact enum values.
