---
id: project-stakeholders
title: Stakeholder và lớp người dùng LabelX
type: reference
domain: project
module: repository
tags: [stakeholders, roles, users]
priority: 2
---

# Stakeholder và lớp người dùng LabelX

## Purpose

Vai trò tham gia dự án và người dùng hệ thống, trách nhiệm phê duyệt và quyền chính. Tên người cụ thể chưa được gán (cần điền khi giao việc).

## Lớp người dùng

| Vai trò | Mô tả và nhiệm vụ | Quyền chính |
|---|---|---|
| Reviewer | Người dùng chính. Làm việc theo hàng đợi ưu tiên, xem bằng chứng, ra quyết định, yêu cầu sửa, xác minh sau sửa. | Review; yêu cầu/xác minh rework. Không review annotation của mình. |
| Annotator | Sửa annotation trên CVAT theo yêu cầu rework; tham gia calibration. | Xem yêu cầu sửa của mình; thực hiện rework trên CVAT. |
| Quality Assurance Lead | Phân xử, quản lý nội dung guideline, chịu trách nhiệm reference và tập held-out; duyệt ngoại lệ khi được cấp quyền. | Adjudication; quản lý audit/calibration; duyệt waiver (khác người yêu cầu). |
| Quality Control Admin | Cấu hình kỹ thuật: engine, ngưỡng, policy version, mapping guideline, scope quyền. | Configuration (engine, ngưỡng, quyền). Không chạy phân tích (theo H: QA Lead chạy/xem). |
| Product / Data Owner | Chốt phạm vi, ngưỡng KPI, đọc báo cáo hiệu quả; quản lý dữ liệu BDD100K và artifact Detector. | Xem báo cáo; duyệt tiêu chí. |
| Super Admin | Quản trị hệ thống. Không là người duyệt mặc định; mọi ghi đè phải có lý do và gắn nhãn trong audit. | Ghi đè có lý do; vẫn chịu self-review và tách nhiệm vụ. |

## Trách nhiệm phê duyệt SRS

| Vai trò | Phê duyệt | Người được gán |
|---|---|---|
| Product Owner M13 | Phạm vi, KPI, tiêu chí nghiệm thu | chưa gán |
| Quality Assurance Lead | Taxonomy lỗi, reference, quy trình phân xử | chưa gán |
| Quality Control Admin | Cấu hình kỹ thuật, quyền, engine | chưa gán |
| Tech Lead Backend | Kiến trúc, API, yêu cầu phi chức năng | chưa gán |
| Data/Model Owner | Dữ liệu BDD100K, Detector baseline | chưa gán |

## Quy tắc tách nhiệm vụ

- Reviewer không review annotation của chính mình (assignee tại snapshot) — B-12.
- Người duyệt waiver, khoá reference, phân xử khác người yêu cầu — B-11, B-12.
- Super Admin không là người duyệt mặc định; ghi đè phải có lý do và gắn nhãn trong audit.

Nguồn: [SRS M13](../01-business/labelX.html) mục 2.6, bảng ma trận quyền chương 6; `docs/00-project/sources/architecture_review.html`.
