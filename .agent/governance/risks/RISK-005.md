---
id: risk-005
title: Effort log sai do bỏ máy, nhiều tab
type: governance
domain: governance
module: risks
tags: [risk, technical, m13]
priority: 3
---
# RISK-005: Effort log sai do bỏ máy, nhiều tab

## Record Metadata

- **Risk ID**: `RISK-005`
- **Title**: `Effort log sai do bỏ máy, nhiều tab`
- **Owner**: `unassigned (vai trò: Tech Lead Backend)`
- **Status**: `identified`
- **Category**: `technical`
- **Probability**: `medium`
- **Impact**: `medium`
- **Priority**: `3`
- **Created Date**: `2026-10-05`
- **Review Date**: `not-set`

## Risk Statement

If reviewer bỏ máy hoặc mở nhiều tab, then effort log sai, resulting in KPI-2 sai lệch.

Nguồn: RK-05 (`docs/label-x_system-requirement-specification/sections/11-traceability.tex` bảng rủi ro).

## Exposure Assessment

- **Affected Scope**: `E-13, E-14, E-20`
- **Impact Description**: KPI-2 sai lệch.
- **Detection Signals**: Phiên effort dài bất thường
- **Assumptions**: `none`

## Related Files

- **Epics or Tasks**: `E-13, E-14, E-20`
- **Decisions**: `none`
- **Issues or Blockers**: `none`
- **Change Requests**: `none`
- **Evidence**: `none`

## Response Plan

- **Strategy**: `mitigate`
- **Mitigation Actions**: Ngưỡng t_idle; một lease mỗi reviewer; quy tắc loại phiên bất thường khoá trước
- **Contingency Actions**: Phân tích độ nhạy hai giá trị t_idle
- **Trigger Threshold**: Tỉ lệ phiên bị loại vượt quy tắc đã khoá
- **Responsible Owner**: `unassigned (vai trò: Tech Lead Backend)`

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
