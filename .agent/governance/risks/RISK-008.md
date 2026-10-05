---
id: risk-008
title: Guideline chưa có rule ID rõ
type: governance
domain: governance
module: risks
tags: [risk, operational, m13]
priority: 3
---
# RISK-008: Guideline chưa có rule ID rõ

## Record Metadata

- **Risk ID**: `RISK-008`
- **Title**: `Guideline chưa có rule ID rõ`
- **Owner**: `unassigned (vai trò: Quality Assurance Lead)`
- **Status**: `identified`
- **Category**: `operational`
- **Probability**: `medium`
- **Impact**: `medium`
- **Priority**: `3`
- **Created Date**: `2026-10-05`
- **Review Date**: `not-set`

## Risk Statement

If guideline BDD100K của dự án chưa có rule ID, then Workspace không truy vết được rule, resulting in phân xử chậm và Decision Case kém giá trị.

Nguồn: RK-08 (`docs/label-x_system-requirement-specification/sections/11-traceability.tex` bảng rủi ro).

## Exposure Assessment

- **Affected Scope**: `E-03, E-15`
- **Impact Description**: phân xử chậm và Decision Case kém giá trị.
- **Detection Signals**: Mapping rule thiếu cho lớp
- **Assumptions**: `none`

## Related Files

- **Epics or Tasks**: `E-03, E-15`
- **Decisions**: `none`
- **Issues or Blockers**: `none`
- **Change Requests**: `none`
- **Evidence**: `none`

## Response Plan

- **Strategy**: `mitigate`
- **Mitigation Actions**: QA Lead chuẩn hoá rule tối thiểu cho 10 lớp trước pilot (AS-06)
- **Contingency Actions**: Hiển thị guideline dạng văn bản, ghi nhận thiếu
- **Trigger Threshold**: Lớp nào chưa có rule ID khi bắt đầu E-03
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
