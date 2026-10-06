---
id: roadmap-v1
title: Project Roadmap
type: planning
domain: governance
module: planning
tags: [roadmap, milestones, planning]
priority: 1
---
# Project Roadmap

## Purpose

Maintain the approved sequence of outcome-level roadmap items and their target windows without defining task-level implementation.

## Status Model

- **Valid Statuses**: `ROADMAP_DRAFT | ROADMAP_APPROVED | ROADMAP_ACTIVE | ROADMAP_BLOCKED | ROADMAP_DONE | ROADMAP_CANCELLED`

## Roadmap Records

| Roadmap ID | Outcome | Owner | Target Window | Status | Milestone IDs | Change Request |
|---|---|---|---|---|---|---|
| `R-001` | Hoàn thành và nghiệm thu LabelX M13 (phạm vi pilot theo CR-101, SRS v1.1) — Reviewer Prioritization Assistant: CVAT → snapshot → phân tích nghi vấn → xếp hạng frame → review/phân xử/rework → đo KPI-1, KPI-2 và báo cáo hiệu quả | `project-owner (Trịnh Quang Trung, @toilatrung)` | `2026-10-06 → 2026-10-27` | `ROADMAP_APPROVED` | `M-01, M-02, M-03, M-04, M-05, M-06` | `CR-101` |

## Basis

- Nguồn: SRS M13 v1.0 (`docs/label-x_system-requirement-specification/sections/`), `docs/00-project/sources/architecture_review.html` (B-01…B-21, R-01…R-07, mục 7 — thứ tự triển khai), `docs/00-project/charter.md`, `.agent/governance/decisions/DEC-001.md`.
- Thứ tự milestone theo bản rà soát R và charter: nền tảng → kiểm xác định → review/rework → reference + discovery → kiểm chứng/gate/báo cáo → vận hành/nghiệm thu. Đây là thứ tự phụ thuộc, không phải lịch.
- Phạm vi hoàn thành: SRS v1.1 — mọi yêu cầu Must và Should trừ danh sách hoãn ở SRS mục "Phạm vi pilot theo CR-101"; FR-RNK-09 (Could) ở backlog; VLM tắt (`BLOCKER-002`).
- Lập qua ba vòng thảo luận độc lập Claude ↔ Codex ngày 2026-10-05; thống nhất 24 epic, 21 blocker, 10 risk.
- Trạng thái `ROADMAP_APPROVED` ngày 2026-10-06 theo `.agent/governance/decisions/DEC-004.md`: Product Owner duyệt `CR-101` (phạm vi MVP và lịch) và SRS v1.1. Sản phẩm hoàn thiện 2026-10-20; thử nghiệm 2026-10-20…23; nghiệm thu 2026-10-27.
- Phiếu chốt blocker 2026-10-06 (`.agent/governance/decisions/DEC-002.md`): Product Owner ký từng epic và gán task cho từng developer thay cho việc chờ ký SRS theo vai trò (`BLOCKER-001`); target window 3 tuần do Product Owner thông báo.
- Kế hoạch gồm cả triển khai frontend: mỗi epic có màn hình phải xong cả backend và frontend chạy trên API thật. `docs/design/` là thiết kế mẫu để tham khảo khi code frontend; delta thiết kế bổ sung just-in-time trước epic dùng tới (`BLOCKER-013`).
- Khung 3 tuần so với phạm vi: SRS có 87 FR Must, 12 Should, 2 Could; chuỗi chi phối gồm 17 epic nối tiếp và M-04/M-05 cần nhân lực ngoài đội phát triển (reference hai GT, ≥ 4 reviewer, người phân xử thí nghiệm riêng). Phạm vi MVP chốt bằng `CR-101` (`RISK-011`).
