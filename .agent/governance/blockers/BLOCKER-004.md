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
- **Status**: `resolved`
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
- **Decisions**: `.agent/governance/decisions/DEC-002.md`
- **Risks**: `none`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`

## Resolution Plan

- **Required Action**: Thêm CVAT dev (cùng phiên bản instance thật) vào `infrastructure/docker-compose.dev.yml`; chủ CVAT cung cấp phiên bản, URL và service account chỉ đọc cho lần kiểm trước nghiệm thu E-04.
- **Responsible Owner**: `unassigned (vai trò: Tech Lead Backend)`
- **Dependency or Approval**: `Tech Lead Backend`
- **Workaround**: `CVAT dev trong docker compose; gỡ khi adapter đã kiểm trên instance thật và pin phiên bản.`
- **Verification Method**: Quyết định/bằng chứng được ghi thành decision record hoặc cập nhật SRS có version, liên kết vào đây.

## Resolution Record

- **Resolved Date**: `2026-10-06`
- **Evidence**: `.agent/governance/decisions/DEC-002.md` — phiếu chốt của Product Owner ngày 2026-10-06.
- **Note**: Chốt 2026-10-06 (CR-101 được duyệt): pilot chạy trên CVAT do đội tự dựng, cùng phiên bản với CVAT dev trong docker compose; ảnh, GT và annotation BDD100K do đội nạp, nên instance này là "CVAT thật" của pilot và không cần instance của bên khác. Lê Duy Nam pin phiên bản CVAT khi dựng (TBD-01). Ghi chú cũ — phương án B: dựng CVAT dev riêng cùng phiên bản trong docker compose để xây adapter song song. Còn mở: (1) phiên bản CVAT của instance thật (TBD-01) để pin đúng phiên bản dev; (2) kiểm lại adapter trên instance thật (đọc job/annotation/ảnh, hash ổn định, phát hiện drift — AC-03) trước khi nghiệm thu E-04.

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
