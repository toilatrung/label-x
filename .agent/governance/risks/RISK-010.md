---
id: risk-010
title: KPI trượt trên held-out
type: governance
domain: governance
module: risks
tags: [risk, delivery, m13]
priority: 2
---
# RISK-010: KPI trượt trên held-out

## Record Metadata

- **Risk ID**: `RISK-010`
- **Title**: `KPI trượt trên held-out`
- **Owner**: `unassigned (vai trò: Product Owner)`
- **Status**: `identified`
- **Category**: `delivery`
- **Probability**: `medium`
- **Impact**: `high`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Review Date**: `not-set`

## Risk Statement

If KPI-1 hoặc KPI-2 không đạt trên held-out, then không nghiệm thu được, resulting in phải hiệu chỉnh lại và cần tập đánh giá độc lập mới.

Nguồn: Thảo luận Claude–Codex (G8) (`docs/label-x_system-requirement-specification/sections/11-traceability.tex` bảng rủi ro — bổ sung).

## Exposure Assessment

- **Affected Scope**: `E-20, E-24`
- **Impact Description**: phải hiệu chỉnh lại và cần tập đánh giá độc lập mới.
- **Detection Signals**: AC-08/AC-09 không đạt
- **Assumptions**: `none`

## Related Files

- **Epics or Tasks**: `E-20, E-24`
- **Decisions**: `none`
- **Issues or Blockers**: `none`
- **Change Requests**: `none`
- **Evidence**: `none`

## Response Plan

- **Strategy**: `mitigate`
- **Mitigation Actions**: Kiểm chứng kỹ trên tập hiệu chỉnh (ablation, ngoài fold) trước khi chạy held-out
- **Contingency Actions**: Change request; hiệu chỉnh trên tập hiệu chỉnh; đánh giá trên tập độc lập mới, không tái dùng held-out
- **Trigger Threshold**: Cận dưới CI dưới ngưỡng TBD-K1/K2
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
