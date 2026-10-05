---
id: architecture-decisions
title: Quyết định kiến trúc B-01…B-21 và DEC-001
type: reference
domain: architecture
module: quality-control
tags: [architecture, decisions, adr, mvp]
priority: 1
---
# Quyết định kiến trúc

## Mục đích

Tài liệu này ghi lại các quyết định kiến trúc đã chốt cho module Quality Control (QC) của LabelX. Nguồn chính là bản rà soát [architecture_review.html](../00-project/sources/architecture_review.html) (gọi là **nguồn R**). Người dùng đã chốt 21/21 mục vào ngày 05/10/2026: 20 mục chọn phương án A, riêng B-05 chọn phương án B. Tài liệu cũng ghi stack đã chốt trong [DEC-001](../../.agent/governance/decisions/DEC-001.md).

Quy ước:

- "Đã chốt" nghĩa là đã chọn hướng thiết kế. Nó **không** có nghĩa là tính năng đã được triển khai hay đã đạt nghiệm thu (nguồn: R mục 1, mục 7).
- Cột "Hệ quả" nêu ràng buộc mà thiết kế, mã nguồn và kiểm thử phải tuân theo. Mỗi hệ quả kèm mã yêu cầu SRS liên quan nếu có.
- Các tên nguồn: H là các màn hình `docs/design/screens`; A là `docs/00-project/sources/Quality_Control_Review_UX_Architecture.html`; T là `docs/00-project/sources/QC_Engine_Review_Report.html`; L là `docs/00-project/sources/mermaid-diagram.png`. SRS là bộ tài liệu LaTeX trong [docs/label-x_system-requirement-specification](../label-x_system-requirement-specification/main.tex).

## DEC-001 — Stack MVP

| Hạng mục | Lựa chọn | Nguồn |
|---|---|---|
| Backend | Django 5.2 LTS, Django REST framework, drf-spectacular (OpenAPI), kiến trúc modular monolith | DEC-001; R cấu hình MVP "Backend"; L khối "Django / DRF - Modular Monolith" |
| Worker | Celery 5 + Redis 7 (broker/result), django-celery-beat; worker kiểm xác định và worker model tách khỏi API | DEC-001; R B-01 |
| CSDL | PostgreSQL 17 | DEC-001; [docker-compose.dev.yml](../../infrastructure/docker-compose.dev.yml) |
| Lưu blob | Object Storage S3-compatible qua django-storages; dev local dùng SeaweedFS | DEC-001; compose |
| Frontend | Next.js 16, React 19, TypeScript, TanStack Query; type sinh từ OpenAPI | DEC-001 |
| Runtime | Python 3.12 (uv); Node từ 22 trở lên | DEC-001; [pyproject.toml](../../src/backend/pyproject.toml) |

R cho phép ngoại lệ giữ FastAPI nếu đã có backend FastAPI chạy ổn định. Ngoại lệ này **không áp dụng**. Lý do: *tại thời điểm ra DEC-001*, repository chưa có backend nào (nguồn: DEC-001, "Rationale"). Hiện repository đã có scaffold Django ở `src/backend` theo DEC-001 (cấu hình `config/`, chưa có app nghiệp vụ). A §20.1 đề xuất FastAPI, SQLAlchemy và Alembic. Đề xuất đó bị thay bằng Django ORM và Django migrations.

## Bảng B-01…B-21

| Mã | Vấn đề | Phương án chọn | Hệ quả bắt buộc cho thiết kế |
|---|---|---|---|
| B-01 | Có sơ đồ thành phần nhưng backend và hợp đồng chưa được xác nhận với H | **A**: modular monolith + worker pool; chốt schema/API chung | Một ứng dụng Django gồm nhiều app theo module. Engine chạy trong Celery worker, không chạy trong request API. Hợp đồng duy nhất là OpenAPI do drf-spectacular sinh ra (SRS ch.10). |
| B-02 | Chưa chốt cách tạo revision và snapshot nhất quán từ CVAT | **A**: export từng job, chuẩn hoá, hash, kiểm lại trước khi khoá, lưu ảnh và metadata | Mỗi job có hash SHA-256 của JSON chuẩn hoá, kèm một hash tổng. Trước khi khoá, hệ thống đọc lại `updated_date` của job; nếu có drift thì không khoá. Ảnh được lưu kèm checksum (FR-SNP-03…05). |
| B-03 | Rework tạo revision mới nhưng chưa rõ revision nào được phát hành | **A**: tạo snapshot và QC Run cuối trên revision đã sửa, liên kết các verification trước đó | Thêm cờ `qc_run.is_final`. Báo cáo và gate chỉ trỏ run cuối khi run đó Completed và coverage đạt. Run gốc giữ nguyên để kiểm toán (FR-RWK-06, FR-RWK-08, FR-RPT-06). |
| B-04 | T có công thức coverage, nhưng eligibility và gate của H chưa được ánh xạ | **A**: coverage theo từng engine, mẫu số là các đơn vị áp dụng | Ledger lưu riêng từng engine. Đơn vị lỗi không bị loại khỏi mẫu số. Coverage chung chỉ dùng để xem tiến độ (FR-AGG-04, FR-RPT-04). |
| B-05 | Metric chưa chạy nhưng báo cáo vẫn hiện độ chính xác | **B**: khối đánh giá engine riêng, tính metric trên reference theo B-20; Model Orchestrator tổng hợp | Có bảng `evaluation_run` lưu provenance. Khi thiếu reference, trạng thái là Not checked, không bao giờ hiện 0% hay pass. Không dùng model làm trọng tài (FR-EVL-14, FR-EVL-15, FR-RPT-03). |
| B-06 | Geometry được gọi là kiểm xác định nhưng có rule cần biết biên vật thể | **A**: Geometry tự động chỉ kiểm cấu trúc, bounds và diện tích | Kiểm `x1<x2`, `y1<y2`, bounds với dung sai 2 px, diện tích từ 24 px² trở lên (G-014). G-009 luôn là Not checked (FR-ENG-03). |
| B-07 | Chưa chốt dùng một hay hai mô hình độc lập | **A**: pilot Detector trước | Chỉ dùng một Detector baseline đã freeze (artifact, version, checksum, mapping lớp). Classifier không bật mặc định. Nếu không có Detector thì engine là Not checked (FR-ENG-05, FR-ENG-09). |
| B-08 | Chạy song song chưa xử lý phụ thuộc candidate của VLM | **A**: pipeline candidate → chọn theo policy → worker kiểm chọn lọc | Nếu bật: tối đa 400 candidate mỗi run, tối đa 3 lần thử mỗi lượt (đã gồm retry). Hết hạn mức thì ghi "chưa kiểm". Pilot M13 đề xuất **không bật** VLM (TBD-08; FR-ENG-10). |
| B-09 | T đưa Temporal / Track trở lại phạm vi | **A**: không kiểm tự động trong giai đoạn đầu | Không có engine temporal. Lỗi track chỉ do người review ghi nhận. Ngoài phạm vi MVP. |
| B-10 | Chạy lại và gộp issue chưa có khoá, provenance và lifecycle | **A**: Candidate và Issue tách riêng, retry idempotent, dedup theo scope/object/family và policy version | Khoá idempotent của đơn vị xử lý là `(snapshot, engine, config, model, shard)`. `dedup_key` là `(snapshot, frame, đối tượng, nhóm lỗi)`. Candidate không sửa được sau khi ghi (FR-AGG-01…03). |
| B-11 | Waiver lỗi nghiêm trọng và Rework được mở rộng nhưng chưa có guard | **A**: giữ scope waiver của H, nhưng mỗi điều kiện phải có policy; người duyệt khác người yêu cầu; bắt buộc lý do, hạn và evidence | Có CHECK `approved_by <> requested_by`. Waiver chỉ có hiệu lực sau khi duyệt. Hết hạn thì điều kiện trở lại "chưa đạt" (FR-GTE-03, FR-SEC-04). |
| B-12 | Tách nhiệm vụ và audit transaction chưa được tái xác nhận | **A**: scope quyền, assignee tại snapshot, tách người yêu cầu và người duyệt, audit append-only cùng transaction | Backend kiểm quyền trên mọi endpoint. Self-review được xác định theo assignee tại snapshot. Audit ghi trong cùng transaction với thao tác. Token CVAT chỉ nằm ở backend (FR-SEC-01…06). |
| B-13 | L và T có RAG nhưng H chưa chốt cơ chế tra cứu guideline | **A**: tra cứu trực tiếp theo rule ID + guideline version + section, cộng case đã duyệt | Không dùng retrieval ngữ nghĩa, Vector Index hay pgvector trong MVP (FR-GDL-04). RAG để sau MVP. |
| B-14 | Pilot có chỉ số nhưng chưa có ngưỡng chứng minh | **A**: chạy một pilot đại diện, đo baseline thủ công rồi mới đặt tiêu chí | Không tự đặt ngưỡng accuracy hay năng suất. Timeout, retry và budget lấy từ phép đo pilot (TBD-13, TBD-14). |
| B-15 | Quality Gate chưa phản ánh ngưỡng audit và reviewer | **A**: mỗi ngưỡng là một gate riêng, có nguồn, scope, cỡ mẫu và tiêu chí đủ dữ liệu | Có các bảng `gate_check` riêng theo điều kiện. Thiếu dữ liệu thì "chưa đạt" (FR-GTE-01, FR-GTE-02). |
| B-16 | Diff/pre-label và các feature mở rộng chưa được ánh xạ vào H | **A**: ánh xạ feature vào sáu engine/module của H | Diff, profile camera, Vehicle plausibility và Feedback loop **ngoài phạm vi MVP**. MVP chỉ làm ảnh + Bounding box. |
| B-17 | Sơ đồ chưa có trạng thái, actor và nhánh huỷ | **A**: chốt bảng transition/event/actor/guard dùng trạng thái của H | Dùng state machine trong SRS §5 (bảng `tab:transitions`). Chuyển trạng thái không có trong bảng thì trả 409. |
| B-18 | Writeback annotation trong T vượt ranh giới "chỉ sửa trên CVAT" | **A**: adapter chỉ đọc, sửa qua deep link sang CVAT | Không có đường gọi nào ghi annotation lên CVAT. Mirror issue/comment chỉ làm khi API và quyền đã được xác minh, và không thuộc MVP (FR-SNP-01, FR-SNP-08). |
| B-19 | NOT_REQUIRED, abstain, exception chưa ánh xạ trạng thái hiển thị của H | **A**: giữ trạng thái công khai của H | Trạng thái công khai gồm Checked, Partial, Failed, Not checked, Running. Lý do áp dụng (`disabled`, `no_model`, `no_reference`, `not_applicable`, `not_triggered`) lưu riêng trong ledger (FR-AGG-05, SRS `tab:enginestates`). |
| B-20 | Đo recall/precision ở giai đoạn B nhưng Ground Truth giao ở giai đoạn C | **A**: chuẩn bị một reference đã duyệt trước khi đo | Reference phải được khoá (GT, mapping, ngưỡng, version thuật toán) trước khi đo. QA Lead chịu trách nhiệm (FR-EVL-01…05). |
| B-21 | Matching (không cần GT) bị gộp với Metric (cần GT) | **A**: matching là một bước của Mô hình độc lập để sinh candidate | Matching một-một, không xét lớp. Kết quả là association, không phải Precision/Recall (FR-ENG-06, SRS §3 "Matching"). |

## Cấu hình MVP đã chốt (sáu mục)

Nguồn: R mục 7, "Cấu hình MVP đã chốt".

| Mục | Phương án | Còn mở |
|---|---|---|
| Backend | Django + DRF, PostgreSQL, Celery + Redis, Object Storage hiện có | Cấu hình phần cứng — TBD-02 |
| CVAT | Giữ phiên bản đang triển khai; adapter chỉ đọc; deep link; polling có checkpoint nếu không có webhook | Phiên bản pin, URL, quyền token — TBD-01 |
| Taxonomy/shape | Ảnh + Bounding box; khoá taxonomy và guideline version | Danh sách ảnh và N — TBD-03; nguồn annotation — TBD-04 |
| Model | Một Detector baseline đã freeze, bảng mapping lớp | Artifact thật, ngưỡng `τ` — TBD-05 |
| Required units | Ledger theo engine: Schema/Geometry theo annotation; Duplicate theo frame/cặp; Detector theo frame; VLM theo candidate được trigger; Metric theo scope reference | — |
| Gate/pilot | Coverage 95%; critical chưa đóng = 0; rework verify 100%; residual tối đa 5%; reviewer agreement tối thiểu 90% (cấu hình khởi điểm pilot, chưa phải cam kết nghiệm thu) | Ngưỡng KPI — TBD-K1…K4 |

## Mục tiêu kiểm chứng R-01…R-07

| Mã | Mục tiêu | Yêu cầu SRS chính |
|---|---|---|
| R-01 | Tái lập kết quả trên dữ liệu đã khoá; retry không tạo issue trùng | FR-SNP-03…06, FR-ENG-01, FR-AGG-02, FR-AGG-06, FR-RNK-03 |
| R-02 | Candidate có evidence, người review ra quyết định | FR-ENG-08, FR-REV-07…10, FR-ESC-01…04 |
| R-03 | Verify và phát hành đúng revision đã sửa | FR-RWK-01…08 |
| R-04 | Đo chất lượng đúng reference và mẫu | FR-EVL-01…05, FR-EVL-14, FR-RPT-01…03 |
| R-05 | Phân quyền và audit đầy đủ | FR-SEC-01…07, FR-REV-14 |
| R-06 | Coverage/Gate phản ánh phần chưa kiểm | FR-AGG-04, FR-AGG-05, FR-RNK-06, FR-GTE-01…02 |
| R-07 | Hiệu quả review có căn cứ | FR-EVL-06, FR-EVL-11…13 |

(nguồn: R mục 3; SRS `tab:trace` trong [11-traceability.tex](../label-x_system-requirement-specification/sections/11-traceability.tex))

## Nội dung nguồn A/T bị loại hoặc hoãn

Các mục sau **không phải yêu cầu MVP**. Không được triển khai nếu chưa có quyết định mới.

| Nội dung | Nguồn đề xuất | Lý do loại hoặc hoãn |
|---|---|---|
| FastAPI, SQLAlchemy, Alembic | A §20.1 | DEC-001 chọn Django |
| Guideline RAG, pgvector, Vector Index | A §20, L, T §3 | B-13, FR-GDL-04 |
| Temporal / Track engine | T §3–4 | B-09 |
| Diff Engine, pre-label review, Vehicle plausibility, Specialized Classifier | T §3–4 | B-16, B-07 |
| Annotation writeback lên CVAT | T §6 | B-18 |
| Release, Manifest, Revoke, Release History | A §23.2, §25; H ReleaseHistory | FR-GTE-04: phát hành đầy đủ nằm ngoài phạm vi M13 |
| SSO OIDC dùng chung CVAT | A §20 | SRS §9.3: xác thực theo phiên đăng nhập LabelX |
| AI Assistant query (`/assistant/query`) | A §25 | B-13; ngoài phạm vi |
| Trạng thái Issue: Known Defect, Superseded, On Hold | A §23.1 | SRS `tab:transitions` theo H; không có các trạng thái này |
| Trạng thái run Draft/Snapshotting/Published/Archived | A §23.2 | SRS state machine QC Run chỉ có Queued, Running, Completed, Partial, Failed, Cancelled |
| NOT_REQUIRED, EXCEPTION_APPROVED | T §6 | B-19: chỉ lưu làm lý do trong ledger, không phải trạng thái công khai |

## Tài liệu liên quan

- [Kiến trúc hệ thống](system-design.md)
- [Intake kiến trúc](architecture.md)
- [REST API](../04-api/rest-api.md)
