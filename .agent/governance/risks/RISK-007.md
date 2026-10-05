---
id: risk-007
title: Ít lỗi E3 tự nhiên
type: governance
domain: governance
module: risks
tags: [risk, technical, m13]
priority: 4
---
# RISK-007: Ít lỗi E3 tự nhiên

## Record Metadata

- **Risk ID**: `RISK-007`
- **Title**: `Ít lỗi E3 tự nhiên`
- **Owner**: `unassigned (vai trò: Quality Assurance Lead)`
- **Status**: `identified`
- **Category**: `technical`
- **Probability**: `high`
- **Impact**: `low`
- **Priority**: `4`
- **Created Date**: `2026-10-05`
- **Review Date**: `not-set`

## Risk Statement

If lỗi E3 tự nhiên ít, then không đủ mẫu kết luận theo nhóm, resulting in chỉ kết luận được KPI tổng.

Nguồn: RK-07 (`docs/label-x_system-requirement-specification/sections/11-traceability.tex` bảng rủi ro).

## Exposure Assessment

- **Affected Scope**: `E-20`
- **Impact Description**: chỉ kết luận được KPI tổng.
- **Detection Signals**: |𝓔_E3| < E_min,g
- **Assumptions**: `none`

## Related Files

- **Epics or Tasks**: `E-20`
- **Decisions**: `none`
- **Issues or Blockers**: `none`
- **Change Requests**: `none`
- **Evidence**: `none`

## Response Plan

- **Strategy**: `mitigate`
- **Mitigation Actions**: E_min,g; lỗi chèn báo cáo riêng (BR-15)
- **Contingency Actions**: Chỉ báo cáo E3, không kết luận
- **Trigger Threshold**: Số E3 trên tập hiệu chỉnh dưới E_min,g
- **Responsible Owner**: `unassigned (vai trò: Quality Assurance Lead)`

## Review Record

- **Last Reviewed Date**: `2026-10-05`
- **Reviewed By**: `claude-code, codex`
- **Probability Change**: `unchanged`
- **Impact Change**: `unchanged`
- **Review Evidence**: `.agent/planning/roadmap.md`

## Completion Criteria

- [ ] The risk is eliminated, accepted by an authorized owner, transferred, or converted to an issue after realization.
- [ ] Final status and supporting evidence are recorded.
- [ ] Related tasks, blockers, issues, and decisions are updated.

## Forbidden Actions

- Do not close a risk solely because its review date passed.
- Do not accept a high or critical risk without an identified authorized owner.
- Do not use vague triggers or unowned mitigation actions.
- Do not delete prior assessments when exposure changes.

## Output Requirements

- Save as `.agent/governance/risks/RISK-<number>.md`.
- Preserve every heading in this template.
- Use repository-relative links and exact enum values.
