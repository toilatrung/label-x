---
id: blocker-007
title: Lineage issue qua revision và neo issue cấu trúc/thủ công chưa có contract
type: governance
domain: governance
module: blockers
tags: [blocker, decision, m13]
priority: 2
---
# BLOCKER-007: Lineage issue qua revision và neo issue cấu trúc/thủ công chưa có contract

## Record Metadata

- **Blocker ID**: `BLOCKER-007`
- **Title**: `Lineage issue qua revision và neo issue cấu trúc/thủ công chưa có contract`
- **Owner**: `unassigned (vai trò chốt: Tech Lead Backend)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `resolved`
- **Blocker Type**: `decision`
- **Priority**: `1`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

dedup_key chỉ định nghĩa cho đối tượng tham chiếu; bảng neo chỉ có E1/E2/E3; FR-RWK-06/08 cần nối verification cũ với issue run cuối nhưng chưa có quy tắc tương ứng.

Bằng chứng: docs/label-x_system-requirement-specification/sections/06-functional.tex FR-AGG-03, FR-RNK-12, FR-RWK-05…08.

## Impact

- **Blocked Epics or Tasks**: `E-01, E-08, E-11, E-16`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `.agent/governance/decisions/DEC-002.md`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Duyệt ADR trong E-01: định danh đối tượng qua revision, neo issue cấu trúc/thủ công, quy tắc liên kết verification.
- **Responsible Owner**: `unassigned (vai trò: Tech Lead Backend)`
- **Dependency or Approval**: `Tech Lead Backend`
- **Workaround**: `none`
- **Verification Method**: Quyết định/bằng chứng được ghi thành decision record hoặc cập nhật SRS có version, liên kết vào đây.

## Resolution Record

- **Resolved Date**: `2026-10-06`
- **Evidence**: `.agent/governance/decisions/DEC-002.md` — phiếu chốt của Product Owner ngày 2026-10-06.
- **Note**: Phương án A: định danh đối tượng qua revision bằng cvat_shape_id + namespace nguồn; fallback matching chỉ để gợi ý. Issue gốc giữ verification; run cuối gặp lại cùng neo thì tạo issue mới liên kết issue gốc, không tự kế thừa quyết định. Issue cấu trúc neo (annotation, rule ID); issue thủ công neo (frame, vùng vẽ). ADR ghi thành decision `accepted` trong E-01.

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
