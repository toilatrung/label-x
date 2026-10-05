---
id: blocker-001
title: SRS chờ ký theo vai trò; owner planning chưa gán
type: governance
domain: governance
module: blockers
tags: [blocker, approval, m13]
priority: 2
---
# BLOCKER-001: SRS chờ ký theo vai trò; owner planning chưa gán

## Record Metadata

- **Blocker ID**: `BLOCKER-001`
- **Title**: `SRS chờ ký theo vai trò; owner planning chưa gán`
- **Owner**: `unassigned (vai trò chốt: Product Owner)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `open`
- **Blocker Type**: `approval`
- **Priority**: `1`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

SRS v1.0 đã được người dùng chấp nhận nội dung (05/10/2026) nhưng bảng phê duyệt theo vai trò còn trống; owner của milestone/epic chưa được gán người.

Bằng chứng: docs/label-x_system-requirement-specification/sections/00-frontmatter.tex — Bảng phê duyệt; AGENT.md — Epic Expansion Rule.

## Impact

- **Blocked Epics or Tasks**: `E-01, E-24; mọi chuyển EPIC_READY và ROADMAP_APPROVED`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `none`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Các vai trò trong bảng phê duyệt ký SRS; gán người cho owner từng epic; phê duyệt roadmap qua roadmap-lock-prompt.
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
