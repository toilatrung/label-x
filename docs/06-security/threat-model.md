---
id: security-threat-model
title: Threat model LabelX
type: reference
domain: security
module: repository
tags: [security, threat-model, stride, cvat, trust-boundary]
priority: 2
---
# Threat model LabelX

## Mục đích và phạm vi

Tài liệu mô tả tài sản cần bảo vệ, ranh giới tin cậy và các mối đe doạ theo STRIDE của LabelX — module Quality Control chạy quanh CVAT — cùng biện pháp **lấy từ quyết định đã chốt**. Đây là threat model ở mức thiết kế cho MVP/pilot. Repo hiện mới có khung dự án (Django chưa có app nghiệp vụ, frontend mới có trang mặc định), nên mọi biện pháp dưới đây là **yêu cầu phải hiện thực**. Chúng chưa phải chức năng đã có.

Nguồn:

- `docs/00-project/sources/architecture_review.html` — phiếu chốt B-01…B-21, đặc biệt B-10, B-11, B-12, B-18 (gọi tắt **R**).
- `docs/00-project/sources/Quality_Control_Review_UX_Architecture.html` — mục 14, 20.2 (ADR-01…07), 21, 28 (gọi tắt **A**).
- `docs/00-project/sources/QC_Engine_Review_Report.html` — mục 6, độ tin cậy vận hành (gọi tắt **T**).
- SRS đã duyệt: `docs/label-x_system-requirement-specification/sections/06-functional.tex` (FR-SNP, FR-REV, FR-SEC, FR-GTE), `08-nonfunctional.tex` (NFR-05…09, NFR-16), `09-interfaces.tex`, `10-architecture.tex`.
- Cấu hình thật: `src/backend/config/settings.py`, `infrastructure/docker-compose.dev.yml`.

## Tài sản

| Tài sản | Nơi lưu | Vì sao quan trọng | Nguồn |
|---|---|---|---|
| Token service account CVAT | Backend (biến môi trường `CVAT_SERVICE_TOKEN`; production: secret store) | Có token là đọc được toàn bộ project/job/ảnh trên CVAT | FR-SNP-02, NFR-07, A mục 21 |
| Snapshot (annotation đã chuẩn hoá, hash SHA-256, assignee từng job, mapping frame) | PostgreSQL + Object Storage | Nền của tái lập (R-01) và kiểm self-review (assignee tại snapshot) | FR-SNP-03…06 |
| Ảnh BDD100K và crop evidence | Object Storage nội bộ | Dữ liệu nguồn; không được gửi ra ngoài | NFR-09, NFR-06 |
| Candidate, issue, decision, lease, effort log | PostgreSQL | Bằng chứng review và KPI | FR-REV, FR-EVL-06 |
| Audit log | PostgreSQL (append-only) | Bằng chứng nghiệm thu R-05; không sửa ngược được | FR-SEC-05, NFR-08, ADR-06 |
| Reference (Ground Truth) đã khoá, tập held-out | PostgreSQL + Object Storage | Rò rỉ hoặc sửa reference làm sai KPI | FR-EVL, RK-02, RK-09 |
| Waiver, gate, báo cáo/manifest | PostgreSQL + Object Storage | Quyết định phát hành phụ thuộc vào đây | FR-GTE-01…03, B-11 |
| Model artifact Detector (checksum, mapping lớp) | Object Storage / GPU server | Artifact bị thay thì candidate sai mà không ai biết | FR-ENG-05, NFR-04 |
| Cấu hình engine, ngưỡng, policy version | PostgreSQL | Đổi ngưỡng sau khi thấy held-out là gian lận đo | RK-09 |
| `DJANGO_SECRET_KEY`, thông tin kết nối DB/Redis/S3 | Biến môi trường backend | Lộ ra thì giả mạo được phiên đăng nhập hoặc truy cập thẳng kho dữ liệu | `src/backend/.env.example` (chỉ là mẫu) |

## Ranh giới tin cậy

Sơ đồ triển khai lấy từ SRS chương 10 (`10-architecture.tex`, hình deployment). Cấu hình phần cứng còn **TBD-02**.

```text
[Trình duyệt] --(TB-1) HTTPS + session--> [App server: Gunicorn + Django/DRF, Celery CPU workers]
     |                                                 |                    |
     | (TB-3) deep link, mở thẳng CVAT                  | (TB-2) HTTPS,      | (TB-4) task qua Redis
     v                                                 |  chỉ đọc            v
[CVAT hiện có] <---------------------------------------+          [GPU server: Celery GPU worker, Detector]
                                                       |                    |
                                     (TB-5, TB-6)      v                    v
                                 [Data: PostgreSQL · Redis · Object Storage]
```

| # | Ranh giới | Bên ngoài → bên trong | Giả định tin cậy | Biện pháp chính |
|---|---|---|---|---|
| TB-1 | Trình duyệt ↔ Django API | Người dùng (Annotator, Reviewer, QA Lead, QC Admin, Super Admin) | **Không tin** mọi thứ từ client: ẩn nút trên UI chỉ để thuận tiện | Backend kiểm quyền mọi request (FR-SEC-01, H WorkflowPermissions); session + CSRF (Django `SessionAuthentication`, `CsrfViewMiddleware` đã bật trong `settings.py`); HTTPS (NFR-07) |
| TB-2 | Django/worker ↔ CVAT | Hệ thống ngoài do đội khác vận hành | Tin dữ liệu ở mức "nguồn annotation", không tin là bất biến | Adapter **chỉ đọc** (B-18, FR-SNP-01); token chỉ ở backend (FR-SNP-02); kiểm drift trước khi khoá snapshot (FR-SNP-04); engine chỉ đọc snapshot đã export, không đọc CVAT live (ADR-02) |
| TB-3 | Trình duyệt ↔ CVAT (deep link) | Người dùng sang thẳng CVAT | LabelX không kiểm được thao tác trong CVAT | Sửa annotation chỉ trong CVAT bằng quyền CVAT của chính người dùng; LabelX phát hiện thay đổi qua hash revision và tạo snapshot mới (FR-SNP-06, B-03) |
| TB-4 | App server ↔ GPU worker | Máy riêng chạy Detector | Tin ở mức worker nội bộ, nhưng kết quả phải truy được nguồn | Kết quả gắn model name/version/checksum/mapping (09-interfaces, giao diện mô hình); GPU worker không gửi ảnh ra ngoài (NFR-09); worker chỉ ghi candidate/evidence (ADR-07) |
| TB-5 | Ứng dụng ↔ Object Storage | Kho S3-compatible hiện có | Tin cậy nội bộ; dữ liệu đã ghi không được ghi đè | Khoá blob theo hash nội dung, ghi lại là idempotent (NFR-06); `file_overwrite: False` trong `STORAGES` (settings.py); bật versioning khi sao lưu (NFR-16) |
| TB-6 | Ứng dụng ↔ PostgreSQL / Redis | Hạ tầng dữ liệu | PostgreSQL là nguồn chuẩn; Redis chỉ là broker/cache | Lease cấp bằng khoá dòng trong transaction PostgreSQL (SRS 10, tab:modules); decision và audit cùng transaction (NFR-06, ADR-04); `ATOMIC_REQUESTS = True` (settings.py) |

## Mối đe doạ STRIDE và biện pháp

Cột "Trạng thái" cho biết biện pháp đã có trong repo hay mới là yêu cầu. Hiện gần như toàn bộ là **yêu cầu**, vì chưa có module nghiệp vụ nào.

### S — Spoofing (giả mạo danh tính)

| Mã | Mối đe doạ | Biện pháp | Nguồn | Trạng thái |
|---|---|---|---|---|
| S-1 | Người dùng mượn tài khoản thứ hai để tự duyệt waiver/reference/phân xử của chính mình | Người duyệt khác người yêu cầu; cấm dùng tài khoản khác của cùng người. Nếu chưa có người khác đủ quyền thì phải chờ | FR-SEC-04; R phiếu chốt B-11, B-20 | Yêu cầu. Kiểm "cùng một người" cần identity mapping (S-2) và quy trình cấp tài khoản; kỹ thuật thuần không chặn được hết |
| S-2 | Reviewer review chính annotation của mình bằng cách dùng tài khoản LabelX khác tên CVAT | Lưu identity mapping LabelX ↔ CVAT; kiểm self-review theo **assignee của job tại snapshot** | FR-SEC-02, FR-SEC-03; A mục 21 | Yêu cầu |
| S-3 | Đánh cắp session cookie / CSRF | Session auth + CSRF middleware (đã có); HTTPS bắt buộc (NFR-07); cookie `Secure` ở production | settings.py; NFR-07 | Một phần: session/CSRF đã bật, cấu hình HTTPS/`SECURE_*` **chưa có** (đề xuất, xem [security-policies.md](security-policies.md)) |
| S-4 | Worker hoặc service account AI giả làm người ra quyết định | Service account AI/worker chỉ được ghi Candidate/Evidence, không có quyền decision/gate/release | ADR-07; A mục 28 | Yêu cầu |

### T — Tampering (sửa trái phép)

| Mã | Mối đe doạ | Biện pháp | Nguồn | Trạng thái |
|---|---|---|---|---|
| T-1 | LabelX ghi đè annotation trên CVAT (nhánh writeback trong T) | **Không có đường gọi tạo/sửa/xoá annotation trên CVAT**; sửa bằng deep link. Service account CVAT nên chỉ có quyền đọc | B-18 (chặn); FR-SNP-01; `.env.example` ghi "service account CHỈ ĐỌC" | Yêu cầu; quyền token thật còn **TBD-01** |
| T-2 | Annotation trên CVAT đổi giữa lúc export làm snapshot không nhất quán | Export từng job, chuẩn hoá, hash; đọc lại trước khi khoá; drift thì không khoá | B-02; FR-SNP-03, FR-SNP-04; RK-06 | Yêu cầu |
| T-3 | Sửa hoặc xoá audit log để che quyết định | Append-only: không có API sửa/xoá, không cấp quyền UPDATE/DELETE ở DB; tuỳ chọn nối hash chain | FR-SEC-05, NFR-08, ADR-06 | Yêu cầu; hash chain là **đề xuất** (A ghi "có thể") |
| T-4 | Ghi đè blob evidence/snapshot/báo cáo trên Object Storage | Khoá theo hash nội dung; `file_overwrite: False`; versioning bucket | NFR-06, NFR-16; settings.py | Một phần: `file_overwrite: False` đã có |
| T-5 | Thay model artifact Detector | Freeze artifact + checksum + mapping lớp, ghi vào QC Run | FR-ENG-01, FR-ENG-05 | Yêu cầu |
| T-6 | Đổi ngưỡng/tham số sau khi thấy kết quả held-out | Pre-registration; audit mọi thay đổi version | RK-09 | Yêu cầu |
| T-7 | Client gửi quyết định cho frame có lease đã hết hạn hoặc thuộc người khác | Backend trả 409; lease là khoá dòng PostgreSQL | FR-REV-14; SRS 10 | Yêu cầu |

### R — Repudiation (chối bỏ hành vi)

| Mã | Mối đe doạ | Biện pháp | Nguồn |
|---|---|---|---|
| R-1 | Người duyệt chối đã duyệt waiver/phát hành | AuditEvent ghi actor, hành động, đối tượng, trước/sau, revision, lý do; cùng transaction với thao tác | FR-SEC-05; B-12 |
| R-2 | Super Admin dùng quyền ghi đè mà không ai biết | Bắt buộc lý do, gắn nhãn Super Admin trong audit | FR-SEC-06; H WorkflowPermissions |
| R-3 | Thao tác bị từ chối (403/409) không để lại dấu vết | Lỗi 403/409 được ghi audit; mọi phản hồi lỗi có `request_id` | 09-interfaces, hợp đồng lỗi |

### I — Information disclosure (lộ thông tin)

| Mã | Mối đe doạ | Biện pháp | Nguồn |
|---|---|---|---|
| I-1 | Token CVAT lộ xuống trình duyệt hoặc vào log | Token chỉ ở backend; secret không xuất hiện trong log | FR-SNP-02, NFR-07 |
| I-2 | Ảnh BDD100K (có thể có mặt người, biển số) bị gửi ra dịch vụ ngoài (VLM/API) | Pilot: không gửi ảnh ra ngoài; Detector chạy GPU worker nội bộ; VLM đề xuất không bật (TBD-08) | NFR-09; FR-ENG-10; A mục 28 |
| I-3 | Người dùng xem dataset/job ngoài scope được giao | RBAC theo vai trò **và** scope dataset, kiểm ở backend | FR-SEC-01; A mục 28 |
| I-4 | Reviewer ở nhánh baseline thấy ranking/evidence làm hỏng thí nghiệm effort | Workspace nhánh baseline ẩn ranking, risk score, evidence | FR-EVL-12 |
| I-5 | Tập held-out lọt vào dữ liệu huấn luyện Detector | Chọn held-out từ phần chắc chắn không dùng huấn luyện | AS-03, RK-02, FR-EVL-05(b) |
| I-6 | OpenAPI schema/Swagger (`/api/schema/`, `/api/docs/`) mở công khai ở production | Đề xuất: giới hạn quyền xem schema ở production (settings hiện chưa đặt `SERVE_PERMISSIONS`) | `src/backend/config/urls.py`; **đề xuất** |

### D — Denial of service (từ chối dịch vụ)

| Mã | Mối đe doạ | Biện pháp | Nguồn |
|---|---|---|---|
| D-1 | Một shard lỗi làm hỏng cả run | Retry có giới hạn với backoff; phần còn lại ghi Failed cho đơn vị đó; worker chết không mất kết quả đã commit | NFR-05 (số lần **TBD-14**); `CELERY_TASK_ACKS_LATE`, `CELERY_TASK_REJECT_ON_WORKER_LOST` trong settings.py |
| D-2 | Retry tạo issue trùng, làm phình hàng đợi | Task idempotent theo khoá (run, engine, shard); dedup theo scope/object/family và version policy | B-10; A mục 20.3; T mục 6 |
| D-3 | Kiểm thị giác – ngôn ngữ (nếu bật) gọi vô hạn | Tối đa 400 candidate mỗi run; tối đa 3 lần thử mỗi lượt kiểm; hết hạn mức thì ghi phần chưa kiểm | B-08; FR-ENG-10 |
| D-4 | Redis mất dữ liệu làm mất event quyết định | Redis chỉ là broker/cache; quyết định và audit nằm trong PostgreSQL (transactional outbox) | ADR-04; SRS 10 |
| D-5 | CVAT chậm/không truy cập được làm treo snapshot | Timeout riêng cho đọc CVAT (chưa đặt số khi chưa đo); snapshot không khoá được thì báo lỗi, không khoá dở | R phiếu chốt B-10; FR-SNP-04 |

### E — Elevation of privilege (leo thang quyền)

| Mã | Mối đe doạ | Biện pháp | Nguồn |
|---|---|---|---|
| E-1 | Gọi API trực tiếp (bỏ qua UI) để làm việc của vai trò khác | `IsAuthenticated` mặc định (đã có trong `REST_FRAMEWORK`); permission theo vai trò + scope ở từng endpoint | settings.py; FR-SEC-01 |
| E-2 | Super Admin tự duyệt yêu cầu của chính mình | Super Admin **không** là người duyệt mặc định; vẫn chịu self-review và tách nhiệm vụ | B-12 (phiếu chốt); FR-SEC-06 |
| E-3 | Waiver tự có hiệu lực hoặc biến Not checked thành pass | Waiver chỉ hiệu lực sau khi duyệt; hết hạn thì điều kiện trở lại chưa đạt; không tự biến Not checked thành pass | B-11; FR-GTE-02, FR-GTE-03 |
| E-4 | Mở frame bằng URL để né kiểm self-review | Backend từ chối (403) kể cả khi mở frame trực tiếp bằng URL | FR-REV-14 |

## Rủi ro còn lại và việc mở

- **TBD-01**: phiên bản CVAT, URL, quyền thật của token. Chưa kiểm được token có thật sự chỉ đọc hay không.
- **TBD-02**: phần cứng app server/GPU server, nên chưa vẽ được vùng mạng chi tiết.
- **TBD-15**: thời hạn lưu audit tối thiểu. **TBD-17**: RPO/RTO sao lưu.
- Cơ chế phát hiện drift: A đề xuất webhook `update:job` có chữ ký, T cho polling có checkpoint làm dự phòng, SRS chỉ yêu cầu đọc lại trước khi khoá (FR-SNP-04). `scripts/init-develop-environment.mk` chỉ khởi động Celery beat, chưa có task/lịch polling CVAT. Phải chốt khi có TBD-01; nếu dùng webhook thì phải xác minh chữ ký.
- Xác thực: A đề xuất SSO OIDC dùng chung với CVAT, còn SRS (09-interfaces) và `settings.py` dùng phiên đăng nhập LabelX. Tài liệu này theo SRS; OIDC là phương án sau, chưa chốt.

## Liên quan

- [security-policies.md](security-policies.md) — chính sách cụ thể (RBAC, tách nhiệm vụ, audit, lưu trữ).
- [compliance.md](compliance.md) — dữ liệu BDD100K, riêng tư dữ liệu.
- [../13-observability/logging.md](../13-observability/logging.md) — quy tắc log không chứa secret.
