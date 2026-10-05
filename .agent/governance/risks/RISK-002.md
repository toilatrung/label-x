---
id: risk-002
title: Detector đã thấy ảnh held-out khi huấn luyện
type: governance
domain: governance
module: risks
tags: [risk, technical, m13]
priority: 1
---
# RISK-002: Detector đã thấy ảnh held-out khi huấn luyện

## Record Metadata

- **Risk ID**: `RISK-002`
- **Title**: `Detector đã thấy ảnh held-out khi huấn luyện`
- **Owner**: `unassigned (vai trò: Data/Model Owner)`
- **Status**: `identified`
- **Category**: `technical`
- **Probability**: `medium`
- **Impact**: `high`
- **Priority**: `1`
- **Created Date**: `2026-10-05`
- **Review Date**: `not-set`

## Risk Statement

If Detector được huấn luyện trên ảnh held-out, then recall bị thổi phồng, resulting in kết quả KPI-1 không hợp lệ.

Nguồn: RK-02 (`docs/label-x_system-requirement-specification/sections/11-traceability.tex` bảng rủi ro).

## Exposure Assessment

- **Affected Scope**: `E-06, E-18, E-20`
- **Impact Description**: kết quả KPI-1 không hợp lệ.
- **Detection Signals**: Giao nhau giữa training manifest và held-out
- **Assumptions**: `none`

## Related Files

- **Epics or Tasks**: `E-06, E-18, E-20`
- **Decisions**: `none`
- **Issues or Blockers**: `none`
- **Change Requests**: `none`
- **Evidence**: `none`

## Response Plan

- **Strategy**: `mitigate`
- **Mitigation Actions**: FR-EVL-05(b); chọn held-out từ phần chắc chắn không dùng huấn luyện
- **Contingency Actions**: Huỷ kết quả, chọn held-out mới
- **Trigger Threshold**: Bất kỳ ảnh giao nhau nào
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
