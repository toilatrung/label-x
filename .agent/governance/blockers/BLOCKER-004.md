---
id: blocker-004
title: CVAT thật chưa xác minh (TBD-01, AS-01)
type: governance
domain: governance
module: blockers
tags: [blocker, external, m13]
priority: 2
---
# BLOCKER-004: CVAT thật chưa xác minh (TBD-01, AS-01)

## Record Metadata

- **Blocker ID**: `BLOCKER-004`
- **Title**: `CVAT thật chưa xác minh (TBD-01, AS-01)`
- **Owner**: `unassigned (vai trò chốt: Tech Lead Backend)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `open`
- **Blocker Type**: `external`
- **Priority**: `1`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

Chưa có URL, version, quyền token, endpoint thật, frame mapping và cách phát hiện drift trên CVAT đang triển khai.

Bằng chứng: docs/label-x_system-requirement-specification/sections/11-traceability.tex TBD-01; docs/label-x_system-requirement-specification/sections/02-overview.tex AS-01; RK-06.

## Impact

- **Blocked Epics or Tasks**: `E-04, E-06`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `none`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Chủ CVAT cung cấp instance + service account chỉ đọc; spike adapter chứng minh đọc/hash/drift; pin version.
- **Responsible Owner**: `unassigned (vai trò: Tech Lead Backend)`
- **Dependency or Approval**: `Tech Lead Backend`
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
