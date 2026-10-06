---
id: blocker-021
title: Đặc tả Model Orchestrator chưa chốt (TBD-21)
type: governance
domain: governance
module: blockers
tags: [blocker, decision, m13]
priority: 2
---
# BLOCKER-021: Đặc tả Model Orchestrator chưa chốt (TBD-21)

## Record Metadata

- **Blocker ID**: `BLOCKER-021`
- **Title**: `Đặc tả Model Orchestrator chưa chốt (TBD-21)`
- **Owner**: `unassigned (vai trò chốt: Data/Model Owner)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `resolved`
- **Blocker Type**: `decision`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

B-05 cần Model Orchestrator tổng hợp kết quả đánh giá engine nhưng đầu vào/đầu ra/provenance chưa đặc tả.

Bằng chứng: docs/label-x_system-requirement-specification/sections/11-traceability.tex TBD-21; docs/00-project/sources/architecture_review.html B-05.

## Impact

- **Blocked Epics or Tasks**: `E-17, E-20`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `.agent/governance/decisions/DEC-002.md`
- **Risks**: `.agent/governance/risks/RISK-011.md`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Đội mô hình đặc tả trước khi đo Metric engine.
- **Responsible Owner**: `unassigned (vai trò: Data/Model Owner)`
- **Dependency or Approval**: `Data/Model Owner`
- **Workaround**: `none`
- **Verification Method**: Quyết định/bằng chứng được ghi thành decision record hoặc cập nhật SRS có version, liên kết vào đây.

## Resolution Record

- **Resolved Date**: `2026-10-06`
- **Evidence**: `.agent/governance/decisions/DEC-002.md` — phiếu chốt của Product Owner ngày 2026-10-06.
- **Note**: Phương án A: đặc tả tối thiểu, xây trong E-17. Đầu vào: evaluation run + GT version. Đầu ra: bảng Precision/Recall theo lớp và theo slice, có provenance (snapshot, model checksum, reference version). Không thêm tham số mới: matching dùng thư viện E-05 với τ_m đã khoá trong reference, slice dùng danh sách của FR-EVL-08. Việc có xây trong MVP 3 tuần hay hoãn (FR-EVL-15 là Should, không thuộc AC nào) do Product Owner quyết theo RISK-011. Cập nhật 2026-10-06: CR-101 được duyệt — FR-EVL-15/Model Orchestrator hoãn sau pilot M13.

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
