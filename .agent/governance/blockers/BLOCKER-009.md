---
id: blocker-009
title: Lý do cho quyết định "Chưa chắc chắn" không nhất quán
type: governance
domain: governance
module: blockers
tags: [blocker, decision, m13]
priority: 2
---
# BLOCKER-009: Lý do cho quyết định "Chưa chắc chắn" không nhất quán

## Record Metadata

- **Blocker ID**: `BLOCKER-009`
- **Title**: `Lý do cho quyết định "Chưa chắc chắn" không nhất quán`
- **Owner**: `unassigned (vai trò chốt: Quality Assurance Lead)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `resolved`
- **Blocker Type**: `decision`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

FR-REV-08 chỉ bắt buộc lý do cho bác bỏ/chuyển cấp; bảng transition bắt buộc lý do cho cả uncertain.

Bằng chứng: docs/label-x_system-requirement-specification/sections/06-functional.tex FR-REV-08; docs/label-x_system-requirement-specification/sections/05-dynamics.tex bảng transition.

## Impact

- **Blocked Epics or Tasks**: `E-01, E-14`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `none`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Chốt một quy tắc validate và sửa SRS cho thống nhất.
- **Responsible Owner**: `unassigned (vai trò: Quality Assurance Lead)`
- **Dependency or Approval**: `Quality Assurance Lead`
- **Workaround**: `none`
- **Verification Method**: Quyết định/bằng chứng được ghi thành decision record hoặc cập nhật SRS có version, liên kết vào đây.

## Resolution Record

- **Resolved Date**: `2026-10-05`
- **Evidence**: docs/label-x_system-requirement-specification/sections/06-functional.tex FR-REV-08: "bác bỏ, chưa chắc chắn và chuyển cấp bắt buộc lý do" — khớp bảng transition chương 5.
- **Note**: Sửa trong SRS v1.0 (LaTeX, `docs/01-business/labelX.html`); SRS vẫn chờ ký theo vai trò — phê duyệt cuối theo dõi ở `BLOCKER-001`.

## Completion Criteria

- [x] The blocking condition no longer prevents affected work.
- [x] Resolution evidence is linked.
- [ ] Affected epic and task statuses are updated.
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
