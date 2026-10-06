---
id: risk-011
title: Khung 3 tuần không đủ cho toàn bộ phạm vi R-001
type: governance
domain: governance
module: risks
tags: [risk, delivery, schedule, m13]
priority: 1
---
# RISK-011: Khung 3 tuần không đủ cho toàn bộ phạm vi R-001

## Record Metadata

- **Risk ID**: `RISK-011`
- **Title**: `Khung 3 tuần không đủ cho toàn bộ phạm vi R-001`
- **Owner**: `project-owner (Trịnh Quang Trung, @toilatrung)`
- **Status**: `mitigating`
- **Category**: `delivery`
- **Probability**: `high`
- **Impact**: `high`
- **Priority**: `1`
- **Created Date**: `2026-10-06`
- **Review Date**: `2026-10-08`

## Risk Statement

If giữ nguyên phạm vi R-001 (mọi Must + Should, 24 epic, thí nghiệm crossover và reference hai GT cho hai tập dữ liệu) trong khung 3 tuần 2026-10-06 → 2026-10-27, then các epic M-04…M-06 không hoàn tất và KPI-1/KPI-2 không có số liệu nghiệm thu, resulting in R-001 không được nghiệm thu đúng hạn.

Căn cứ: Product Owner thông báo khung 3 tuần trong `.agent/governance/decisions/DEC-002.md`; chuỗi chi phối trong `.agent/planning/dependency-graph.md` gồm 17 epic nối tiếp; E-07, E-18, E-19 phụ thuộc nhân lực ngoài đội phát triển (hai người xác minh GT, ≥ 4 reviewer, người phân xử thí nghiệm riêng theo BLOCKER-019); ngưỡng NFR và cỡ mẫu chỉ chốt được sau đo pilot (BLOCKER-014, BLOCKER-015).

## Exposure Assessment

- **Affected Scope**: `R-001, M-04, M-05, M-06, E-06, E-07, E-10, E-17, E-18, E-19, E-20, E-21, E-22, E-23, E-24`
- **Impact Description**: Không đủ thời gian lập reference đã khoá, chạy thí nghiệm crossover và đo KPI theo phương pháp đã preregister; nghiệm thu thiếu AC-08…AC-10.
- **Detection Signals**: Cuối tuần 1 (2026-10-13) M-01 chưa xong; reference tập hiệu chỉnh chưa bắt đầu gán GT trước 2026-10-13; chưa có danh sách reviewer cho thí nghiệm trước 2026-10-15.
- **Assumptions**: `Số developer và người xác minh/reviewer sẵn có chưa được cung cấp.`

## Related Files

- **Epics or Tasks**: `E-06, E-07, E-10, E-17, E-18, E-19, E-20, E-21, E-22, E-23, E-24`
- **Decisions**: `.agent/governance/decisions/DEC-002.md`
- **Issues or Blockers**: `BLOCKER-004, BLOCKER-005, BLOCKER-014, BLOCKER-015`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`
- **Evidence**: `.agent/planning/dependency-graph.md`

## Response Plan

- **Strategy**: `mitigate`
- **Mitigation Actions**: Product Owner quyết định phạm vi MVP 3 tuần theo đề xuất `.agent/governance/change-requests/CR-101.md` trước khi khoá roadmap; chạy song song backend/frontend trong mỗi epic; bắt đầu chuẩn bị dữ liệu reference ngay tuần 1.
- **Contingency Actions**: Hoãn Should không nằm trên đường đo KPI (FR-EVL-15 Metric engine/Model Orchestrator, FR-RNK-10/11 hiệu chỉnh score, VLM) sang giai đoạn sau; nếu không đủ người cho thí nghiệm thì báo cáo KPI-2 "không đủ mẫu" thay vì kết luận đạt.
- **Trigger Threshold**: Bất kỳ tín hiệu trong Detection Signals xảy ra.
- **Responsible Owner**: `project-owner (Trịnh Quang Trung, @toilatrung)`

## Review Record

- **Last Reviewed Date**: `2026-10-06`
- **Reviewed By**: `claude-code (planner)`
- **Probability Change**: `decreased`
- **Impact Change**: `unchanged`
- **Review Evidence**: `.agent/governance/decisions/DEC-002.md`; `.agent/governance/change-requests/CR-101.md` được duyệt 2026-10-06 (phạm vi MVP, GT BDD100K, reviewer ngoài đã xác nhận)

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
