---
id: risk-009
title: Đổi tham số sau khi thấy kết quả held-out
type: governance
domain: governance
module: risks
tags: [risk, compliance, m13]
priority: 1
---
# RISK-009: Đổi tham số sau khi thấy kết quả held-out

## Record Metadata

- **Risk ID**: `RISK-009`
- **Title**: `Đổi tham số sau khi thấy kết quả held-out`
- **Owner**: `unassigned (vai trò: Product Owner)`
- **Status**: `identified`
- **Category**: `compliance`
- **Probability**: `medium`
- **Impact**: `high`
- **Priority**: `1`
- **Created Date**: `2026-10-05`
- **Review Date**: `not-set`

## Risk Statement

If tham số bị đổi sau khi thấy kết quả held-out, then kết quả bị thiên lệch, resulting in nghiệm thu không hợp lệ.

Nguồn: RK-09 (`docs/label-x_system-requirement-specification/sections/11-traceability.tex` bảng rủi ro).

## Exposure Assessment

- **Affected Scope**: `E-19, E-20, E-24`
- **Impact Description**: nghiệm thu không hợp lệ.
- **Detection Signals**: Thay đổi version sau mốc khoá trong audit
- **Assumptions**: `none`

## Related Files

- **Epics or Tasks**: `E-19, E-20, E-24`
- **Decisions**: `none`
- **Issues or Blockers**: `none`
- **Change Requests**: `none`
- **Evidence**: `none`

## Response Plan

- **Strategy**: `mitigate`
- **Mitigation Actions**: Preregistration (SRS §7.3); audit mọi thay đổi version
- **Contingency Actions**: Báo cáo cả kết quả phiên bản cũ
- **Trigger Threshold**: Bất kỳ thay đổi version sau khoá
- **Responsible Owner**: `unassigned (vai trò: Product Owner)`

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
