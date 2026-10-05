---
id: blocker-016
title: Reference phải phủ cả tập hiệu chỉnh
type: governance
domain: governance
module: blockers
tags: [blocker, decision, m13]
priority: 2
---
# BLOCKER-016: Reference phải phủ cả tập hiệu chỉnh

## Record Metadata

- **Blocker ID**: `BLOCKER-016`
- **Title**: `Reference phải phủ cả tập hiệu chỉnh`
- **Owner**: `unassigned (vai trò chốt: Quality Assurance Lead)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `resolved`
- **Blocker Type**: `decision`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

FR-RNK-10/11 và EX-06 cần 𝓔 trên tập hiệu chỉnh, nhưng hình phân chia dữ liệu chỉ vẽ reference cho held-out; khối lượng AS-04/RK-03 bị ước thấp.

Bằng chứng: docs/label-x_system-requirement-specification/sections/03-data-errors.tex hình phân chia dữ liệu; docs/label-x_system-requirement-specification/sections/06-functional.tex FR-RNK-10, 11; docs/label-x_system-requirement-specification/sections/07-evaluation.tex EX-06.

## Impact

- **Blocked Epics or Tasks**: `E-07, E-17, E-18`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `none`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Xác nhận reference lập cho tập hiệu chỉnh và mọi tập đánh giá thực dùng; cập nhật SRS và ước lượng nhân lực.
- **Responsible Owner**: `unassigned (vai trò: Quality Assurance Lead)`
- **Dependency or Approval**: `Quality Assurance Lead`
- **Workaround**: `none`
- **Verification Method**: Quyết định/bằng chứng được ghi thành decision record hoặc cập nhật SRS có version, liên kết vào đây.

## Resolution Record

- **Resolved Date**: `2026-10-05`
- **Evidence**: docs/label-x_system-requirement-specification/sections/03-data-errors.tex mục Reference: reference lập cho cả tập hiệu chỉnh và held-out, version/khoá riêng; hình phân chia dữ liệu vẽ lại.
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
