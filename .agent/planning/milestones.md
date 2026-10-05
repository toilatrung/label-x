---
id: milestones-v1
title: Milestones
type: planning
domain: governance
module: planning
tags: [milestones, planning]
priority: 2
---
# Milestones

## Purpose

Maintain measurable delivery checkpoints that group epics under approved roadmap outcomes.

## Status Model

- **Valid Statuses**: `proposed | ready | in-progress | blocked | completed | cancelled`

## Milestone Records

| Milestone ID | Roadmap ID | Outcome | Owner | Target Window | Status | Epic IDs | Acceptance Evidence |
|---|---|---|---|---|---|---|---|
| `M-01` | `R-001` | **Nền tảng và hợp đồng triển khai** — Contract dữ liệu/API/state/lineage được review; nền backend+frontend có auth, RBAC theo scope, audit append-only, CI; guideline có version. | `unassigned` | `not-set` | `proposed` | `E-01, E-02, E-03` | Contract E-01 được Tech Lead Backend + QA Lead review; kiểm thử quyền/audit (FR-SEC-01…07) xanh trên CI; `make check` chạy cả backend lẫn frontend. |
| `M-02` | `R-001` | **Pipeline kiểm xác định tái lập** — Snapshot bất biến từ CVAT thật; QC Run với engine xác định, ledger, dedup và ranking score_v0 tái lập. | `unassigned` | `not-set` | `proposed` | `E-04, E-05, E-08, E-09, E-11` | AC-01, AC-02, AC-03 đạt; engine thiếu/hỏng hiển thị Not checked/Failed (phần engine của AC-07). |
| `M-03` | `R-001` | **Vòng review–rework khép kín** — Reviewer xử lý frame theo hàng đợi đến phân xử, sửa trên CVAT, verify và QC run cuối. | `unassigned` | `not-set` | `proposed` | `E-13, E-14, E-15, E-16` | AC-04, AC-05, AC-06, AC-11 đạt; lease nguyên tử dưới tải đồng thời (NFR-15); transition ngoài bảng bị từ chối. |
| `M-04` | `R-001` | **Reference và discovery** — Công cụ reference, reference tập hiệu chỉnh đã khoá; Detector sinh E1/E2; score được hiệu chỉnh và khoá version. | `unassigned` | `not-set` | `proposed` | `E-06, E-07, E-10, E-12, E-17` | Reference hiệu chỉnh khoá version (FR-EVL-04); ngưỡng Detector chọn trên tập hiệu chỉnh; score version khoá kèm kết quả ngoài fold/ablation (FR-RNK-10, 11); TBD-08 có quyết định. |
| `M-05` | `R-001` | **Kiểm chứng hiệu quả, gate và báo cáo** — Reference held-out/D1-D2 khoá; preregistration; thí nghiệm crossover; đánh giá KPI-1/KPI-2; báo cáo và Quality Gate. | `unassigned` | `not-set` | `proposed` | `E-18, E-19, E-20, E-21, E-22` | AC-07, AC-08, AC-09, AC-10 đạt theo ngưỡng đã preregister (TBD-K1…K4); thiếu mẫu ghi "không đủ mẫu", không kết luận đạt. |
| `M-06` | `R-001` | **Vận hành và nghiệm thu tổng thể** — Hệ thống chạy trên môi trường mục tiêu, đo NFR, phục hồi được; bằng chứng nghiệm thu AC-01…AC-11 và R-01…R-07 đầy đủ. | `unassigned` | `not-set` | `proposed` | `E-23, E-24` | NFR có ngưỡng đã duyệt được kiểm; diễn tập restore nhất quán (NFR-16); mọi Must + Should có evidence; blocker bắt buộc đóng. |
