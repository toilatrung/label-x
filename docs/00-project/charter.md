---
id: project-charter
title: Project Charter — LabelX
type: reference
domain: project
module: repository
tags: [charter, scope, objectives, m13]
priority: 1
---
# Project Charter — LabelX

## Purpose

Xác định mục đích, phạm vi, mục tiêu đo được, ràng buộc và thứ tự triển khai của LabelX ở giai đoạn nghiệm thu đầu tiên (chức năng M13).

## Bối cảnh và vấn đề

LabelX là module Quality Control chạy quanh CVAT: snapshot annotation → engine kiểm tra → review/rework → Quality Gate → báo cáo. Review thủ công tuần tự tốn công vì lỗi phân bố không đều, reviewer thiếu bằng chứng tại chỗ, và chưa đo được lỗi còn sót. Chức năng M13 — **Reviewer Prioritization Assistant** (tên đề tài đăng ký: Annotation QC Studio) — giải bài toán ưu tiên: xem frame nào trước để bắt nhiều lỗi thật nhất với cùng công sức, kèm bằng chứng để reviewer quyết định. Con người luôn là người quyết định (R-02).

## Phạm vi nghiệm thu

- **Luồng duy nhất:** Annotation từ CVAT → phân tích nghi vấn → xếp hạng frame → reviewer xem bằng chứng và phân xử → báo cáo hiệu quả.
- **Dữ liệu:** Bounding box trên BDD100K (10 lớp), ba nhóm lỗi: E1 thiếu box, E2 sai lớp, E3 trùng box.
- **Hỗ trợ ở mức cần thiết:** tra cứu guideline, rework và kiểm lại sau sửa, phân quyền/audit, Quality Gate tối thiểu.
- **Ngoài phạm vi:** temporal/track, polygon, video, ghi annotation ngược vào CVAT, Diff/pre-label, Classifier thứ hai, RAG, phát hành dataset đầy đủ. VLM không bật trong pilot là đề xuất chờ Product Owner duyệt (TBD-08).

## Mục tiêu đo được

| Mã | Mục tiêu | Cách đo |
|---|---|---|
| KPI-1 | Recall lỗi trong top 20% frame | Lỗi đã xác minh độc lập nằm trong 20% frame được ưu tiên đầu / tổng lỗi đã xác minh của tập held-out |
| KPI-2 | Giảm công sức review với chất lượng tương đương | 1 − T_assisted / T_baseline, tính cả xử lý cảnh báo sai, phân xử và kiểm lại sau sửa; chất lượng kiểm bằng non-inferiority |

Ngưỡng đạt (TBD-K1…K4) chốt từ đo baseline trước khi chạy held-out. Chi tiết phương pháp: [SRS chương 7](../01-business/labelX.html).

## Sản phẩm bàn giao

- SRS M13 v1.0: [labelX.html](../01-business/labelX.html), bản LaTeX `docs/label-x_system-requirement-specification/`.
- Hệ thống LabelX MVP theo stack ở `.agent/governance/decisions/DEC-001.md`: Django 5.2 + DRF, PostgreSQL 17, Celery + Redis, Object Storage S3-compatible, frontend Next.js 16.
- Reference độc lập (GT + tập lỗi) của tập đánh giá; báo cáo pilot KPI-1, KPI-2.

## Ràng buộc

- 21 quyết định kiến trúc B-01…B-21 đã chốt trong `docs/00-project/sources/architecture_review.html`; thay đổi cần change request được duyệt.
- Adapter CVAT chỉ đọc; Celery task idempotent; quyền project/job kiểm ở API (CLAUDE.md).
- Giao diện theo Design System LabelX (`docs/design/`).

## Thứ tự triển khai đề xuất

Theo bản rà soát đã chốt (mục 7), là thứ tự phụ thuộc, không phải lịch:

1. Chốt ranh giới và nền tảng: adapter, snapshot, contract, quyền.
2. Kiểm xác định + review/rework: candidate có provenance, vòng verify.
3. Reference + discovery (Detector) + audit.
4. Gate, báo cáo, pilot đo KPI.
5. Mở rộng (temporal, classifier, feedback) chỉ sau quyết định scope.

Planning (bản nháp, chờ duyệt): roadmap `R-001` (ROADMAP_DRAFT) ở `.agent/planning/roadmap.md`, milestone M-01…M-06 ở `.agent/planning/milestones.md`, epic E-01…E-24 (EPIC_PROPOSED) ở `.agent/planning/epics.md`, phụ thuộc ở `.agent/planning/dependency-graph.md`. Blocker BLOCKER-001…021 và risk RISK-001…010 ở `.agent/governance/`. Chưa có task nào được tạo.

## Stakeholder

Xem [stakeholders.md](stakeholders.md).
