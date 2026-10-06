---
id: epics-v1
title: Epics
type: planning
domain: governance
module: planning
tags: [epics, planning]
priority: 2
---
# Epics

## Purpose

Maintain the authoritative registry of bounded delivery outcomes that may be expanded into executable tasks.

## Status Model

- **Valid Statuses**: `EPIC_PROPOSED | EPIC_READY | EPIC_IN_PROGRESS | EPIC_BLOCKED | EPIC_DONE | EPIC_CANCELLED`

## Epic Records

| Epic ID | Milestone ID | Outcome | Owner | Status | Task IDs | Acceptance Evidence | Governance Links |
|---|---|---|---|---|---|---|---|
| `E-01` | `M-01` | **Hợp đồng triển khai M13, lineage và phép đo** — Có một contract duy nhất (entity, API, state machine, lỗi, engine interface, lineage, nối quyết định với reference) truy được tới FR/BR trước khi build. | `Trịnh Quang Trung` | `EPIC_IN_PROGRESS` | `T-001` | Xem [chi tiết](#e-01) | `BLOCKER-001, BLOCKER-003, BLOCKER-007, BLOCKER-009, BLOCKER-010, BLOCKER-012, DEC-002, DEC-003` |
| `E-02` | `M-01` | **Nền backend/frontend, auth, RBAC, audit, storage và CI** — Mọi epic nghiệp vụ dựng trên một nền chung: phiên đăng nhập, quyền theo scope, audit append-only cùng transaction, truy cập storage có kiểm soát, app shell Next.js và CI. | `Trịnh Quang Trung (frontend: Trần Đức Thọ)` | `EPIC_IN_PROGRESS` | `T-002` | Xem [chi tiết](#e-02) | `BLOCKER-003, BLOCKER-013, BLOCKER-014, DEC-002, DEC-003, CR-101` |
| `E-03` | `M-01` | **Guideline version và mapping rule** — Workspace tra được rule theo rule ID + version + section của snapshot, không dùng RAG. | `Nguyễn Đức Hà` | `EPIC_IN_PROGRESS` | `T-003` | Xem [chi tiết](#e-03) | `DEC-002, DEC-003, CR-101` |
| `E-04` | `M-02` | **CVAT adapter chỉ đọc và snapshot bất biến** — Tạo snapshot bất biến, có hash, phát hiện drift, từ CVAT thật mà không có đường ghi annotation. | `Lê Duy Nam (frontend: Trần Đức Thọ)` | `EPIC_IN_PROGRESS` | `T-004` | Xem [chi tiết](#e-04) | `BLOCKER-004, BLOCKER-020, DEC-002, DEC-003` |
| `E-05` | `M-02` | **Matching dùng chung, tất định** — Một thư viện matching một-một không phụ thuộc lớp dùng chung cho Detector–annotation, GT–annotation và GT–GT. | `Lê Duy Nam` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-05) | `BLOCKER-015, DEC-002, DEC-003` |
| `E-06` | `M-04` | **Công cụ reference: hai GT, phân xử, suy lỗi, khoá, leakage** — LabelX nhập hai bản GT độc lập, ghép, đưa bất đồng cho QA Lead phân xử, suy ra 𝓔, khoá version và chặn rò rỉ dữ liệu. | `Lê Duy Nam (frontend: Trần Đức Thọ)` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-06) | `BLOCKER-005, BLOCKER-013, BLOCKER-018, DEC-002, DEC-003, CR-101, BLOCKER-022` |
| `E-07` | `M-04` | **Bộ reference tập hiệu chỉnh đã khoá** — Có reference (GT + 𝓔) đã khoá cho tập hiệu chỉnh để chọn ngưỡng Detector, học score và chọn k*. | `Lê Duy Nam` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-07) | `BLOCKER-015, BLOCKER-016, BLOCKER-018, BLOCKER-020, DEC-002, DEC-003, CR-101, BLOCKER-022` |
| `E-08` | `M-02` | **QC Orchestrator, shard, aggregation và coverage ledger** — QC Run chạy theo shard, chịu được retry/worker chết, gộp candidate thành issue và ghi coverage đúng mẫu số. | `Trịnh Quang Trung (frontend: Trần Đức Thọ)` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-08) | `BLOCKER-003, BLOCKER-007, BLOCKER-014, DEC-002, DEC-003` |
| `E-09` | `M-02` | **Engine Schema/Taxonomy, Geometry, Duplicate/Overlap** — Ba engine xác định sinh cảnh báo cấu trúc và candidate E3 có evidence. | `Nguyễn Xuân Việt Anh` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-09) | `DEC-002, DEC-003` |
| `E-10` | `M-04` | **Detector baseline, candidate E1/E2 và evidence** — Một Detector baseline đã freeze chạy trên GPU worker sinh candidate E1/E2 kèm evidence; thiếu model thì Not checked. | `Nguyễn Xuân Việt Anh (frontend: Trần Đức Thọ)` | `EPIC_IN_PROGRESS` | `T-005` | Xem [chi tiết](#e-10) | `BLOCKER-005, BLOCKER-014, DEC-002, DEC-003, CR-101` |
| `E-11` | `M-02` | **Ranking, score_v0, giải thích, random slice và đối chứng** — Mọi frame có điểm và hạng tái lập, giải thích được, kèm lát ngẫu nhiên và ranking đối chứng. | `Nguyễn Xuân Việt Anh (frontend: Trần Đức Thọ)` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-11) | `BLOCKER-006, BLOCKER-007, BLOCKER-010, DEC-002, DEC-003` |
| `E-12` | `M-04` | **VLM tắt trong pilot (TBD-08)** — Thực hiện nhánh đã duyệt cho FR-ENG-10: VLM tắt trong pilot, có ghi nhận (DEC-002). | `Nguyễn Xuân Việt Anh` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-12) | `BLOCKER-002, DEC-002, DEC-003` |
| `E-13` | `M-03` | **Review Queues và lease nguyên tử** — Reviewer nhận frame theo hàng đợi, lease cấp nguyên tử trên PostgreSQL, self-review bị chặn ở backend. | `Nguyễn Đức Hà` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-13) | `BLOCKER-008, BLOCKER-013, DEC-002, DEC-003` |
| `E-14` | `M-03` | **Review Workspace, quyết định và effort log** — Reviewer xem ảnh, annotation, dự đoán, evidence, guideline và ra quyết định có lý do; effort ghi tự động. | `Nguyễn Đức Hà (frontend: Trần Đức Thọ)` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-14) | `BLOCKER-008, BLOCKER-009, BLOCKER-013, DEC-002, DEC-003, CR-101` |
| `E-15` | `M-03` | **Escalation, phân xử, Decision Case và Guideline Gap** — Issue chưa đủ căn cứ được QA Lead phân xử, lưu thành Decision Case có version. | `Nguyễn Đức Hà` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-15) | `DEC-002, DEC-003, CR-101` |
| `E-16` | `M-03` | **Rework, re-check, verify và QC run cuối** — Lỗi xác nhận được sửa trên CVAT, kiểm lại trên revision mới, và mọi báo cáo/gate trỏ QC run cuối. | `Trịnh Quang Trung (frontend: Trần Đức Thọ)` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-16) | `BLOCKER-007, BLOCKER-011, DEC-002, DEC-003, CR-101` |
| `E-17` | `M-04` | **Hiệu chỉnh score** — Score version được học và kiểm chứng ngoài fold trên tập hiệu chỉnh rồi khoá (Metric engine và pilot nhỏ hoãn theo CR-101). | `Nguyễn Xuân Việt Anh (frontend: Trần Đức Thọ)` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-17) | `BLOCKER-010, BLOCKER-015, BLOCKER-016, BLOCKER-021, DEC-002, DEC-003, CR-101` |
| `E-18` | `M-05` | **Reference held-out và D1/D2 đã khoá** — Reference độc lập, đã khoá cho tập held-out và dữ liệu thí nghiệm theo thiết kế được duyệt. | `Lê Duy Nam` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-18) | `BLOCKER-005, BLOCKER-015, BLOCKER-016, BLOCKER-017, BLOCKER-018, BLOCKER-019, BLOCKER-020, DEC-002, DEC-003, CR-101, BLOCKER-022` |
| `E-19` | `M-05` | **Preregistration và thí nghiệm crossover** — Thí nghiệm baseline/assisted chạy đúng thiết kế đã khoá trước. | `Nguyễn Đức Hà` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-19) | `BLOCKER-002, BLOCKER-015, BLOCKER-017, BLOCKER-018, BLOCKER-019, DEC-002, DEC-003, CR-101, BLOCKER-022` |
| `E-20` | `M-05` | **Đánh giá KPI-1, KPI-2 và guardrail** — KPI-1, KPI-2, KPI-2b, G-1…G-5 tính đúng phương pháp đã preregister, có provenance. | `Nguyễn Xuân Việt Anh (frontend: Trần Đức Thọ)` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-20) | `BLOCKER-006, BLOCKER-010, BLOCKER-012, BLOCKER-015, BLOCKER-021, DEC-002, DEC-003, CR-101, BLOCKER-022` |
| `E-21` | `M-05` | **Báo cáo hiệu quả và xuất PDF/CSV/JSON** — Báo cáo đủ cỡ mẫu, mẫu số, phương pháp, CI, provenance; random và risk tách riêng; xuất được. | `Trần Đức Thọ` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-21) | `BLOCKER-012, BLOCKER-013, DEC-002, DEC-003` |
| `E-22` | `M-05` | **Quality Gate tối thiểu và waiver** — Gate tính từng điều kiện trên run cuối, thiếu dữ liệu là chưa đạt, waiver có người duyệt khác người đề nghị. | `Nguyễn Đức Hà (frontend: Trần Đức Thọ)` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-22) | `BLOCKER-006, BLOCKER-011, DEC-002, DEC-003, CR-101, BLOCKER-022` |
| `E-23` | `M-06` | **Vận hành, đo NFR, retention và backup/restore** — Hệ thống chạy trên môi trường mục tiêu, NFR đo trên phần cứng thật, khôi phục được nhất quán. | `Trịnh Quang Trung` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-23) | `BLOCKER-014, DEC-002, DEC-003, CR-101` |
| `E-24` | `M-06` | **Nghiệm thu độc lập và bàn giao M13** — Bằng chứng nghiệm thu đầy đủ cho mọi Must + Should, AC-01…AC-11, R-01…R-07. | `Trịnh Quang Trung` | `EPIC_PROPOSED` | `none` | Xem [chi tiết](#e-24) | `BLOCKER-001, DEC-002, DEC-003` |

## Epic Details

Mỗi epic giữ cấu trúc của `.agent/templates/epic-template.md`. Không epic nào được mở rộng task khi còn `EPIC_PROPOSED`.

Quy tắc bổ sung theo `.agent/governance/decisions/DEC-002.md` (2026-10-06):

- **Ký epic**: một epic chỉ chuyển `EPIC_READY` khi Product Owner ghi chữ ký vào trường **PO Sign-off** (người, ngày) và mọi task của epic có developer được gán (BLOCKER-001).
- **Frontend thuộc phạm vi epic**: epic có màn hình gồm cả backend lẫn frontend (dòng `Frontend:` trong Included); epic chỉ xong khi màn hình chạy trên API thật.
- **Thiết kế tham khảo**: `docs/design/` (Design System và `screens/*.dc.html`) là thiết kế mẫu để tham khảo khi code frontend, không phải đặc tả pixel. Delta thiết kế bổ sung just-in-time ngay trước epic dùng tới: đăng nhập/audit trước E-02; hàng đợi frame + đóng góp điểm trước E-13; Workspace delta trước E-14; reference hai GT trước E-06; thí nghiệm và KPI trước E-19/E-20 (BLOCKER-013).

### E-01

#### Record Metadata

- **Epic ID**: `E-01`
- **Title**: `Hợp đồng triển khai M13, lineage và phép đo`
- **Owner**: `Trịnh Quang Trung`
- **Status**: `EPIC_IN_PROGRESS`
- **Milestone ID**: `M-01`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-07`
- **Priority**: `1`
- **PO Sign-off**: `Trịnh Quang Trung, 2026-10-06 — giao task đợt 1`

#### Objective

Có một contract duy nhất (entity, API, state machine, lỗi, engine interface, lineage, nối quyết định với reference) truy được tới FR/BR trước khi build.

#### Scope

##### Included

- OpenAPI baseline cho bảng endpoint SRS §9.3 và hợp đồng lỗi 400/403/404/409/422 kèm code/message/request_id
- Bảng transition/event/actor/guard của Issue, QC Run, frame (SRS §5.3–5.5, B-17)
- Engine interface chung: input, output, trạng thái công khai, applicability trong ledger (NFR-13, B-19)
- ADR theo DEC-002 (BLOCKER-007 phương án A): định danh đối tượng qua revision bằng cvat_shape_id + namespace nguồn, fallback matching chỉ để gợi ý; run cuối gặp lại cùng neo thì tạo issue mới liên kết issue gốc (FR-RWK-05…08)
- ADR theo DEC-002: neo issue cấu trúc (annotation, rule ID), issue thủ công (frame, vùng vẽ) (FR-AGG-03, FR-RNK-12)
- Bổ sung contract và SRS theo DEC-002: trạng thái frame "đang dở" (BLOCKER-008), FR-GTE-01 khi không rework (BLOCKER-011), báo cáo hai phần KPI/run cuối (BLOCKER-012)
- Contract nối quyết định Xác nhận lỗi ↔ phần tử 𝓔 cho KPI-2b (FR-EVL-13)
- Ma trận actor/action/scope chuẩn (FR-SEC-01, bảng RBAC)
- Frontend: OpenAPI baseline là nguồn sinh type cho frontend (`npm run gen:api`); bảng mã lỗi 400/403/404/409/422 ↔ thông báo UI dùng chung; không có màn riêng

##### Excluded

- Implementation chức năng (thuộc epic tương ứng)
- Tự chốt các tham số TBD

#### Dependencies

- **Depends On**: `none`
- **Blocked By**: `none`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `none`
- **Change Requests**: `none`
- **Screens (H)**: Main, ContextBarStates, WorkflowPermissions, AnalysisConfig, RulesThresholds

#### Acceptance Criteria

- [ ] Mọi endpoint/state/guard trong contract có trích FR/BR/UC
- [ ] Các ADR lineage/neo/KPI-2b có quyết định được duyệt (status accepted)
- [ ] Không còn mâu thuẫn contract ở BLOCKER-003/007/009/010/012 chưa có disposition
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-02

#### Record Metadata

- **Epic ID**: `E-02`
- **Title**: `Nền backend/frontend, auth, RBAC, audit, storage và CI`
- **Owner**: `Trịnh Quang Trung (frontend: Trần Đức Thọ)`
- **Status**: `EPIC_IN_PROGRESS`
- **Milestone ID**: `M-01`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-09`
- **Priority**: `1`
- **PO Sign-off**: `Trịnh Quang Trung, 2026-10-06 — giao task đợt 1`

#### Objective

Mọi epic nghiệp vụ dựng trên một nền chung: phiên đăng nhập, quyền theo scope, audit append-only cùng transaction, truy cập storage có kiểm soát, app shell Next.js và CI.

#### Scope

##### Included

- Auth phiên LabelX + CSRF giữa Next.js và DRF; identity mapping LabelX ↔ CVAT (FR-SEC-02)
- RBAC theo vai trò + scope dataset, kiểm mọi request (FR-SEC-01); tách người yêu cầu/duyệt, chặn cùng người nhiều tài khoản (FR-SEC-04); override Super Admin có lý do (FR-SEC-06)
- Audit log append-only, ghi cùng transaction (FR-SEC-05; NFR-08)
- Lớp Object Storage: upload blob theo hash nội dung trước, commit metadata sau (nền NFR-06)
- Log có cấu trúc kèm request_id (nền NFR-12); secret không vào log (NFR-07)
- Frontend shell theo Design System: TopBar, FlowNav, ContextBar, component lx-*, API client sinh từ OpenAPI, UI theo quyền (NFR-10)
- Chọn test runner frontend và đưa vào `make check`; CI chạy lint/typecheck/test
- Frontend: màn đăng nhập/đăng xuất (thiết kế bổ sung just-in-time trước E-02, BLOCKER-013); menu và hành động ẩn/khoá theo vai trò + scope; xử lý 401/403 toàn cục; test runner frontend kèm test component đầu tiên trong CI

##### Excluded

- Màn nghiệp vụ cụ thể (thuộc epic tương ứng)
- Màn xem audit FR-SEC-07 (hoãn theo CR-101)

#### Dependencies

- **Depends On**: `E-01`
- **Blocked By**: `BLOCKER-014`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `none`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`
- **Screens (H)**: Main, WorkflowPermissions, TopBar, FlowNav, NavigationMenu, ContextBarStates

#### Acceptance Criteria

- [ ] API ngoài scope trả 403 và có audit
- [ ] Không tồn tại API sửa/xoá audit; kiểm DB grant
- [ ] Người duyệt trùng người yêu cầu bị từ chối (FR-SEC-04)
- [ ] CI xanh với test backend + frontend
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-03

#### Record Metadata

- **Epic ID**: `E-03`
- **Title**: `Guideline version và mapping rule`
- **Owner**: `Nguyễn Đức Hà`
- **Status**: `EPIC_IN_PROGRESS`
- **Milestone ID**: `M-01`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-09`
- **Priority**: `1`
- **PO Sign-off**: `Trịnh Quang Trung, 2026-10-06 — giao task đợt 1`

#### Objective

Workspace tra được rule theo rule ID + version + section của snapshot, không dùng RAG.

#### Scope

##### Included

- Guideline tĩnh có rule ID, section, trích đoạn nạp từ tệp lúc khởi tạo; mapping nhóm lỗi/lớp → rule ID trong cùng tệp; API tra rule (thay FR-GDL-01…03 theo CR-101)
- Không retrieval ngữ nghĩa (FR-GDL-04)
- Frontend: ModelsGuidelines phần guideline (version, rule ID, section, trích đoạn) và RulesThresholds phần mapping nhóm lỗi/lớp → rule ID (QC Admin sửa, vai trò khác chỉ xem); component tra rule dùng lại ở Workspace (E-14)

##### Excluded

- Soạn/duyệt nội dung guideline (làm ở nơi soạn guideline)
- Guideline RAG (B-13)

#### Dependencies

- **Depends On**: `E-02`
- **Blocked By**: `none`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `RISK-008`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`
- **Screens (H)**: ModelsGuidelines, RulesThresholds

#### Acceptance Criteria

- [ ] Lookup trả đúng version gắn với snapshot
- [ ] Mapping không hợp lệ bị từ chối
- [ ] Rule tối thiểu cho 10 lớp BDD100K được nạp (AS-06, RK-08)
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-04

#### Record Metadata

- **Epic ID**: `E-04`
- **Title**: `CVAT adapter chỉ đọc và snapshot bất biến`
- **Owner**: `Lê Duy Nam (frontend: Trần Đức Thọ)`
- **Status**: `EPIC_IN_PROGRESS`
- **Milestone ID**: `M-02`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-09`
- **Priority**: `1`
- **PO Sign-off**: `Trịnh Quang Trung, 2026-10-06 — giao task đợt 1`

#### Objective

Tạo snapshot bất biến, có hash, phát hiện drift, từ CVAT thật mà không có đường ghi annotation.

#### Scope

##### Included

- Adapter chỉ đọc project/task/job/frame/annotation/media; token ở backend (FR-SNP-01, 02)
- Chuẩn hoá JSON, SHA-256 từng job và tổng (FR-SNP-03)
- Kiểm drift trước khoá (FR-SNP-04)
- Lưu ảnh + checksum, frame mapping, assignee, taxonomy/guideline version (FR-SNP-05)
- Bất biến + parent_snapshot (FR-SNP-06)
- Bỏ qua shape không phải bbox và đếm (FR-SNP-07)
- Deep link job/frame (FR-SNP-08)
- Ảnh chỉ trong storage nội bộ (NFR-09)
- Màn Snapshot, SnapshotHistory
- CVAT dev cùng phiên bản instance thật trong `infrastructure/docker-compose.dev.yml` để xây song song (BLOCKER-004 phương án B); kiểm lại trên instance thật trước nghiệm thu
- Frontend: Snapshot (chọn project/task/job, tạo snapshot, trạng thái hash/drift, số shape bị bỏ qua) và SnapshotHistory (danh sách, parent_snapshot, deep link CVAT)

##### Excluded

- Ghi annotation vào CVAT (B-18)
- Snapshot gia tăng (FR-SNP-09, thuộc E-16)

#### Dependencies

- **Depends On**: `E-02, E-03`
- **Blocked By**: `none`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `RISK-006`
- **Change Requests**: `none`
- **Screens (H)**: Snapshot, SnapshotHistory, Main

#### Acceptance Criteria

- [ ] AC-03: sửa annotation trong lúc tạo snapshot → không khoá, báo job drift
- [ ] Hai lần export không đổi cho cùng hash
- [ ] Không có code path gọi API ghi của CVAT (kiểm bằng test + review)
- [ ] Deep link mở đúng job/frame trên CVAT pin version
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-05

#### Record Metadata

- **Epic ID**: `E-05`
- **Title**: `Matching dùng chung, tất định`
- **Owner**: `Lê Duy Nam`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-02`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-13`
- **Priority**: `1`
- **PO Sign-off**: `pending`

#### Objective

Một thư viện matching một-một không phụ thuộc lớp dùng chung cho Detector–annotation, GT–annotation và GT–GT.

#### Scope

##### Included

- Lọc cạnh IoU < τ_m trước tối ưu; Hungarian tối đa số cặp rồi tổng IoU; phá hoà tất định; ghi ambiguous (SRS §3.4, FR-ENG-06)
- Có version thuật toán (BR-13)
- Frontend: không có màn riêng; kết quả matching hiển thị qua E-06 và E-14

##### Excluded

- Gọi kết quả matching là Precision/Recall (B-21)

#### Dependencies

- **Depends On**: `E-02`
- **Blocked By**: `BLOCKER-015`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `none`
- **Change Requests**: `none`
- **Screens (H)**: — (dùng trong Benchmark, ReviewWorkspace)

#### Acceptance Criteria

- [ ] Bộ test bao phủ sai lớp, unmatched, cụm trùng, hoà, ignore
- [ ] Cùng input cho cùng mapping (NFR-04)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-06

#### Record Metadata

- **Epic ID**: `E-06`
- **Title**: `Công cụ reference: hai GT, phân xử, suy lỗi, khoá, leakage`
- **Owner**: `Lê Duy Nam (frontend: Trần Đức Thọ)`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-04`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-15`
- **Priority**: `2`
- **PO Sign-off**: `pending`

#### Objective

LabelX nhập hai bản GT độc lập, ghép, đưa bất đồng cho QA Lead phân xử, suy ra 𝓔, khoá version và chặn rò rỉ dữ liệu.

#### Scope

##### Included

- Nhập GT là nhãn gốc BDD100K từ tệp, khoá theo checksum (FR-EVL-01 bản v1.1, CR-101)
- Nạp tệp annotation người học gán sẵn vào CVAT làm annotation cần review (TBD-04 phương án a, DEC-003)
- Người lập GT không xem ranking/score/candidate (FR-EVL-02, BR-10)
- Suy 𝓔 theo BR-01…07, sửa mapping thì suy lại (FR-EVL-03, BR-14)
- Khoá reference cùng GT/snapshot/mapping/τ_m/a_min/version (FR-EVL-04)
- Kiểm leakage: split theo video, training manifest Detector, case hiệu chỉnh (FR-EVL-05)
- Báo cáo ghi rõ nguồn GT là nhãn gốc BDD100K (BR-11 bản v1.1)
- Màn Benchmark, Calibration
- Checklist QC Admin tạo bản sao annotation hai nhánh thí nghiệm trên CVAT, quy ước tên/tag để adapter nhận diện (BLOCKER-018 phương án A)
- Frontend: Benchmark/Calibration phần reference — nhập GT BDD100K, suy 𝓔 để QA Lead duyệt, khoá version, cảnh báo leakage (thiết kế bổ sung just-in-time trước E-06); người lập GT không thấy ranking/score/candidate ở cả UI và API

##### Excluded

- Lập dữ liệu reference thực (E-07, E-18)

#### Dependencies

- **Depends On**: `E-04, E-05`
- **Blocked By**: `BLOCKER-022`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `RISK-002`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`
- **Screens (H)**: Benchmark, Calibration

#### Acceptance Criteria

- [ ] Khoá reference khi còn bất đồng → 422
- [ ] Không có thao tác xoá lỗi trực tiếp khỏi 𝓔
- [ ] Overlap held-out với training manifest chặn đánh giá
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-07

#### Record Metadata

- **Epic ID**: `E-07`
- **Title**: `Bộ reference tập hiệu chỉnh đã khoá`
- **Owner**: `Lê Duy Nam`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-04`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-16`
- **Priority**: `2`
- **PO Sign-off**: `pending`

#### Objective

Có reference (GT + 𝓔) đã khoá cho tập hiệu chỉnh để chọn ngưỡng Detector, học score và chọn k*.

#### Scope

##### Included

- Chọn ảnh/video tập hiệu chỉnh (TBD-03)
- GT là nhãn gốc BDD100K; QA Lead duyệt 𝓔 và khoá version (CR-101)
- Chuẩn bị bắt đầu sớm song song M-02/M-03 (RK-03)
- Frontend: dùng màn reference của E-06

##### Excluded

- Reference held-out và D1/D2 (E-18)

#### Dependencies

- **Depends On**: `E-06`
- **Blocked By**: `BLOCKER-015, BLOCKER-022`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `RISK-003`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`
- **Screens (H)**: Benchmark, Calibration

#### Acceptance Criteria

- [ ] Reference hiệu chỉnh khoá version với đủ provenance
- [ ] Tỉ lệ khớp hai GT được báo cáo
- [ ] Không người xác minh nào tự review annotation của mình (BR-12)
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-08

#### Record Metadata

- **Epic ID**: `E-08`
- **Title**: `QC Orchestrator, shard, aggregation và coverage ledger`
- **Owner**: `Trịnh Quang Trung (frontend: Trần Đức Thọ)`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-02`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-14`
- **Priority**: `1`
- **PO Sign-off**: `pending`

#### Objective

QC Run chạy theo shard, chịu được retry/worker chết, gộp candidate thành issue và ghi coverage đúng mẫu số.

#### Scope

##### Included

- Run provenance: snapshot, config, seed, version engine, artifact (FR-ENG-01)
- State machine run Queued/Running/Completed/Partial/Failed/Cancelled; cancel; retry-failed
- Candidate và Issue tách riêng, candidate bất biến (FR-AGG-01)
- Khoá idempotent theo shard (FR-AGG-02)
- Dedup theo dedup_key + policy version (FR-AGG-03)
- Ledger theo engine, không loại đơn vị lỗi khỏi mẫu số (FR-AGG-04)
- Trạng thái công khai Checked/Partial/Failed/Not checked/Running (FR-AGG-05)
- Candidate + evidence + ledger cùng transaction (FR-AGG-06; NFR-06)
- Retry có backoff, worker chết không mất kết quả (NFR-05)
- Metric hàng đợi/shard (NFR-12)
- Màn AnalysisConfig, ExecutionHistory
- Frontend: AnalysisConfig (chọn snapshot, engine, tạo run, huỷ, retry-failed) và ExecutionHistory (trạng thái run/shard, ledger theo engine, trạng thái công khai Checked/Partial/Failed/Not checked/Running, tự làm mới khi run đang chạy)

##### Excluded

- Engine cụ thể (E-09, E-10, E-12)

#### Dependencies

- **Depends On**: `E-04`
- **Blocked By**: `BLOCKER-014`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `none`
- **Change Requests**: `none`
- **Screens (H)**: AnalysisConfig, ExecutionHistory

#### Acceptance Criteria

- [ ] AC-01: hai run cùng input → hash nội dung chuẩn hoá giống hệt
- [ ] AC-02: ép lỗi shard rồi retry → số issue không đổi
- [ ] Ngắt giữa upload và commit không để metadata trỏ blob thiếu
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-09

#### Record Metadata

- **Epic ID**: `E-09`
- **Title**: `Engine Schema/Taxonomy, Geometry, Duplicate/Overlap`
- **Owner**: `Nguyễn Xuân Việt Anh`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-02`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-14`
- **Priority**: `1`
- **PO Sign-off**: `pending`

#### Objective

Ba engine xác định sinh cảnh báo cấu trúc và candidate E3 có evidence.

#### Scope

##### Included

- Schema/Taxonomy theo taxonomy version + thuộc tính bắt buộc (FR-ENG-02)
- Geometry: x1<x2, y1<y2, bounds dung sai 2 px, diện tích ≥ 24 px² (FR-ENG-03)
- Duplicate/Overlap IoU ≥ 0,85 sinh candidate E3 (FR-ENG-04)
- Frontend: tham số engine hiển thị trên AnalysisConfig/RulesThresholds; cảnh báo cấu trúc và candidate E3 kèm evidence trong ExecutionHistory

##### Excluded

- Kiểm độ khít biên (G-009 giữ Not checked, B-06)

#### Dependencies

- **Depends On**: `E-08`
- **Blocked By**: `none`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `none`
- **Change Requests**: `none`
- **Screens (H)**: AnalysisConfig, RulesThresholds, ExecutionHistory

#### Acceptance Criteria

- [ ] Bộ test theo từng rule ID
- [ ] Cảnh báo cấu trúc không tự thành lỗi KPI
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-10

#### Record Metadata

- **Epic ID**: `E-10`
- **Title**: `Detector baseline, candidate E1/E2 và evidence`
- **Owner**: `Nguyễn Xuân Việt Anh (frontend: Trần Đức Thọ)`
- **Status**: `EPIC_IN_PROGRESS`
- **Milestone ID**: `M-04`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-14`
- **Priority**: `2`
- **PO Sign-off**: `Trịnh Quang Trung, 2026-10-06 — giao task đợt 1`

#### Objective

Một Detector baseline đã freeze chạy trên GPU worker sinh candidate E1/E2 kèm evidence; thiếu model thì Not checked.

#### Scope

##### Included

- Freeze artifact/version/checksum, mapping 10 lớp BDD100K (FR-ENG-05): Faster R-CNN R-50-FPN 3x của model zoo BDD100K (BLOCKER-005); GPU worker dùng image riêng MMDetection 2.x; training manifest = BDD100K train
- Inference theo lô trên GPU worker, toạ độ pixel gốc (SRS §9.4)
- Candidate E1/E2 theo τ_E1, τ_E2 (FR-ENG-07)
- Evidence: box/lớp dự đoán, confidence, IoU, ambiguous, crop, rule (FR-ENG-08)
- Not checked khi không có Detector (FR-ENG-09)
- Code phụ thuộc E-05/E-08; nghiệm thu ngưỡng phụ thuộc E-07
- Frontend: ModelsGuidelines phần model (artifact, version, checksum, mapping 10 lớp — giá trị thật, không dùng số demo); trạng thái Not checked khi thiếu Detector

##### Excluded

- Classifier thứ hai (B-07)

#### Dependencies

- **Depends On**: `E-05, E-08, E-07`
- **Blocked By**: `BLOCKER-014`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `RISK-001`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`
- **Screens (H)**: ModelsGuidelines, AnalysisConfig, ExecutionHistory

#### Acceptance Criteria

- [ ] Chạy đủ mọi frame áp dụng, ledger đúng
- [ ] Ngưỡng có version, chọn trên tập hiệu chỉnh
- [ ] Không ranking giả khi thiếu model
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-11

#### Record Metadata

- **Epic ID**: `E-11`
- **Title**: `Ranking, score_v0, giải thích, random slice và đối chứng`
- **Owner**: `Nguyễn Xuân Việt Anh (frontend: Trần Đức Thọ)`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-02`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-14`
- **Priority**: `1`
- **PO Sign-off**: `pending`

#### Objective

Mọi frame có điểm và hạng tái lập, giải thích được, kèm lát ngẫu nhiên và ranking đối chứng.

#### Scope

##### Included

- s(f) cho mọi frame, kể cả không candidate (FR-RNK-01)
- Score version bất biến sau khoá (FR-RNK-02); tái lập (FR-RNK-03); phá hoà hash (FR-RNK-04)
- Lưu đóng góp n_i·q_i và h(f) (FR-RNK-05)
- Cờ thiếu bằng chứng (FR-RNK-06)
- Lát ngẫu nhiên r% (FR-RNK-07)
- Ranking đối chứng ngẫu nhiên/heuristic (FR-RNK-08)
- Neo + n_i theo bảng neo (FR-RNK-12)
- Chạy lại ranking khi có candidate E1/E2 từ E-10
- Frontend: component giải thích điểm (n_i·q_i, h(f), cờ thiếu bằng chứng) dùng lại ở E-13/E-14; AuditSampling cho lát ngẫu nhiên r%

##### Excluded

- Học tham số score (E-17)
- Biến thể s(f)/t̂(f) (FR-RNK-09, Could — backlog)

#### Dependencies

- **Depends On**: `E-09`
- **Blocked By**: `none`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `none`
- **Change Requests**: `none`
- **Screens (H)**: ReviewQueues, AuditSampling, AnalysisConfig

#### Acceptance Criteria

- [ ] Hash ranking giống hệt khi chạy lại (AC-01)
- [ ] Báo cáo ghi rõ đang dùng score_v0
- [ ] Random và risk lưu nguồn riêng
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-12

#### Record Metadata

- **Epic ID**: `E-12`
- **Title**: `VLM tắt trong pilot (TBD-08)`
- **Owner**: `Nguyễn Xuân Việt Anh`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-04`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-14`
- **Priority**: `2`
- **PO Sign-off**: `pending`

#### Objective

Thực hiện nhánh đã duyệt cho FR-ENG-10: VLM tắt trong pilot, có ghi nhận (DEC-002).

#### Scope

##### Included

- VLM tắt trong pilot (DEC-002, BLOCKER-002 phương án A): trạng thái disabled/Not checked đúng, không giả coverage
- Frontend: AnalysisConfig/ExecutionHistory hiển thị VLM disabled/Not checked; không có điều khiển bật VLM

##### Excluded

- Gửi ảnh ra dịch vụ ngoài khi chưa được phép (NFR-09)
- Pipeline VLM bật theo B-08 (để giai đoạn sau)

#### Dependencies

- **Depends On**: `E-09, E-10`
- **Blocked By**: `none`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `none`
- **Change Requests**: `none`
- **Screens (H)**: AnalysisConfig, ModelsGuidelines, ExecutionHistory

#### Acceptance Criteria

- [ ] Bằng chứng của đúng nhánh đã được Product Owner duyệt
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-13

#### Record Metadata

- **Epic ID**: `E-13`
- **Title**: `Review Queues và lease nguyên tử`
- **Owner**: `Nguyễn Đức Hà`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-03`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-15`
- **Priority**: `2`
- **PO Sign-off**: `pending`

#### Objective

Reviewer nhận frame theo hàng đợi, lease cấp nguyên tử trên PostgreSQL, self-review bị chặn ở backend.

#### Scope

##### Included

- Hàng đợi Theo rủi ro và Kiểm tra ngẫu nhiên, lọc (FR-REV-01, 02)
- Bắt đầu review cấp lease, bỏ qua self-review (FR-REV-03; FR-SEC-03)
- Lease hết hạn/gia hạn (FR-REV-04): một lease mỗi reviewer; hết hạn giữ quyết định đã lưu, frame về hàng đợi ở trạng thái "đang dở", ưu tiên reviewer cũ; thời hạn chốt sau đo pilot (BLOCKER-008 phương án A)
- Từ chối lưu khi lease hết/khác người (409) hoặc self-review (403) (FR-REV-14)
- Không hai reviewer cùng lease (NFR-15)
- Frontend: ReviewQueues theo frame — hai hàng đợi Theo rủi ro / Kiểm tra ngẫu nhiên, lọc, rank + đóng góp điểm (thiết kế bổ sung just-in-time trước E-13); nút Bắt đầu review cấp lease; nhãn frame "đang dở"; xử lý 409 (lease hết/khác người) và 403 (self-review)

##### Excluded

- Workspace (E-14)

#### Dependencies

- **Depends On**: `E-11`
- **Blocked By**: `none`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `RISK-005`
- **Change Requests**: `none`
- **Screens (H)**: ReviewQueues

#### Acceptance Criteria

- [ ] Kiểm thử đồng thời không cấp trùng frame
- [ ] AC-05: assignee gửi quyết định qua API bị từ chối, có audit
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-14

#### Record Metadata

- **Epic ID**: `E-14`
- **Title**: `Review Workspace, quyết định và effort log`
- **Owner**: `Nguyễn Đức Hà (frontend: Trần Đức Thọ)`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-03`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-16`
- **Priority**: `2`
- **PO Sign-off**: `pending`

#### Objective

Reviewer xem ảnh, annotation, dự đoán, evidence, guideline và ra quyết định có lý do; effort ghi tự động.

#### Scope

##### Included

- Canvas ảnh + box nét liền/nét đứt, bật/tắt lớp, zoom/pan (FR-REV-05)
- Issue Review và Frame Review (FR-REV-06)
- Panel evidence + trạng thái engine + guideline + case (FR-REV-07)
- Quyết định và validate (FR-REV-08)
- Issue thủ công (FR-REV-09)
- Quyết định + audit cùng transaction (FR-REV-10)
- Mở trong CVAT (FR-REV-12)
- Đã review xong (FR-REV-13)
- Effort log theo hoạt động, t_idle, event idempotent (FR-EVL-06)
- Đo NFR-01, NFR-02 bằng log
- Frontend: ReviewWorkspace — canvas ảnh (box nét liền/nét đứt, bật/tắt lớp, zoom/pan), panel evidence/trạng thái engine/guideline/case, form quyết định validate lý do, vẽ issue thủ công, phím tắt, Mở trong CVAT, gửi effort event idempotent; quyết định đã lưu không mất khi lease hết (thiết kế delta just-in-time trước E-14)

##### Excluded

- Phân xử (E-15)

#### Dependencies

- **Depends On**: `E-13, E-03`
- **Blocked By**: `none`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `RISK-004, RISK-005`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`
- **Screens (H)**: ReviewWorkspace

#### Acceptance Criteria

- [ ] AC-04: mọi candidate có evidence; không issue nào đóng/xác nhận mà thiếu quyết định của người
- [ ] Gửi lại effort event không cộng trùng
- [ ] Trạng thái có nhãn chữ, tương phản WCAG AA (NFR-10)
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-15

#### Record Metadata

- **Epic ID**: `E-15`
- **Title**: `Escalation, phân xử, Decision Case và Guideline Gap`
- **Owner**: `Nguyễn Đức Hà`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-03`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-16`
- **Priority**: `2`
- **PO Sign-off**: `pending`

#### Objective

Issue chưa đủ căn cứ được QA Lead phân xử, lưu thành Decision Case có version.

#### Scope

##### Included

- Danh sách escalation kèm quyết định từng reviewer (FR-ESC-01)
- Kết luận có rule/nhãn/lý do (FR-ESC-02)
- Người phân xử khác người chuyển cấp (FR-ESC-03)
- Decision Case có version (FR-ESC-04)
- Frontend: Escalations — danh sách kèm quyết định từng reviewer, form kết luận (rule/nhãn/lý do), Decision Case có version, ghi Guideline Gap; chặn người chuyển cấp tự phân xử

##### Excluded

- Soạn guideline mới

#### Dependencies

- **Depends On**: `E-14`
- **Blocked By**: `none`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `RISK-008`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`
- **Screens (H)**: Escalations

#### Acceptance Criteria

- [ ] Người chuyển cấp tự phân xử → 403
- [ ] Case tra được ở UC-12 đúng version
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-16

#### Record Metadata

- **Epic ID**: `E-16`
- **Title**: `Rework, re-check, verify và QC run cuối`
- **Owner**: `Trịnh Quang Trung (frontend: Trần Đức Thọ)`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-03`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-16`
- **Priority**: `2`
- **PO Sign-off**: `pending`

#### Objective

Lỗi xác nhận được sửa trên CVAT, kiểm lại trên revision mới, và mọi báo cáo/gate trỏ QC run cuối.

#### Scope

##### Included

- Yêu cầu sửa + deep link (FR-RWK-01)
- Annotator chỉ thấy việc của mình, báo Đã sửa (FR-RWK-02)
- Snapshot mới sau rework; revision không đổi → từ chối (FR-RWK-03); snapshot gia tăng FR-SNP-09 hoãn theo CR-101
- Re-check engine liên quan (FR-RWK-04)
- Verify bởi người khác annotator (FR-RWK-05)
- Snapshot toàn phạm vi + run cuối is_final (FR-RWK-06)
- Chuyển nguồn báo cáo/gate theo FR-RWK-08
- Frontend: danh sách rework tối thiểu (yêu cầu sửa + deep link, annotator chỉ thấy việc của mình và báo Đã sửa, verify bởi người khác; bảng theo dõi FR-RWK-07 hoãn); đánh dấu run cuối trên SnapshotHistory/ExecutionHistory

##### Excluded

- Ghi annotation vào CVAT

#### Dependencies

- **Depends On**: `E-15, E-08`
- **Blocked By**: `none`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `none`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`
- **Screens (H)**: ReworkTracking, SnapshotHistory, ExecutionHistory

#### Acceptance Criteria

- [ ] AC-06: issue chỉ Đã đóng sau verify trên revision mới; báo cáo trỏ run cuối
- [ ] Run gốc giữ nguyên
- [ ] Run cuối Partial/Failed → phạm vi chưa hoàn tất
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-17

#### Record Metadata

- **Epic ID**: `E-17`
- **Title**: `Hiệu chỉnh score`
- **Owner**: `Nguyễn Xuân Việt Anh (frontend: Trần Đức Thọ)`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-04`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-16`
- **Priority**: `2`
- **PO Sign-off**: `pending`

#### Objective

Score version được học và kiểm chứng ngoài fold trên tập hiệu chỉnh rồi khoá.

#### Scope

##### Included

- q_i logistic theo nhóm, h(f) Poisson (SRS §6.4.1)
- CV theo video: Brier, reliability (FR-RNK-10)
- Ablation, chọn version theo Recall@20% ngoài fold (FR-RNK-11)
- Frontend: Calibration (CV theo video, Brier, reliability, ablation, khoá score version) 

##### Excluded

- Học từ held-out (FR-EVL-05)
- Metric engine + Model Orchestrator (FR-EVL-15), đồng thuận reviewer G-3 (FR-EVL-16), pilot nhỏ (TBD-12) — hoãn theo CR-101; đặc tả tối thiểu giữ ở BLOCKER-021

#### Dependencies

- **Depends On**: `E-07, E-10, E-11, E-16`
- **Blocked By**: `BLOCKER-015`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `RISK-001`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`
- **Screens (H)**: Calibration, PerformanceEvaluation, ModelsGuidelines

#### Acceptance Criteria

- [ ] Score version khoá kèm kết quả ngoài fold và ablation
- [ ] Chưa đủ n_min thì giữ score_v0 và ghi rõ
- [ ] Báo cáo ghi rõ Metric engine, G-3 và pilot nhỏ hoãn theo CR-101
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-18

#### Record Metadata

- **Epic ID**: `E-18`
- **Title**: `Reference held-out và D1/D2 đã khoá`
- **Owner**: `Lê Duy Nam`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-05`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-16`
- **Priority**: `3`
- **PO Sign-off**: `pending`

#### Objective

Reference độc lập, đã khoá cho tập held-out và dữ liệu thí nghiệm theo thiết kế được duyệt.

#### Scope

##### Included

- Chọn held-out theo video, không giao tập hiệu chỉnh (EX-02); D1/D2 là hai nửa của held-out chia ngẫu nhiên theo video (BLOCKER-017 phương án A)
- GT nhãn gốc BDD100K, QA Lead duyệt và khoá; loại ảnh thuộc BDD100K train (AS-03 bản v1.1)
- Kiểm leakage trước đo (FR-EVL-05)
- Frontend: dùng màn reference của E-06 cho held-out; hiển thị chia D1/D2 theo video và kết quả kiểm leakage

##### Excluded

- Dùng held-out để hiệu chỉnh

#### Dependencies

- **Depends On**: `E-17`
- **Blocked By**: `BLOCKER-015, BLOCKER-022`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `RISK-002, RISK-003`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`
- **Screens (H)**: Benchmark

#### Acceptance Criteria

- [ ] Reference held-out/D1/D2 khoá version
- [ ] Kết quả kiểm leakage lưu cùng reference
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-19

#### Record Metadata

- **Epic ID**: `E-19`
- **Title**: `Preregistration và thí nghiệm crossover`
- **Owner**: `Nguyễn Đức Hà`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-05`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-23`
- **Priority**: `3`
- **PO Sign-off**: `pending`

#### Objective

Thí nghiệm baseline/assisted chạy đúng thiết kế đã khoá trước.

#### Scope

##### Included

- Khoá preregistration (SRS §7.3): Detector, score, reference, ngưỡng KPI, thí nghiệm
- Tạo thí nghiệm, gán AB/BA, khoá quy tắc dừng/δ/cỡ mẫu (FR-EVL-11); cỡ mẫu theo nguồn lực ≥ 4 reviewer ngoài, khoá preregistration 2026-10-19 (TBD-12 bản v1.1); thí nghiệm chạy 2026-10-20…23
- Nhánh baseline ẩn ranking/score/evidence (FR-EVL-12)
- Bản sao annotation riêng mỗi nhánh (EX-03)
- Chống carryover (EX-08); buổi làm quen (NFR-11)
- Người phân xử thí nghiệm khác người phân xử GT (BLOCKER-019 phương án A)
- Frontend: màn thí nghiệm/preregistration (thiết kế bổ sung just-in-time trước E-19) — tạo thí nghiệm, gán AB/BA, khoá preregistration (chỉ đọc sau khoá); ReviewWorkspace chế độ baseline ẩn ranking/score/evidence

##### Excluded

- Đổi tham số sau khi thấy kết quả (RK-09)

#### Dependencies

- **Depends On**: `E-18, E-16`
- **Blocked By**: `BLOCKER-015, BLOCKER-022`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `RISK-004, RISK-009`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`
- **Screens (H)**: PerformanceEvaluation, AuditSampling, ReviewWorkspace

#### Acceptance Criteria

- [ ] Mọi mục preregistration khoá version trước đợt 1
- [ ] Baseline không lộ evidence (kiểm UI + API)
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-20

#### Record Metadata

- **Epic ID**: `E-20`
- **Title**: `Đánh giá KPI-1, KPI-2 và guardrail`
- **Owner**: `Nguyễn Xuân Việt Anh (frontend: Trần Đức Thọ)`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-05`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-26`
- **Priority**: `3`
- **PO Sign-off**: `pending`

#### Objective

KPI-1, KPI-2, KPI-2b, G-1…G-5 tính đúng phương pháp đã preregister, có provenance.

#### Scope

##### Included

- Recall@k, slice, recall theo frame (FR-EVL-07, 08)
- Cluster bootstrap ≥ 1000, đối chứng ≥ 1000 seed (FR-EVL-09)
- E_min (FR-EVL-10)
- T_A, T_B, KPI-2, KPI-2b, ρ, non-inferiority, mixed model, độ nhạy (FR-EVL-13)
- Provenance evaluation run (FR-EVL-14; NFR-14)
- Frontend: PerformanceEvaluation phần KPI (Recall@k, slice, KTC, KPI-2, KPI-2b, non-inferiority, G-1…G-5) — hiển thị "không đủ mẫu"/Not checked, không hiển thị 0% (thiết kế bổ sung just-in-time trước E-20)

##### Excluded

- Đổi ngưỡng sau khi thấy kết quả

#### Dependencies

- **Depends On**: `E-19`
- **Blocked By**: `BLOCKER-015, BLOCKER-022`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `RISK-001, RISK-002, RISK-004, RISK-005, RISK-007, RISK-009, RISK-010`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`
- **Screens (H)**: PerformanceEvaluation

#### Acceptance Criteria

- [ ] AC-08, AC-09 đánh giá được với TBD-K1…K4 đã chốt
- [ ] |𝓔| < E_min ghi "không đủ mẫu"
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-21

#### Record Metadata

- **Epic ID**: `E-21`
- **Title**: `Báo cáo hiệu quả và xuất PDF/CSV/JSON`
- **Owner**: `Trần Đức Thọ`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-05`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-26`
- **Priority**: `3`
- **PO Sign-off**: `pending`

#### Objective

Báo cáo đủ cỡ mẫu, mẫu số, phương pháp, CI, provenance; random và risk tách riêng; xuất được.

#### Scope

##### Included

- FR-RPT-01…06
- Phân biệt lineage KPI (snapshot đầu vào) với báo cáo/gate revision cuối
- Frontend: QualityReport hai phần (KPI theo snapshot đầu vào; chất lượng/gate theo run cuối), ghi rõ nguồn từng phần; xuất PDF/CSV/JSON

##### Excluded

- Release History, Dashboard (ngoài phạm vi)

#### Dependencies

- **Depends On**: `E-20, E-16`
- **Blocked By**: `none`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `none`
- **Change Requests**: `none`
- **Screens (H)**: QualityReport, PerformanceEvaluation

#### Acceptance Criteria

- [ ] AC-10
- [ ] Chỉ số thiếu dữ liệu không hiển thị 0% hay đạt (FR-RPT-03)
- [ ] Tệp xuất ghi version snapshot/run/score/reference
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-22

#### Record Metadata

- **Epic ID**: `E-22`
- **Title**: `Quality Gate tối thiểu và waiver`
- **Owner**: `Nguyễn Đức Hà (frontend: Trần Đức Thọ)`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-05`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-26`
- **Priority**: `3`
- **PO Sign-off**: `pending`

#### Objective

Gate tính từng điều kiện trên run cuối, thiếu dữ liệu là chưa đạt, waiver có người duyệt khác người đề nghị.

#### Scope

##### Included

- Năm điều kiện pilot (FR-GTE-01); G-3 hiển thị Not checked vì FR-EVL-16 hoãn (CR-101), chỉ đạt qua waiver
- Thiếu dữ liệu = chưa đạt (FR-GTE-02)
- Waiver chỉ cho coverage và đồng thuận reviewer; không waiver lỗi nghiêm trọng chưa đóng hay rework chưa verify; không rework thì run gốc Completed là run cuối (FR-GTE-03; BLOCKER-011 phương án A)
- G-4: lát ngẫu nhiên trên snapshot run cuối, đạt khi cận trên KTC 95% ≤ 5% (BLOCKER-006 phương án A)
- Không phát hành dataset (FR-GTE-04)
- Frontend: QualityGate — từng điều kiện kèm nguồn dữ liệu và trạng thái; form waiver chỉ cho coverage và đồng thuận reviewer; người duyệt khác người đề nghị

##### Excluded

- Phát hành dataset đầy đủ

#### Dependencies

- **Depends On**: `E-20, E-16`
- **Blocked By**: `BLOCKER-022`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `none`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`
- **Screens (H)**: QualityGate, RulesThresholds

#### Acceptance Criteria

- [ ] AC-07: engine Not checked/Failed → gate không đạt
- [ ] Waiver hết hạn → điều kiện trở lại chưa đạt
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-23

#### Record Metadata

- **Epic ID**: `E-23`
- **Title**: `Vận hành, đo NFR, retention và backup/restore`
- **Owner**: `Trịnh Quang Trung`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-06`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-23`
- **Priority**: `3`
- **PO Sign-off**: `pending`

#### Objective

Hệ thống chạy trên môi trường mục tiêu, NFR đo trên phần cứng thật, khôi phục được nhất quán.

#### Scope

##### Included

- Triển khai app/CPU/GPU/data (TBD-02), HTTPS, secrets (NFR-07)
- Đo NFR-01…03 và chốt TBD-13
- Retry/backoff TBD-14; GC blob t_gc (NFR-06, TBD-20)
- Retention audit (NFR-08, TBD-15)
- Backup PostgreSQL + Object Storage versioning, diễn tập restore, RPO/RTO (NFR-16, TBD-17)
- Dashboard vận hành (NFR-12)
- Frontend: build production Next.js sau HTTPS, cấu hình qua biến môi trường, không lộ secret; đo NFR-01…03 phía trình duyệt cùng backend

##### Excluded

- Dùng compose dev làm production

#### Dependencies

- **Depends On**: `E-20`
- **Blocked By**: `BLOCKER-014`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `none`
- **Change Requests**: `.agent/governance/change-requests/CR-101.md`
- **Screens (H)**: —

#### Acceptance Criteria

- [ ] Restore khôi phục nhất quán snapshot/ảnh/evidence/quyết định/reference/effort
- [ ] NFR có ngưỡng đã duyệt mới dùng pass/fail
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

### E-24

#### Record Metadata

- **Epic ID**: `E-24`
- **Title**: `Nghiệm thu độc lập và bàn giao M13`
- **Owner**: `Trịnh Quang Trung`
- **Status**: `EPIC_PROPOSED`
- **Milestone ID**: `M-06`
- **Created Date**: `2026-10-05`
- **Target Date**: `2026-10-27`
- **Priority**: `3`
- **PO Sign-off**: `pending`

#### Objective

Bằng chứng nghiệm thu đầy đủ cho mọi Must + Should, AC-01…AC-11, R-01…R-07.

#### Scope

##### Included

- Tổng hợp evidence, review, QA cho từng yêu cầu
- Báo cáo nghiệm thu, runbook, version cấu hình
- Disposition cho Could (FR-RNK-09 backlog)
- Frontend: kiểm thử e2e luồng chính (snapshot → run → hàng đợi → workspace → rework → báo cáo/gate) làm bằng chứng nghiệm thu

##### Excluded

- Đổi ngưỡng hoặc học từ held-out để biến kết quả thành đạt

#### Dependencies

- **Depends On**: `E-12, E-21, E-22, E-23`
- **Blocked By**: `none`

#### Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `.agent/governance/decisions/DEC-001.md, .agent/governance/decisions/DEC-002.md, .agent/governance/decisions/DEC-003.md`
- **Risks**: `RISK-009, RISK-010`
- **Change Requests**: `none`
- **Screens (H)**: Toàn bộ màn trong SRS bảng 9.1

#### Acceptance Criteria

- [ ] Mọi AC đạt hoặc có disposition được duyệt
- [ ] Không còn blocker bắt buộc mở
- [ ] Frontend: màn trong Screens (H) chạy trên API thật (không dữ liệu giả), đúng quyền theo vai trò, có test frontend trong CI; giao diện tham khảo `docs/design/` (không yêu cầu khớp pixel)
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

#### Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

#### Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

## Forbidden Actions

- Do not expand tasks while status is `EPIC_PROPOSED`.
- Do not mark the epic `EPIC_DONE` with unmet acceptance criteria.
- Do not change baselined scope without an approved change request.
- Do not record fabricated links, evidence, or completion state.
