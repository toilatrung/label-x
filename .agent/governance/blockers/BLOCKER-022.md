---
id: blocker-022
title: QA Lead và QC Admin của pilot chưa gán
type: governance
domain: governance
module: blockers
tags: [blocker, approval, roles, m13]
priority: 2
---
# BLOCKER-022: QA Lead và QC Admin của pilot chưa gán

## Record Metadata

- **Blocker ID**: `BLOCKER-022`
- **Title**: `QA Lead và QC Admin của pilot chưa gán`
- **Owner**: `project-owner (Trịnh Quang Trung, @toilatrung)`
- **Reporter**: `claude-code (planner)`
- **Status**: `open`
- **Blocker Type**: `approval`
- **Priority**: `1`
- **Created Date**: `2026-10-06`
- **Target Resolution Date**: `2026-10-16`

## Blocking Condition

Vai Quality Assurance Lead và Quality Control Admin khi chạy pilot chưa có người. Product Owner ghi nhận ngày 2026-10-06: "Lưu lại, tôi sẽ bổ sung sau".

QA Lead phải chốt TBD-05, 06 trước khi khoá reference (E-06, trước 2026-10-15), TBD-07, 10 trước pilot, TBD-K4 (E_min) trước chạy held-out và cùng Product Owner chốt TBD-K3 trước khoá preregistration 2026-10-19; QA Lead duyệt và khoá reference (AS-04 bản v1.1). QC Admin cấu hình engine, ngưỡng và quyền trên môi trường pilot.

Bằng chứng: `docs/label-x_system-requirement-specification/sections/11-traceability.tex` bảng TBD; `.agent/governance/decisions/DEC-003.md`.

## Impact

- **Blocked Epics or Tasks**: `E-06, E-07, E-18, E-19, E-20, E-22`
- **Blocked Deliverables**: khoá reference, preregistration, đánh giá KPI và gate
- **Schedule or Quality Impact**: chưa gán trước 2026-10-15 thì reference không khoá kịp mốc M-03/M-04 2026-10-16

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `.agent/governance/decisions/DEC-003.md`
- **Risks**: `.agent/governance/risks/RISK-011.md`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`

## Resolution Plan

- **Required Action**: Product Owner gán người cho QA Lead và QC Admin của pilot và ghi vào decision record; QA Lead không phải người phân xử thí nghiệm (BLOCKER-019).
- **Responsible Owner**: `project-owner (Trịnh Quang Trung, @toilatrung)`
- **Dependency or Approval**: `Product Owner`
- **Workaround**: `none`
- **Verification Method**: Decision record ghi tên người và ngày, liên kết vào đây.

## Completion Criteria

- [ ] The blocking condition no longer prevents affected work.
- [ ] Resolution evidence is linked.
- [ ] Affected epic and task statuses are updated.
- [ ] Workaround removal is tracked when applicable.

## Forbidden Actions

- Do not mark status `resolved` based only on a proposed action.
- Do not continue blocked work through an unauthorized workaround.
- Do not omit affected epic or task links.
- Do not fabricate resolution evidence.

## Output Requirements

- Save as `.agent/governance/blockers/BLOCKER-<number>.md`.
- Preserve every heading in this template.
- Use repository-relative links and exact enum values.
