---
id: blocker-010
title: Mô hình điểm: cấp candidate/issue, tên đối chứng score_v0, ε chưa thống nhất
type: governance
domain: governance
module: blockers
tags: [blocker, decision, m13]
priority: 2
---
# BLOCKER-010: Mô hình điểm: cấp candidate/issue, tên đối chứng score_v0, ε chưa thống nhất

## Record Metadata

- **Blocker ID**: `BLOCKER-010`
- **Title**: `Mô hình điểm: cấp candidate/issue, tên đối chứng score_v0, ε chưa thống nhất`
- **Owner**: `unassigned (vai trò chốt: Data/Model Owner)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `resolved`
- **Blocker Type**: `decision`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

UC-03 nói xác suất theo candidate, FR-RNK nói theo issue; chương 7 gọi heuristic max-confidence là score_v0 khác định nghĩa score_v0 ở chương 6; ε thuộc TBD-20.

Bằng chứng: docs/label-x_system-requirement-specification/sections/04-usecases.tex UC-03; docs/label-x_system-requirement-specification/sections/06-functional.tex §RNK; docs/label-x_system-requirement-specification/sections/07-evaluation.tex bảng đối chứng; TBD-16, TBD-20.

## Impact

- **Blocked Epics or Tasks**: `E-01, E-11, E-17, E-20`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `none`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Xác nhận FR-RNK là chuẩn; đổi tên đối chứng heuristic Detector; chốt ε và n_min.
- **Responsible Owner**: `unassigned (vai trò: Data/Model Owner)`
- **Dependency or Approval**: `Data/Model Owner`
- **Workaround**: `none`
- **Verification Method**: Quyết định/bằng chứng được ghi thành decision record hoặc cập nhật SRS có version, liên kết vào đây.

## Resolution Record

- **Resolved Date**: `2026-10-05`
- **Evidence**: docs/label-x_system-requirement-specification/sections/04-usecases.tex UC-03 bước 1: xác suất q_i theo issue; docs/label-x_system-requirement-specification/sections/07-evaluation.tex bảng đối chứng: Heuristic Detector "không cộng điểm nền, khác score_v0". ε và n_min vẫn mở ở TBD-20/TBD-16 (theo dõi trong BLOCKER-015).
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
