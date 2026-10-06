---
id: blocker-017
title: Quan hệ D1/D2 với tập held-out KPI-1 chưa xác định
type: governance
domain: governance
module: blockers
tags: [blocker, decision, m13]
priority: 2
---
# BLOCKER-017: Quan hệ D1/D2 với tập held-out KPI-1 chưa xác định

## Record Metadata

- **Blocker ID**: `BLOCKER-017`
- **Title**: `Quan hệ D1/D2 với tập held-out KPI-1 chưa xác định`
- **Owner**: `unassigned (vai trò chốt: Product Owner)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `resolved`
- **Blocker Type**: `decision`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

EX-02 chỉ nói D1/D2 không giao tập hiệu chỉnh; chưa rõ D1/D2 là held-out hay tập thứ ba.

Bằng chứng: docs/label-x_system-requirement-specification/sections/07-evaluation.tex EX-02; TBD-03, TBD-12.

## Impact

- **Blocked Epics or Tasks**: `E-18, E-19, E-20`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `.agent/governance/decisions/DEC-002.md`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Chốt cấu trúc tập dữ liệu đánh giá.
- **Responsible Owner**: `unassigned (vai trò: Product Owner)`
- **Dependency or Approval**: `Product Owner`
- **Workaround**: `none`
- **Verification Method**: Quyết định/bằng chứng được ghi thành decision record hoặc cập nhật SRS có version, liên kết vào đây.

## Resolution Record

- **Resolved Date**: `2026-10-06`
- **Evidence**: `.agent/governance/decisions/DEC-002.md` — phiếu chốt của Product Owner ngày 2026-10-06.
- **Note**: Phương án A: D1/D2 là hai nửa của tập held-out, chia ngẫu nhiên theo video. KPI-1 đo trên toàn tập; thí nghiệm effort chạy trên D1/D2. Chỉ lập reference cho hai tập (hiệu chỉnh + held-out).

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
