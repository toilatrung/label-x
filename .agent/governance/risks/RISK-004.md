---
id: risk-004
title: Automation bias ở nhánh assisted
type: governance
domain: governance
module: risks
tags: [risk, operational, m13]
priority: 2
---
# RISK-004: Automation bias ở nhánh assisted

## Record Metadata

- **Risk ID**: `RISK-004`
- **Title**: `Automation bias ở nhánh assisted`
- **Owner**: `unassigned (vai trò: Quality Assurance Lead)`
- **Status**: `identified`
- **Category**: `operational`
- **Probability**: `medium`
- **Impact**: `high`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Review Date**: `not-set`

## Risk Statement

If reviewer tin máy quá mức, then bỏ qua lỗi không có candidate, resulting in residual tăng và G-1 trượt.

Nguồn: RK-04 (`docs/label-x_system-requirement-specification/sections/11-traceability.tex` bảng rủi ro).

## Exposure Assessment

- **Affected Scope**: `E-14, E-19, E-20`
- **Impact Description**: residual tăng và G-1 trượt.
- **Detection Signals**: KPI-2b thấp; residual assisted cao hơn baseline
- **Assumptions**: `none`

## Related Files

- **Epics or Tasks**: `E-14, E-19, E-20`
- **Decisions**: `none`
- **Issues or Blockers**: `none`
- **Change Requests**: `none`
- **Evidence**: `none`

## Response Plan

- **Strategy**: `mitigate`
- **Mitigation Actions**: Lát ngẫu nhiên; Frame Review hiển thị toàn ảnh; đo KPI-2b và residual
- **Contingency Actions**: Bổ sung hướng dẫn và buổi làm quen
- **Trigger Threshold**: Cận trên CI của ρ_A − ρ_B tiến gần δ
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
