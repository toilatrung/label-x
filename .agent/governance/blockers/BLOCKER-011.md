---
id: blocker-011
title: Run gốc/run cuối, Completed/coverage và waiver từng điều kiện (TBD-19)
type: governance
domain: governance
module: blockers
tags: [blocker, decision, m13]
priority: 2
---
# BLOCKER-011: Run gốc/run cuối, Completed/coverage và waiver từng điều kiện (TBD-19)

## Record Metadata

- **Blocker ID**: `BLOCKER-011`
- **Title**: `Run gốc/run cuối, Completed/coverage và waiver từng điều kiện (TBD-19)`
- **Owner**: `unassigned (vai trò chốt: Product Owner)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `resolved`
- **Blocker Type**: `decision`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

FR-GTE-01 tính gate trên run cuối, UC-14 cho phép run gốc khi chưa rework; danh sách điều kiện được waiver chưa chốt.

Bằng chứng: docs/label-x_system-requirement-specification/sections/06-functional.tex FR-RWK-08, FR-GTE-01…03; docs/label-x_system-requirement-specification/sections/04-usecases.tex UC-14; TBD-19.

## Impact

- **Blocked Epics or Tasks**: `E-16, E-22`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `.agent/governance/decisions/DEC-002.md`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Chốt quy tắc run nào là nguồn gate khi không có rework và policy waiver từng điều kiện.
- **Responsible Owner**: `unassigned (vai trò: Product Owner)`
- **Dependency or Approval**: `Product Owner`
- **Workaround**: `none`
- **Verification Method**: Quyết định/bằng chứng được ghi thành decision record hoặc cập nhật SRS có version, liên kết vào đây.

## Resolution Record

- **Resolved Date**: `2026-10-06`
- **Evidence**: `.agent/governance/decisions/DEC-002.md` — phiếu chốt của Product Owner ngày 2026-10-06.
- **Note**: Phương án A: không có rework thì run gốc Completed được đánh dấu run cuối; waiver chỉ áp dụng cho coverage và đồng thuận reviewer; lỗi nghiêm trọng chưa đóng và rework chưa verify không bao giờ được waiver. Việc tiếp theo: làm rõ FR-GTE-01 trong contract E-01 và SRS.

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
