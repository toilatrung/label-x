---
id: risk-001
title: Detector yếu trên ảnh đêm/đối tượng nhỏ
type: governance
domain: governance
module: risks
tags: [risk, technical, m13]
priority: 2
---
# RISK-001: Detector yếu trên ảnh đêm/đối tượng nhỏ

## Record Metadata

- **Risk ID**: `RISK-001`
- **Title**: `Detector yếu trên ảnh đêm/đối tượng nhỏ`
- **Owner**: `unassigned (vai trò: Data/Model Owner)`
- **Status**: `identified`
- **Category**: `technical`
- **Probability**: `medium`
- **Impact**: `high`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Review Date**: `not-set`

## Risk Statement

If Detector baseline yếu trên ảnh đêm và đối tượng nhỏ, then ít candidate E1/E2 đúng, resulting in KPI-1 thấp.

Nguồn: RK-01 (`docs/label-x_system-requirement-specification/sections/11-traceability.tex` bảng rủi ro).

## Exposure Assessment

- **Affected Scope**: `E-10, E-17, E-20`
- **Impact Description**: KPI-1 thấp.
- **Detection Signals**: Recall Detector theo slice thấp ở Metric engine
- **Assumptions**: `none`

## Related Files

- **Epics or Tasks**: `E-10, E-17, E-20`
- **Decisions**: `none`
- **Issues or Blockers**: `none`
- **Change Requests**: `none`
- **Evidence**: `none`

## Response Plan

- **Strategy**: `mitigate`
- **Mitigation Actions**: Báo cáo theo slice; h(f) dùng đặc trưng ngày/đêm
- **Contingency Actions**: Cân nhắc Detector khác sau pilot (B-07) qua change request
- **Trigger Threshold**: Recall theo slice đêm thấp rõ rệt so với ngày trên tập hiệu chỉnh
- **Responsible Owner**: `unassigned (vai trò: Data/Model Owner)`

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
