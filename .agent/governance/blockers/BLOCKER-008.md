---
id: blocker-008
title: Lease hết hạn khi đã lưu một phần, resume, multi-tab (TBD-09)
type: governance
domain: governance
module: blockers
tags: [blocker, decision, m13]
priority: 2
---
# BLOCKER-008: Lease hết hạn khi đã lưu một phần, resume, multi-tab (TBD-09)

## Record Metadata

- **Blocker ID**: `BLOCKER-008`
- **Title**: `Lease hết hạn khi đã lưu một phần, resume, multi-tab (TBD-09)`
- **Owner**: `unassigned (vai trò chốt: Product Owner)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `resolved`
- **Blocker Type**: `decision`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

FR-REV-04 trả frame về hàng đợi khi hết lease, nhưng transition lease_expired yêu cầu chưa có quyết định đã lưu; chưa quy định một hay nhiều lease mỗi reviewer.

Bằng chứng: docs/label-x_system-requirement-specification/sections/06-functional.tex FR-REV-04; docs/label-x_system-requirement-specification/sections/05-dynamics.tex bảng transition; TBD-09; RK-05.

## Impact

- **Blocked Epics or Tasks**: `E-13, E-14`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `.agent/governance/decisions/DEC-002.md`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Chốt thời hạn lease, quy tắc gia hạn, xử lý quyết định một phần và giới hạn lease mỗi reviewer.
- **Responsible Owner**: `unassigned (vai trò: Product Owner)`
- **Dependency or Approval**: `Product Owner`
- **Workaround**: `none`
- **Verification Method**: Quyết định/bằng chứng được ghi thành decision record hoặc cập nhật SRS có version, liên kết vào đây.

## Resolution Record

- **Resolved Date**: `2026-10-06`
- **Evidence**: `.agent/governance/decisions/DEC-002.md` — phiếu chốt của Product Owner ngày 2026-10-06.
- **Note**: Phương án A: mỗi reviewer giữ một lease (chặn nhiều tab); hết hạn thì giữ quyết định đã lưu, frame về hàng đợi ở trạng thái "đang dở", ưu tiên trả về reviewer cũ. Thời hạn và quy tắc gia hạn đo trong pilot rồi chốt. Việc tiếp theo: bổ sung trạng thái "đang dở" vào bảng transition (contract E-01, cập nhật SRS).

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
