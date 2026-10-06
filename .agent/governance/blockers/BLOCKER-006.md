---
id: blocker-006
title: Mẫu G-4 sau sửa, mẫu số và cách kết luận gate chưa chốt
type: governance
domain: governance
module: blockers
tags: [blocker, decision, m13]
priority: 2
---
# BLOCKER-006: Mẫu G-4 sau sửa, mẫu số và cách kết luận gate chưa chốt

## Record Metadata

- **Blocker ID**: `BLOCKER-006`
- **Title**: `Mẫu G-4 sau sửa, mẫu số và cách kết luận gate chưa chốt`
- **Owner**: `unassigned (vai trò chốt: Quality Assurance Lead)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `resolved`
- **Blocker Type**: `decision`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

G-4 là tỉ lệ frame còn lỗi từ lát ngẫu nhiên; chưa chốt revision lấy mẫu sau sửa, đủ mẫu và quy tắc kết luận residual ≤ 5%.

Bằng chứng: docs/label-x_system-requirement-specification/sections/02-overview.tex G-4; FR-RNK-07, FR-GTE-01/02; TBD-10, TBD-K4.

## Impact

- **Blocked Epics or Tasks**: `E-11, E-20, E-22`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `.agent/governance/decisions/DEC-002.md`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: QA Lead và Product Owner chốt policy lấy mẫu G-4, tách khỏi mẫu U của thí nghiệm.
- **Responsible Owner**: `unassigned (vai trò: Quality Assurance Lead)`
- **Dependency or Approval**: `Quality Assurance Lead`
- **Workaround**: `none`
- **Verification Method**: Quyết định/bằng chứng được ghi thành decision record hoặc cập nhật SRS có version, liên kết vào đây.

## Resolution Record

- **Resolved Date**: `2026-10-06`
- **Evidence**: `.agent/governance/decisions/DEC-002.md` — phiếu chốt của Product Owner ngày 2026-10-06.
- **Note**: Phương án A: G-4 lấy lát ngẫu nhiên r% bằng seed cố định trên snapshot của run cuối (độc lập ranking, FR-RNK-07); mẫu số là frame trong phạm vi; đạt khi cận trên KTC 95% ≤ 5%; chưa đủ cỡ mẫu là chưa đạt (FR-GTE-02). Mẫu U của thí nghiệm không dùng cho gate. Giá trị r% chốt theo BLOCKER-015.

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
