---
id: risk-006
title: CVAT API không cho kiểm drift tin cậy
type: governance
domain: governance
module: risks
tags: [risk, external, m13]
priority: 2
---
# RISK-006: CVAT API không cho kiểm drift tin cậy

## Record Metadata

- **Risk ID**: `RISK-006`
- **Title**: `CVAT API không cho kiểm drift tin cậy`
- **Owner**: `unassigned (vai trò: Tech Lead Backend)`
- **Status**: `identified`
- **Category**: `external`
- **Probability**: `low`
- **Impact**: `high`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Review Date**: `not-set`

## Risk Statement

If CVAT không cung cấp dấu thay đổi tin cậy, then không khoá được snapshot nhất quán, resulting in chặn toàn luồng.

Nguồn: RK-06 (`docs/label-x_system-requirement-specification/sections/11-traceability.tex` bảng rủi ro).

## Exposure Assessment

- **Affected Scope**: `E-04`
- **Impact Description**: chặn toàn luồng.
- **Detection Signals**: Spike adapter không phát hiện được sửa đổi trong lúc export
- **Assumptions**: `none`

## Related Files

- **Epics or Tasks**: `E-04`
- **Decisions**: `none`
- **Issues or Blockers**: `none`
- **Change Requests**: `none`
- **Evidence**: `none`

## Response Plan

- **Strategy**: `mitigate`
- **Mitigation Actions**: Spike adapter trên CVAT thật trước build (B-02)
- **Contingency Actions**: Tạm khoá sửa phạm vi khi export
- **Trigger Threshold**: AC-03 không tái hiện được
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
