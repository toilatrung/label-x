---
id: domain-overview
title: Domain Model
type: reference
domain: domain
module: repository
tags: [domain, model, services]
priority: 3
---
# Domain Model

Mô hình domain của LabelX — module Quality Control quanh CVAT, phạm vi M13 (ưu tiên review frame trên ảnh BDD100K, Bounding box). Nguồn: quyết định đã chốt trong [architecture_review.html](../00-project/sources/architecture_review.html) (B-01…B-21, cấu hình MVP, R-01…R-07), SRS LaTeX ở [label-x_system-requirement-specification](../label-x_system-requirement-specification/sections/) và màn hình chuẩn hành vi H ở [docs/design/screens](../design/screens/).

## Nội dung

| Tài liệu | Nội dung |
|---|---|
| [aggregates.md](aggregates.md) | Dataset, Snapshot, QualityControlRun + ledger, Candidate, Issue, Lease, ReviewDecision, ReworkRequest, Reference, EvaluationRun, Experiment/EffortLog, Gate/Waiver, Guideline, AuditLog — invariant, vòng đời, trạng thái công khai theo H (B-19) |
| [value-objects.md](value-objects.md) | BBox, LabelClass, RevisionHash, ErrorFamily E1–E3, Severity, DedupKey, IdempotencyKey, RiskScore, CoverageUnit, EngineStatus… |
| [services.md](services.md) | Matching, suy ra lỗi, sinh candidate, gộp, xếp hạng, review workflow, coverage ledger, đánh giá, gate — quy tắc BR-xx (SRS) và DR-xx |

## Nguyên tắc cốt lõi

- CVAT là nguồn annotation và editor duy nhất; adapter chỉ đọc (B-18).
- Candidate là nghi vấn bất biến; Issue là đơn vị review; con người quyết định, AI không tự xác nhận (B-10, R-02).
- Not checked / Partial / Failed không bao giờ là đạt (B-19).
- Đo chất lượng chỉ trên reference đã duyệt và khoá; Detector không phải Ground Truth (B-05, B-20).

Liên quan: [AI và đánh giá](../12-ai/index.md), [Testing](../09-testing/index.md).
