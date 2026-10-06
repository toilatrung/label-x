---
id: blocker-013
title: Thiết kế màn hình thiếu delta cho luồng M13
type: governance
domain: governance
module: blockers
tags: [blocker, dependency, m13]
priority: 2
---
# BLOCKER-013: Thiết kế màn hình thiếu delta cho luồng M13

## Record Metadata

- **Blocker ID**: `BLOCKER-013`
- **Title**: `Thiết kế màn hình thiếu delta cho luồng M13`
- **Owner**: `unassigned (vai trò chốt: Product Owner)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `resolved`
- **Blocker Type**: `dependency`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

ReviewQueues là bảng issue, chưa có rank frame/đóng góp điểm; PerformanceEvaluation chưa có KPI/crossover/CI; chưa có màn auth/audit, hai GT, leakage, preregistration.

Bằng chứng: docs/design/screens/; docs/label-x_system-requirement-specification/sections/09-interfaces.tex bảng màn hình.

## Impact

- **Blocked Epics or Tasks**: `E-02, E-06, E-13, E-14, E-19, E-21, E-22`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `.agent/governance/decisions/DEC-002.md`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Bổ sung thiết kế (skill labelx-design) cho các delta trước khi nghiệm thu UI tương ứng.
- **Responsible Owner**: `unassigned (vai trò: Product Owner)`
- **Dependency or Approval**: `Product Owner`
- **Workaround**: `none`
- **Verification Method**: Quyết định/bằng chứng được ghi thành decision record hoặc cập nhật SRS có version, liên kết vào đây.

## Resolution Record

- **Resolved Date**: `2026-10-06`
- **Evidence**: `.agent/governance/decisions/DEC-002.md` — phiếu chốt của Product Owner ngày 2026-10-06.
- **Note**: Phương án khác: thiết kế bổ sung just-in-time ngay trước epic dùng tới — đăng nhập/audit trước E-02; queue frame + đóng góp điểm trước E-13; Workspace delta trước E-14; reference hai GT trước E-06; thí nghiệm và KPI trước E-19/E-20. Kế hoạch bao gồm triển khai frontend trong từng epic có màn hình; thiết kế trong `docs/design/` chỉ là mẫu tham khảo khi code frontend, không phải đặc tả pixel. Cập nhật vào `.agent/planning/epics.md`.

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
