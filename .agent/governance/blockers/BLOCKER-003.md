---
id: blocker-003
title: Quyền chạy phân tích của QC Admin không nhất quán
type: governance
domain: governance
module: blockers
tags: [blocker, decision, m13]
priority: 2
---
# BLOCKER-003: Quyền chạy phân tích của QC Admin không nhất quán

## Record Metadata

- **Blocker ID**: `BLOCKER-003`
- **Title**: `Quyền chạy phân tích của QC Admin không nhất quán`
- **Owner**: `unassigned (vai trò chốt: Quality Control Admin)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `resolved`
- **Blocker Type**: `decision`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

Bảng lớp người dùng ghi QC Admin "Configuration; chạy phân tích", trong khi danh sách UC và ma trận RBAC ghi QA Lead chạy/xem, QC Admin cấu hình.

Bằng chứng: docs/label-x_system-requirement-specification/sections/02-overview.tex bảng lớp người dùng; docs/label-x_system-requirement-specification/sections/06-functional.tex bảng RBAC; docs/label-x_system-requirement-specification/sections/04-usecases.tex UC-01, UC-02.

## Impact

- **Blocked Epics or Tasks**: `E-01, E-02, E-04, E-08`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `none`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Chốt một ma trận actor/action/scope duy nhất và cập nhật SRS.
- **Responsible Owner**: `unassigned (vai trò: Quality Control Admin)`
- **Dependency or Approval**: `Quality Control Admin`
- **Workaround**: `none`
- **Verification Method**: Quyết định/bằng chứng được ghi thành decision record hoặc cập nhật SRS có version, liên kết vào đây.

## Resolution Record

- **Resolved Date**: `2026-10-05`
- **Evidence**: docs/label-x_system-requirement-specification/sections/02-overview.tex bảng lớp người dùng: QC Admin "Configuration (engine, ngưỡng, quyền). Không chạy phân tích (theo H: QA Lead chạy/xem)" — khớp bảng RBAC chương 6.
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
