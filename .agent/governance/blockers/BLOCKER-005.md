---
id: blocker-005
title: Detector artifact, mapping 10 lớp và training manifest chưa xác nhận
type: governance
domain: governance
module: blockers
tags: [blocker, dependency, m13]
priority: 2
---
# BLOCKER-005: Detector artifact, mapping 10 lớp và training manifest chưa xác nhận

## Record Metadata

- **Blocker ID**: `BLOCKER-005`
- **Title**: `Detector artifact, mapping 10 lớp và training manifest chưa xác nhận`
- **Owner**: `unassigned (vai trò chốt: Data/Model Owner)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `resolved`
- **Blocker Type**: `dependency`
- **Priority**: `1`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

FR-ENG-05 cần artifact/checksum/mapping 10 lớp; FR-EVL-05(b) cần danh sách ảnh huấn luyện; màn ModelsGuidelines chỉ có giá trị minh hoạ.

Bằng chứng: docs/label-x_system-requirement-specification/sections/06-functional.tex FR-ENG-05, FR-EVL-05; docs/label-x_system-requirement-specification/sections/02-overview.tex AS-02, AS-03.

## Impact

- **Blocked Epics or Tasks**: `E-06, E-10, E-18`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `.agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `none`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`

## Resolution Plan

- **Required Action**: Product Owner chọn một Detector công khai huấn luyện trên BDD100K train (đề xuất: Faster R-CNN R-50-FPN 3x hoặc Cascade R-CNN R-50-FPN 3x từ model zoo BDD100K, https://github.com/SysCV/bdd100k-models, Apache-2.0); Nguyễn Xuân Việt Anh freeze checkpoint (SHA-256), mapping 10 lớp; training manifest = danh sách ảnh BDD100K train; kiểm ảnh của tệp annotation người học không thuộc BDD100K train.
- **Responsible Owner**: `Nguyễn Xuân Việt Anh`
- **Dependency or Approval**: `Data/Model Owner`
- **Workaround**: `none`
- **Verification Method**: Quyết định/bằng chứng được ghi thành decision record hoặc cập nhật SRS có version, liên kết vào đây.

## Resolution Record

- **Resolved Date**: `2026-10-06`
- **Evidence**: `.agent/governance/decisions/DEC-002.md`; `.agent/governance/decisions/DEC-003.md` (thay phương án A).
- **Note**: Chốt 2026-10-06 (CR-101 được duyệt): Faster R-CNN R-50-FPN 3x của model zoo BDD100K (https://dl.cv.ethz.ch/bdd100k/det/models/faster_rcnn_r50_fpn_3x_det_bdd100k.pth, AP val 32,30, huấn luyện trên BDD100K train); E-10 freeze SHA-256 và mapping 10 lớp; training manifest = BDD100K train. Cập nhật 2026-10-06 (DEC-003): Product Owner không dùng Detector nội bộ; chuyển sang phương án B — Detector công khai huấn luyện trên BDD100K train, chờ chọn model cụ thể. Ghi chú cũ: phương án A đã chọn: dùng Detector nội bộ hiện có của đội mô hình. Còn chờ bàn giao artifact, checksum, mapping 10 lớp BDD100K và training manifest. Không có training manifest thì không kiểm được AS-03 — khi đó Product Owner chọn lại (phương án B: Detector công khai huấn luyện trên BDD100K train).

## Completion Criteria

- [x] The blocking condition no longer prevents affected work.
- [x] Resolution evidence is linked.
- [x] Affected epic and task statuses are updated.
- [x] Workaround removal is tracked when applicable.

## Forbidden Actions

- Do not mark status `resolved` based only on a proposed action.
- Do not continue blocked work through an unauthorized workaround.
- Do not omit affected epic or task links.
- Do not fabricate resolution evidence.

## Output Requirements

- Save as `.agent/governance/blockers/BLOCKER-<number>.md`.
- Preserve every heading in this template.
- Use repository-relative links and exact enum values.
