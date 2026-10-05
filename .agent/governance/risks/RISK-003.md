---
id: risk-003
title: Reference chậm hoặc tốn công
type: governance
domain: governance
module: risks
tags: [risk, delivery, m13]
priority: 1
---
# RISK-003: Reference chậm hoặc tốn công

## Record Metadata

- **Risk ID**: `RISK-003`
- **Title**: `Reference chậm hoặc tốn công`
- **Owner**: `unassigned (vai trò: Quality Assurance Lead)`
- **Status**: `identified`
- **Category**: `delivery`
- **Probability**: `high`
- **Impact**: `high`
- **Priority**: `1`
- **Created Date**: `2026-10-05`
- **Review Date**: `not-set`

## Risk Statement

If hai người gán GT toàn bộ cho tập hiệu chỉnh, held-out và D1/D2, then reference trễ, resulting in M-04/M-05 bị chặn.

Nguồn: RK-03 (`docs/label-x_system-requirement-specification/sections/11-traceability.tex` bảng rủi ro).

## Exposure Assessment

- **Affected Scope**: `E-07, E-18, M-04, M-05`
- **Impact Description**: M-04/M-05 bị chặn.
- **Detection Signals**: Tiến độ gán GT theo frame/ngày
- **Assumptions**: `none`

## Related Files

- **Epics or Tasks**: `E-07, E-18, M-04, M-05`
- **Decisions**: `none`
- **Issues or Blockers**: `none`
- **Change Requests**: `none`
- **Evidence**: `none`

## Response Plan

- **Strategy**: `mitigate`
- **Mitigation Actions**: Bắt đầu chuẩn bị dữ liệu reference song song M-02/M-03; giới hạn N theo power analysis; task CVAT riêng
- **Contingency Actions**: Thu hẹp N theo power analysis đã duyệt
- **Trigger Threshold**: Tiến độ thấp hơn kế hoạch đã duyệt
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
