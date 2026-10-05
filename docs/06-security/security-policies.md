---
id: security-policies
title: Chính sách bảo mật LabelX
type: reference
domain: security
module: repository
tags: [security, rbac, separation-of-duties, audit, retention]
priority: 1
---
# Chính sách bảo mật LabelX

## Mục đích

Gom các chính sách bảo mật **đã chốt** mà backend và frontend LabelX phải hiện thực. Mỗi chính sách ghi nguồn. Phần nào là đề xuất của tài liệu này thì ghi rõ "đề xuất"; phần nào chưa chốt thì dùng mã TBD của SRS.

Nguồn chính:

- SRS: FR-SEC-01…07 và bảng `tab:rbac` trong `06-functional.tex`, NFR-07/08 trong `08-nonfunctional.tex`, hợp đồng lỗi trong `09-interfaces.tex`.
- `docs/00-project/sources/architecture_review.html`, phiếu chốt B-11 (waiver), B-12 (quyền, tách nhiệm vụ, audit), B-18 (adapter chỉ đọc).
- `docs/00-project/sources/Quality_Control_Review_UX_Architecture.html` mục 14, 21, 28, ADR-04/06/07.
- Màn hình H `docs/design/screens/WorkflowPermissions.dc.html`.

## 1. Nguyên tắc chung

1. **Backend luôn kiểm quyền.** Ẩn nút trên giao diện chỉ để thuận tiện (H, WorkflowPermissions). Mọi endpoint kiểm vai trò + scope (FR-SEC-01, NFR-07). Cấu hình hiện có: `DEFAULT_PERMISSION_CLASSES = IsAuthenticated` (`src/backend/config/settings.py`). Permission theo vai trò/scope **chưa có**, sẽ thêm cùng module Auth/RBAC/Audit.
2. **Quyền project/job kiểm ở API**, không dựa vào frontend hay CVAT (`CLAUDE.md`, DEC-001).
3. **Adapter CVAT chỉ đọc**: không có đường gọi tạo/sửa/xoá annotation; sửa annotation bằng deep link sang CVAT (B-18, FR-SNP-01, FR-SNP-08).
4. Chặn theo ngữ cảnh (lease của người khác, self-review, tách nhiệm vụ, gate chưa đạt) vẫn **hiển thị nút ở trạng thái disabled kèm lý do**; truy cập URL không có quyền thì hiện trang "Không đủ quyền" (A mục 14.1).

## 2. RBAC theo vai trò và scope

Ma trận lấy từ SRS `tab:rbac` (theo H WorkflowPermissions). Quyền luôn giới hạn trong **scope dataset** được giao (FR-SEC-01; A mục 28: "RBAC theo vai trò cộng scope project/dataset, enforce ở server").

| Chức năng | Annotator | Reviewer | Quality Assurance Lead | Quality Control Admin | Super Admin |
|---|---|---|---|---|---|
| Snapshot, chạy phân tích | — | — | Chạy/xem | Cấu hình | Chạy/cấu hình |
| Review Queues, Workspace | — | Review | Review/giám sát | Xem | Review/giám sát |
| Rework | Thực hiện | Yêu cầu/xác minh | Yêu cầu/giám sát | — | Thực hiện/xác minh |
| Phân xử | — | — | Có | — | Có (ghi đè) |
| Reference, đánh giá | — | Lập Ground Truth (khi được giao) | Quản lý/khoá | Cấu hình | Quản lý |
| Báo cáo hiệu quả | Giới hạn | Xem | Đầy đủ | Đầy đủ | Đầy đủ |
| Cấu hình, quyền | — | — | Giới hạn | Có | Có |

Phân vai đã duyệt (phiếu chốt B-12): Quality Assurance Lead quản lý chất lượng/phân xử; Quality Control Admin cấu hình kỹ thuật và scope quyền; người có quyền nghiệp vụ duyệt ngoại lệ/phát hành phải khác người yêu cầu; **Super Admin không là người duyệt mặc định**. Việc gán người và tài khoản thật **chưa làm**, không được coi là quyền đã cấp.

Ghi chú khác biệt nguồn:

- H có thêm dòng "Phê duyệt phát hành" (Quality Assurance Lead: "Người được cấp quyền"; Super Admin: "Có (ghi đè)"). SRS FR-GTE-04 đặt phát hành dataset đầy đủ **ngoài phạm vi M13**, M13 chỉ hiển thị kết quả gate. Khi phạm vi phát hành được mở, áp dụng cùng quy tắc tách nhiệm vụ ở mục 4.
- H và A cho Annotator "Tham gia" Calibration và Audit, còn SRS ghi "—" ở dòng Reference, đánh giá. Tài liệu này theo SRS cho reference. Annotator chuẩn bị reference khi được giao nhưng không tự review annotation của mình (phiếu chốt B-20).
- Service account AI/worker chỉ được ghi Candidate và Evidence, không có quyền decision/gate/release (ADR-07, A mục 28).

## 3. Self-review theo assignee tại snapshot

- Lưu **identity mapping** giữa tài khoản LabelX và người dùng CVAT; mapping này dùng để kiểm self-review (FR-SEC-02).
- Snapshot lưu **assignee từng job tại thời điểm snapshot** (FR-SNP-05). Lý do: CVAT không lưu tin cậy người tạo từng shape (A mục 21).
- Backend **từ chối (403)** quyết định review khi reviewer là assignee của job tại snapshot, kể cả khi mở frame trực tiếp bằng URL (FR-SEC-03, FR-REV-14).
- Cấp lease tự động bỏ qua frame mà reviewer là assignee tại snapshot (FR-REV-03).

## 4. Tách người yêu cầu và người duyệt

- Người duyệt waiver, khoá reference, phân xử phải **khác người yêu cầu**; không được dùng tài khoản khác của cùng một người (FR-SEC-04; B-11, B-12).
- Nếu chưa có người khác đủ quyền thì **chờ**, không tự duyệt bằng tài khoản phụ (phiếu chốt R, ghi chú phân vai đi kèm B-11: "Nếu chưa có người khác đủ quyền thì chờ, không dùng tài khoản khác của cùng người để tự duyệt").
- API trả **403** khi người duyệt trùng người đề nghị (09-interfaces, hợp đồng lỗi).

### Waiver (B-11)

- Giữ scope waiver của H, nhưng **bắt buộc policy cho từng điều kiện gate**.
- Mỗi waiver có: lý do, evidence, thời hạn hiệu lực/hết hạn, người duyệt khác người yêu cầu (FR-GTE-03).
- Waiver **không tự có hiệu lực**: chỉ hiệu lực sau khi được duyệt; hết hạn thì điều kiện trở lại "chưa đạt".
- Waiver **không biến Not checked thành pass**; điều kiện thiếu dữ liệu là chưa đạt (FR-GTE-02, B-19).

## 5. Super Admin ghi đè

- Ghi đè bắt buộc **lý do**, được **gắn nhãn Super Admin** trong audit (FR-SEC-06; H: "Ghi đè của Super Admin phải có lý do", áp dụng cho quyết định, phân xử, waiver, phê duyệt phát hành, duyệt guideline).
- Super Admin **vẫn chịu** kiểm self-review và tách nhiệm vụ: không tự duyệt waiver/release do chính mình yêu cầu, không review annotation do chính mình tạo (A mục 14).
- Số tài khoản Super Admin giữ ở mức tối thiểu và được rà soát định kỳ (A mục 14, 28). Chu kỳ rà soát **chưa chốt**.

## 6. Token CVAT và secret

- Token service account CVAT **chỉ ở backend**, không gửi xuống client (FR-SNP-02, NFR-07). Hiện đọc từ biến môi trường `CVAT_SERVICE_TOKEN` (`settings.py`). Ở môi trường thật, đặt trong secret store (FR-SNP-02); secret store cụ thể **chưa chốt** (phụ thuộc TBD-02).
- Service account CVAT chỉ có quyền đọc (`.env.example`; B-18). Quyền thật của token còn **TBD-01**.
- Frontend chỉ biết `NEXT_PUBLIC_CVAT_BASE_URL` để dựng deep link (`src/frontend/.env.example`). Không đưa token hay secret vào biến `NEXT_PUBLIC_*`, vì biến này bị nhúng vào bundle trình duyệt.
- File `.env` và `.env.*` bị loại khỏi git (`.gitignore`, trừ `.env.example`). Credential trong `.env.example`, `infrastructure/docker-compose.dev.yml`, `infrastructure/seaweedfs/s3.json` **chỉ dùng cho dev local**; không dùng lại cho môi trường thật.
- Mật khẩu/secret không xuất hiện trong log (NFR-07). Xem [../13-observability/logging.md](../13-observability/logging.md).
- `make env` sinh `DJANGO_SECRET_KEY` ngẫu nhiên với tiền tố `dev-only-` cho local (`scripts/init-develop-environment.mk`).

## 7. Audit append-only cùng transaction

- AuditEvent ghi: actor, vai trò, hành động, đối tượng, trước/sau, revision, lý do (FR-SEC-05). A bổ sung guideline version và evidence refs (A mục 28).
- Ghi **trong cùng transaction PostgreSQL** với thao tác nghiệp vụ (FR-SEC-05, NFR-06, ADR-04). Cấu hình nền đã có `DATABASES["default"]["ATOMIC_REQUESTS"] = True`. Riêng Celery task phải tự mở transaction cho phần ghi.
- **Append-only**: không có API sửa/xoá; không cấp quyền `UPDATE`/`DELETE` trên bảng audit cho user ứng dụng (NFR-08, ADR-06). Cách kiểm: kiểm thử API và rà soát DB grant (NFR-08).
- Lỗi 403/409 cũng được ghi audit (09-interfaces). **Yêu cầu phải hiện thực (chưa có code):**
  - Vì `ATOMIC_REQUESTS = True`, mọi ghi DB trong view nằm trong transaction của request. Khi view trả 403/409 bằng exception, transaction đó bị rollback, nên AuditEvent "bị từ chối" ghi theo cách thông thường cũng mất theo.
  - `transaction.on_commit` không giải quyết được: callback chỉ chạy khi transaction commit, mà đây là trường hợp rollback.
  - Sự kiện từ chối phải được ghi **ngoài transaction bị rollback**. Các cách có thể chọn: (a) ghi qua một kết nối DB riêng (alias database thứ hai trỏ cùng PostgreSQL, autocommit); (b) ghi sau khi transaction request đã rollback, ví dụ trong exception handler/middleware chạy ngoài khối atomic, hoặc view được đánh dấu `non_atomic_requests` tự quản lý transaction; (c) dùng savepoint chỉ khi phần bị huỷ nằm trong savepoint con và bản ghi audit nằm ở transaction ngoài được commit. Chọn cách nào phải ghi decision.
  - Phân biệt với audit của thao tác **thành công**: thao tác thành công vẫn phải ghi audit **cùng** transaction (nếu audit lỗi thì thao tác rollback).
  - Cách kiểm chứng (đề xuất test): gọi API với tình huống self-review (403) và lease của người khác (409); xác nhận phản hồi đúng mã và có `request_id`; xác nhận **không** có thay đổi nghiệp vụ nào được lưu; truy vấn bảng audit bằng kết nối mới, sau khi request kết thúc, và thấy đúng một AuditEvent từ chối với actor, hành động, đối tượng, lý do và `request_id`. Test phải dùng transaction thật (ví dụ `pytest.mark.django_db(transaction=True)`), vì test bọc trong một transaction lớn sẽ che mất lỗi rollback.
- 100% decision, waiver, approval, config publish phải có AuditEvent (A, bảng NFR).
- Đề xuất (chưa chốt): nối hash chain giữa các AuditEvent (ADR-06 ghi "có thể").
- Màn hình xem audit lọc theo actor, đối tượng, thời gian (FR-SEC-07, mức Should).

## 8. Lưu trữ (NFR-08)

- Audit, evidence, snapshot và reference được giữ **chừng nào dataset còn cần quản lý hoặc đối chiếu** (NFR-08). Phiếu chốt R bổ sung: decision, report/manifest cũng được giữ.
- Việc kết thúc lưu do **người quản lý dữ liệu xác nhận** và được ghi audit. Không tự đặt ngày/tháng, không tự xoá.
- Chỉ dọn **cache/crop tạm** khi không còn công việc dùng và tái tạo được (phiếu chốt R, định hướng lưu).
- Blob không có metadata trỏ tới sau \(t_{gc}\) được job dọn dẹp xoá (NFR-06). Giá trị \(t_{gc}\) **chưa chốt**.
- Thời hạn lưu audit tối thiểu: **TBD-15** (Product Owner, trước triển khai).
- Sao lưu PostgreSQL và Object Storage (bật versioning) theo cùng lịch; RPO/RTO **TBD-17** (NFR-16).

## 9. Truyền tải và cấu hình web

- HTTPS cho trình duyệt ↔ app server và app server ↔ CVAT (NFR-07; SRS hình deployment).
- Hiện trạng `settings.py`: đã có `SecurityMiddleware`, `CsrfViewMiddleware`, `XFrameOptionsMiddleware`, CORS chỉ cho origin trong `CORS_ALLOWED_ORIGINS` kèm credential, `DEBUG` mặc định `False`.
- **Đăng nhập, session và CSRF cho frontend tách cổng** (dev: Next.js `http://localhost:3000` gọi API `http://localhost:8000/api`):
  - Xác thực API là `SessionAuthentication` (settings.py; SRS 09: "xác thực theo phiên đăng nhập LabelX").
  - **Việc mở:** `src/backend/config/urls.py` hiện chỉ có `admin/`, `api/schema/`, `api/docs/`. **Chưa có endpoint đăng nhập/đăng xuất/lấy người dùng hiện tại cho API**, và chưa có trang đăng nhập ở frontend. Đăng nhập qua `/admin/` chỉ dành cho tài khoản staff; không coi đó là luồng đăng nhập của sản phẩm.
  - Luồng cần hiện thực (yêu cầu theo cơ chế session của Django/DRF): frontend lấy cookie `csrftoken` (qua một endpoint GET đặt cookie CSRF); gửi đăng nhập bằng POST kèm header `X-CSRFToken`; backend tạo session và đặt cookie `sessionid`; mọi request sau gửi bằng `credentials: "include"`; mọi request ghi (POST/PUT/PATCH/DELETE) gửi `X-CSRFToken`. DRF `SessionAuthentication` bắt buộc CSRF cho người dùng đã đăng nhập.
  - CORS: đã có `CORS_ALLOWED_ORIGINS` (dev `http://localhost:3000` theo `.env.example`) và `CORS_ALLOW_CREDENTIALS = True`. Origin phải liệt kê cụ thể, không dùng `*` khi bật credential.
  - **`CSRF_TRUSTED_ORIGINS`** đã có trong settings.py: đọc từ biến môi trường cùng tên, mặc định bằng `CORS_ALLOWED_ORIGINS` (dev: `http://localhost:3000`). Django kiểm header `Origin` của request ghi theo danh sách này; thiếu thì POST từ frontend khác origin bị 403 CSRF. Kiểm bằng `src/backend/tests/test_settings.py`.
  - Production: ưu tiên phục vụ frontend và API cùng origin qua reverse proxy, để giảm cấu hình CORS/CSRF (đề xuất, phụ thuộc TBD-02). Nếu khác origin thì đặt `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` đúng tên miền HTTPS, và xem lại `SameSite` của cookie.
- **Đề xuất cho production** (chưa có trong repo): bật `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS; giới hạn quyền xem `/api/schema/` và `/api/docs/`; đặt `ALLOWED_HOSTS` và `CORS_ALLOWED_ORIGINS` đúng tên miền thật.

## Việc còn mở

| Việc | Mã / chủ |
|---|---|
| Quyền thật của token CVAT, endpoint thật | TBD-01 |
| Phần cứng, vùng mạng, secret store | TBD-02 |
| Thời hạn lưu audit | TBD-15 |
| RPO/RTO | TBD-17 |
| Thời hạn lease | TBD-09 |
| Gán người/tài khoản Quality Assurance Lead, Quality Control Admin | Phiếu chốt R, định hướng phân công — chưa thực hiện |
| Xác thực SSO OIDC (A mục 21) so với phiên đăng nhập LabelX (SRS) | Chưa chốt; hiện theo SRS |

## Liên quan

- [threat-model.md](threat-model.md)
- [compliance.md](compliance.md)
