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
- **Owner**: `project-owner (Trịnh Quang Trung, @toilatrung)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `resolved`
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
- **Decisions**: `.agent/governance/decisions/DEC-002.md`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Product Owner ký từng epic (ghi vào `.agent/planning/epics.md`) và gán task cho từng developer trước khi giao task.
- **Responsible Owner**: `project-owner (Trịnh Quang Trung, @toilatrung)`
- **Dependency or Approval**: `Product Owner`
- **Workaround**: `none`
- **Verification Method**: Quyết định/bằng chứng được ghi thành decision record hoặc cập nhật SRS có version, liên kết vào đây.

## Resolution Record

- **Resolved Date**: `2026-10-06`
- **Evidence**: `.agent/governance/decisions/DEC-002.md` — phiếu chốt của Product Owner ngày 2026-10-06.
- **Note**: Phương án khác: Product Owner ký từng epic và gán task cho từng developer trước khi giao task và triển khai. Điều kiện chặn chung (chờ các vai trò ký bảng phê duyệt SRS) được thay bằng cổng theo epic: một epic chỉ chuyển `EPIC_READY` khi Product Owner ghi chữ ký (người, ngày) vào epic đó trong `.agent/planning/epics.md` và mọi task có developer được gán. Bảng phê duyệt SRS theo vai trò vẫn trống nhưng không còn là điều kiện bắt đầu.

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
