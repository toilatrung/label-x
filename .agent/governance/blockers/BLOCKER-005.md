---
id: blocker-005
title: Detector artifact, mapping 10 lớp và training manifest chưa xác nhận
type: governance
domain: governance
module: blockers
tags: [blocker, dependency, m13]
priority: 2
---
# BLOCKER-005: Detector artifact, mapping 10 lớp và training manifest chưa xác nhận

## Record Metadata

- **Blocker ID**: `BLOCKER-005`
- **Title**: `Detector artifact, mapping 10 lớp và training manifest chưa xác nhận`
- **Owner**: `unassigned (vai trò chốt: Data/Model Owner)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `open`
- **Blocker Type**: `dependency`
- **Priority**: `1`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

FR-ENG-05 cần artifact/checksum/mapping 10 lớp; FR-EVL-05(b) cần danh sách ảnh huấn luyện; màn ModelsGuidelines chỉ có giá trị minh hoạ.

Bằng chứng: docs/label-x_system-requirement-specification/sections/06-functional.tex FR-ENG-05, FR-EVL-05; docs/label-x_system-requirement-specification/sections/02-overview.tex AS-02, AS-03.

## Impact

- **Blocked Epics or Tasks**: `E-06, E-10, E-18`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `none`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Data/Model Owner bàn giao artifact, checksum, mapping, training manifest; không sao chép giá trị demo.
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
