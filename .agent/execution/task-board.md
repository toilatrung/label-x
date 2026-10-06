---
id: task-board
title: Task Board
type: execution
domain: governance
module: execution
tags: [tasks, execution, board]
priority: 1
---
# Task Board

## Purpose

Maintain the authoritative registry of executable tasks and their lifecycle state.

## Status Model

- **Valid Statuses**: `pending | in-progress | blocked | review | done | cancelled`
- `pending -> in-progress` requires an owner, sufficient context, satisfied dependencies, and parent epic `EPIC_IN_PROGRESS`.
- `in-progress -> blocked` requires a linked blocker.
- `in-progress -> review` requires implementation evidence and acceptance-criteria results.
- `review -> done` requires required review and QA evidence.
- `blocked -> in-progress` requires verified blocker resolution.
- `cancelled` requires an authorized rationale; `done` and `cancelled` are terminal.

## Task Records

| Task ID | Epic ID | Title | Owner | Status | Dependencies | Blocker IDs | Evidence Links | Updated Date |
|---|---|---|---|---|---|---|---|---|
| T-001 | E-01 | Contract M13 v1: OpenAPI baseline, state machine, ADR lineage | Trịnh Quang Trung (@toilatrung) | pending | none | none | none | 2026-10-06 |
| T-002 | E-02 | App shell frontend, đăng nhập, test runner frontend | Trần Đức Thọ (@tdt2112) | pending | none (mock API tới khi T-001 xong) | none | none | 2026-10-06 |
| T-003 | E-03 | Guideline tĩnh có rule ID: nạp tệp, API tra rule, màn xem | Nguyễn Đức Hà (@DucHa180104) | pending | none | none | none | 2026-10-06 |
| T-004 | E-04 | CVAT dev trong compose, nạp dữ liệu mẫu, adapter chỉ đọc + hash | Lê Duy Nam (@duy12345-6789) | pending | none | none | none | 2026-10-06 |
| T-005 | E-10 | GPU worker Detector Faster R-CNN BDD100K: freeze checksum, inference ra JSON | Nguyễn Xuân Việt Anh (@Vietanhhhhhh2003) | pending | none | none | none | 2026-10-06 |

## Task Details

Đợt 1 giao ngày 2026-10-06, hạn **01:30 ngày 2026-10-07**. Mỗi task làm trên nhánh riêng, mở PR vào `main`; PR cần comment `Đã xem và duyệt` của Trịnh Quang Trung hoặc Nguyễn Đức Hà (CR-102), PR của Nguyễn Đức Hà do Trịnh Quang Trung duyệt. Cập nhật trạng thái trong file riêng `.agent/execution/task-board-@<username>.md` (CR-100), không sửa file này.

### T-001

#### Record Metadata

- **Task ID**: `T-001`
- **Epic ID**: `E-01`
- **Title**: `Contract M13 v1: OpenAPI baseline, state machine, ADR lineage`
- **Owner**: `Trịnh Quang Trung (@toilatrung)`
- **Status**: `pending`
- **Created Date**: `2026-10-06`
- **Target Date**: `2026-10-07`
- **Priority**: `1`

#### Objective

Có contract đầu tiên để các nhánh khác sinh type và mock: OpenAPI baseline cho M-01/M-02, state machine Issue/QC Run/frame (có trạng thái "đang dở"), ADR lineage và neo issue.

#### Scope

##### Included

- OpenAPI baseline (drf-spectacular hoặc tệp YAML trong `docs/04-api/`) cho: auth/phiên, snapshot, QC Run, guideline rule, hàng đợi frame; hợp đồng lỗi 400/403/404/409/422 kèm code/message/request_id
- Bảng transition Issue, QC Run, frame theo SRS §5.3–5.5, thêm trạng thái frame "đang dở" (BLOCKER-008)
- ADR (decision record `accepted`): lineage qua revision bằng cvat_shape_id + namespace nguồn; neo issue cấu trúc/thủ công (BLOCKER-007)
- Ma trận actor/action/scope cho RBAC

##### Excluded

- Implementation chức năng của các epic khác

#### Preconditions

- [x] Parent epic status is `EPIC_IN_PROGRESS`.
- [x] Required context package is available.
- [x] Dependencies, approvals, and access are available.

#### Related Files

- **Context Package**: `.agent/execution/current-context-@toilatrung.md`
- **Parent Epic**: `.agent/planning/epics.md#e-01`
- **Decisions**: `.agent/governance/decisions/DEC-002.md`
- **Risks**: `none`
- **Blockers**: `none`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`

#### Acceptance Criteria

- [ ] OpenAPI hợp lệ (`manage.py spectacular --validate` hoặc trình validate OpenAPI) và frontend sinh được type (`npm run gen:api` hoặc từ tệp)
- [ ] Mỗi endpoint/transition có trích FR/BR/UC
- [ ] Hai ADR ghi thành decision record `accepted`
- [ ] Verification method is specified for each condition.

#### Verification Requirements

- **Automated Checks**: `make validate-kit; make check`
- **Manual Checks**: `Thành viên khác đọc contract trong PR`
- **Expected Evidence**: `.agent/reports/implementation/T-001-@toilatrung.md`

#### Completion Criteria

- [ ] Every acceptance criterion passes.
- [ ] Required reports are stored in `.agent/reports/`.
- [ ] Implementing commits are recorded in `.agent/intelligence/git-nexus/task-commit-map.md`.
- [ ] Current context and task board reflect the final status.

### T-002

#### Record Metadata

- **Task ID**: `T-002`
- **Epic ID**: `E-02`
- **Title**: `App shell frontend, đăng nhập, test runner frontend`
- **Owner**: `Trần Đức Thọ (@tdt2112)`
- **Status**: `pending`
- **Created Date**: `2026-10-06`
- **Target Date**: `2026-10-07`
- **Priority**: `1`

#### Objective

Frontend có test runner chạy trong `make check` và CI, app shell theo Design System và màn đăng nhập gọi API qua client sinh từ OpenAPI.

#### Scope

##### Included

- Chọn test runner frontend (gỡ một phần BLOCKER-014; DEC-001 ghi vitest từng lỗi npm peer-set — kiểm lại hoặc chọn công cụ khác), thêm `npm test`, đưa vào `make check` và job `frontend` của CI
- App shell: TopBar, FlowNav, ContextBar với class `lx-*`; `docs/design/` là mẫu tham khảo, không cần khớp pixel
- Màn đăng nhập/đăng xuất; guard route và ẩn menu theo vai trò; xử lý 401/403 chung
- Mock API theo contract T-001 khi backend auth chưa có

##### Excluded

- Màn nghiệp vụ; backend auth (E-02 backend)

#### Preconditions

- [x] Parent epic status is `EPIC_IN_PROGRESS`.
- [x] Required context package is available.
- [x] Dependencies, approvals, and access are available.

#### Related Files

- **Context Package**: `.agent/execution/current-context-@tdt2112.md`
- **Parent Epic**: `.agent/planning/epics.md#e-02`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md`
- **Risks**: `none`
- **Blockers**: `.agent/governance/blockers/BLOCKER-014.md`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`

#### Acceptance Criteria

- [ ] `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` pass; test chạy trong CI
- [ ] Có ít nhất một test component cho app shell hoặc màn đăng nhập
- [ ] Đăng nhập (mock) → vào shell; vai trò không đủ quyền không thấy menu tương ứng
- [ ] Verification method is specified for each condition.

#### Verification Requirements

- **Automated Checks**: `cd src/frontend && npm run lint && npm run typecheck && npm test && npm run build`
- **Manual Checks**: `Mở trang đăng nhập và shell trên trình duyệt, chụp màn hình vào report`
- **Expected Evidence**: `.agent/reports/implementation/T-002-@tdt2112.md`

#### Completion Criteria

- [ ] Every acceptance criterion passes.
- [ ] Required reports are stored in `.agent/reports/`.
- [ ] Implementing commits are recorded in `.agent/intelligence/git-nexus/task-commit-map.md`.
- [ ] Current context and task board reflect the final status.

### T-003

#### Record Metadata

- **Task ID**: `T-003`
- **Epic ID**: `E-03`
- **Title**: `Guideline tĩnh có rule ID: nạp tệp, API tra rule, màn xem`
- **Owner**: `Nguyễn Đức Hà (@DucHa180104)`
- **Status**: `pending`
- **Created Date**: `2026-10-06`
- **Target Date**: `2026-10-07`
- **Priority**: `2`

#### Objective

Workspace tra được rule theo rule ID từ guideline tĩnh nạp từ tệp (thay FR-GDL-01…03 theo CR-101), không dùng retrieval ngữ nghĩa (FR-GDL-04).

#### Scope

##### Included

- Định dạng tệp guideline (rule ID, section, trích đoạn, mapping nhóm lỗi/lớp → rule ID) và tệp mẫu cho 10 lớp BDD100K
- Django app + model + lệnh nạp tệp idempotent; API đọc rule theo ID và theo nhóm lỗi/lớp; kiểm quyền ở API
- Màn xem guideline chỉ đọc (frontend)
- Test backend

##### Excluded

- Versioning guideline và màn sửa (hoãn theo CR-101)

#### Preconditions

- [x] Parent epic status is `EPIC_IN_PROGRESS`.
- [x] Required context package is available.
- [x] Dependencies, approvals, and access are available.

#### Related Files

- **Context Package**: `.agent/execution/current-context-@ducha180104.md`
- **Parent Epic**: `.agent/planning/epics.md#e-03`
- **Decisions**: `.agent/governance/decisions/DEC-001.md`
- **Risks**: `none`
- **Blockers**: `none`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`

#### Acceptance Criteria

- [ ] Nạp tệp hai lần không tạo bản ghi trùng
- [ ] API trả rule theo ID và theo nhóm lỗi/lớp; ID không tồn tại trả 404 theo hợp đồng lỗi
- [ ] Màn xem hiển thị rule; `make check` pass
- [ ] Verification method is specified for each condition.

#### Verification Requirements

- **Automated Checks**: `make check`
- **Manual Checks**: `Gọi API và mở màn xem trên trình duyệt`
- **Expected Evidence**: `.agent/reports/implementation/T-003-@ducha180104.md`

#### Completion Criteria

- [ ] Every acceptance criterion passes.
- [ ] Required reports are stored in `.agent/reports/`.
- [ ] Implementing commits are recorded in `.agent/intelligence/git-nexus/task-commit-map.md`.
- [ ] Current context and task board reflect the final status.

### T-004

#### Record Metadata

- **Task ID**: `T-004`
- **Epic ID**: `E-04`
- **Title**: `CVAT dev trong compose, nạp dữ liệu mẫu, adapter chỉ đọc + hash`
- **Owner**: `Lê Duy Nam (@duy12345-6789)`
- **Status**: `pending`
- **Created Date**: `2026-10-06`
- **Target Date**: `2026-10-07`
- **Priority**: `1`

#### Objective

CVAT dev chạy được bằng một lệnh make, có một task mẫu chứa ảnh BDD100K và annotation người học, và adapter backend đọc (chỉ đọc) job/annotation rồi tính SHA-256 ổn định.

#### Scope

##### Included

- CVAT dev pin phiên bản (TBD-01) trong compose riêng hoặc `infrastructure/docker-compose.dev.yml`; lệnh make bật/tắt; tài liệu cài đặt
- Script ngoài LabelX nạp ảnh BDD100K mẫu + tệp annotation người học vào một task CVAT (quy ước tên/tag theo BLOCKER-018)
- Kiểm ảnh trong tệp người học thuộc BDD100K `val` hay `train`, ghi số lượng vào report (AS-03, leakage)
- Adapter chỉ đọc: liệt kê job, đọc annotation bbox, chuẩn hoá JSON, SHA-256 từng job; token ở backend; không có đường ghi
- Test adapter với dữ liệu ghi sẵn (không cần CVAT trong CI)

##### Excluded

- Model snapshot, drift, màn Snapshot (task sau của E-04)

#### Preconditions

- [x] Parent epic status is `EPIC_IN_PROGRESS`.
- [x] Required context package is available.
- [x] Dependencies, approvals, and access are available.

#### Related Files

- **Context Package**: `.agent/execution/current-context-@duy12345-6789.md`
- **Parent Epic**: `.agent/planning/epics.md#e-04`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `none`
- **Blockers**: `.agent/governance/blockers/BLOCKER-004.md, .agent/governance/blockers/BLOCKER-018.md`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`

#### Acceptance Criteria

- [ ] CVAT dev bật được bằng lệnh make, phiên bản được pin
- [ ] Đọc hai lần cùng dữ liệu cho cùng SHA-256; adapter không có hàm gọi API ghi
- [ ] Report ghi số ảnh val/train của tệp người học
- [ ] Verification method is specified for each condition.

#### Verification Requirements

- **Automated Checks**: `make check`
- **Manual Checks**: `Bật CVAT dev, nạp task mẫu, chạy adapter đọc và in hash`
- **Expected Evidence**: `.agent/reports/implementation/T-004-@duy12345-6789.md`

#### Completion Criteria

- [ ] Every acceptance criterion passes.
- [ ] Required reports are stored in `.agent/reports/`.
- [ ] Implementing commits are recorded in `.agent/intelligence/git-nexus/task-commit-map.md`.
- [ ] Current context and task board reflect the final status.

### T-005

#### Record Metadata

- **Task ID**: `T-005`
- **Epic ID**: `E-10`
- **Title**: `GPU worker Detector Faster R-CNN BDD100K: freeze checksum, inference ra JSON`
- **Owner**: `Nguyễn Xuân Việt Anh (@Vietanhhhhhh2003)`
- **Status**: `pending`
- **Created Date**: `2026-10-06`
- **Target Date**: `2026-10-07`
- **Priority**: `1`

#### Objective

Có môi trường chạy Detector Faster R-CNN R-50-FPN 3x (model zoo BDD100K) tách khỏi backend, checkpoint đã freeze bằng SHA-256, và lệnh inference trên ảnh mẫu xuất dự đoán JSON theo toạ độ pixel gốc.

#### Scope

##### Included

- Image/Dockerfile riêng cho GPU worker (MMDetection 2.x, mmcv-full) trong `infrastructure/`; chạy được cả CPU để thử
- Tải checkpoint `faster_rcnn_r50_fpn_3x_det_bdd100k.pth`, ghi SHA-256, version, mapping 10 lớp BDD100K
- Lệnh inference theo lô: đầu vào thư mục ảnh, đầu ra JSON (box pixel gốc, lớp, confidence)
- Đo thời gian/ảnh trên phần cứng đang có; ghi vào report làm đầu vào TBD-02 (BLOCKER-014)

##### Excluded

- Sinh candidate E1/E2, evidence, gọi từ QC Orchestrator (task sau của E-10)

#### Preconditions

- [x] Parent epic status is `EPIC_IN_PROGRESS`.
- [x] Required context package is available.
- [x] Dependencies, approvals, and access are available.

#### Related Files

- **Context Package**: `.agent/execution/current-context-@vietanhhhhhh2003.md`
- **Parent Epic**: `.agent/planning/epics.md#e-10`
- **Decisions**: `.agent/governance/decisions/DEC-003.md`
- **Risks**: `none`
- **Blockers**: `.agent/governance/blockers/BLOCKER-005.md, .agent/governance/blockers/BLOCKER-014.md`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`

#### Acceptance Criteria

- [ ] SHA-256 của checkpoint được ghi và kiểm lại khi nạp model (sai checksum thì từ chối chạy)
- [ ] Inference ≥ 10 ảnh BDD100K mẫu ra JSON đúng 10 lớp
- [ ] Report có thời gian/ảnh và cấu hình phần cứng đã dùng
- [ ] Verification method is specified for each condition.

#### Verification Requirements

- **Automated Checks**: `make check (phần backend không đổi); test kiểm checksum`
- **Manual Checks**: `Chạy lệnh inference trên thư mục ảnh mẫu`
- **Expected Evidence**: `.agent/reports/implementation/T-005-@vietanhhhhhh2003.md`

#### Completion Criteria

- [ ] Every acceptance criterion passes.
- [ ] Required reports are stored in `.agent/reports/`.
- [ ] Implementing commits are recorded in `.agent/intelligence/git-nexus/task-commit-map.md`.
- [ ] Current context and task board reflect the final status.
