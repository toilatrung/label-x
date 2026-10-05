---
id: integration-cvat
title: Tích hợp CVAT (adapter chỉ đọc)
type: reference
domain: integrations
module: cvat-adapter
tags: [integrations, cvat, adapter, read-only, deep-link]
priority: 1
---
# Tích hợp CVAT

## 1. Ranh giới

- CVAT là hệ thống nguồn của annotation, đồng thời là **editor duy nhất**. LabelX chỉ đọc cấu trúc Project/Task/Job/Frame, annotation và ảnh (nguồn: H `Main.dc.html`; R B-18; FR-SNP-01).
- Adapter **không có** bất kỳ đường gọi nào để tạo, sửa hay xoá annotation. Annotation writeback mà T §6 đề xuất **ngoài phạm vi**.
- Mirror Rework thành CVAT issue/comment (A §21) và chuyển stage job chỉ được cân nhắc sau khi API và quyền đã được xác minh. Hai việc này không thuộc MVP (R B-18; R cấu hình "CVAT version/quyền").
- Engine không bao giờ đọc CVAT trực tiếp. Mọi engine đọc snapshot đã khoá (A ADR-02; R-01).

## 2. Phiên bản và cấu hình

| Mục | Giá trị | Nguồn |
|---|---|---|
| Phiên bản CVAT | **TBD-01**: giữ phiên bản đang triển khai, pin sau khi kiểm API thật | R; SRS §9.2; DEC-001 "Negative" |
| Edition (self-host hay cloud) | **TBD-01** | T §6 |
| `cvat-sdk` / client | Chưa pin; trong lúc chờ, client gọi REST bằng `httpx` (có sẵn trong [pyproject.toml](../../src/backend/pyproject.toml)) | DEC-001 |
| URL | Biến `CVAT_BASE_URL` | [settings.py](../../src/backend/config/settings.py) |
| Token | Biến `CVAT_SERVICE_TOKEN`: service account **chỉ đọc**; quyền token thuộc **TBD-01** | FR-SNP-02; R B-12 |

## 3. Thao tác (chỉ đọc)

Theo SRS `tab:cvatapi`. Đường dẫn endpoint cụ thể phụ thuộc phiên bản pin (TBD-01), nên **chưa** được ghi ở đây.

| Thao tác | Mục đích | Dùng ở |
|---|---|---|
| Liệt kê project, task, job | Chọn scope; lấy assignee và thời điểm cập nhật (`updated_date`) | `GET /api/datasets…`; `export_job`; `verify_and_lock` |
| Đọc annotation của job | Lấy shape (rectangle), label, attribute, frame | `export_job` |
| Đọc metadata frame | Kích thước ảnh, tên tệp, mapping frame | `export_job` |
| Đọc dữ liệu ảnh frame | Lưu vào Object Storage kèm checksum | `export_job` → [object-storage.md](object-storage.md) |
| Đọc label/taxonomy của project | Kiểm Schema/Taxonomy | `export_job`; engine Schema |
| Deep link UI | URL mở job tại frame cụ thể | `issue`, `rework_request.deep_link` |

Shape không phải rectangle bị bỏ qua và được đếm vào `snapshot.out_of_scope_shapes` (FR-SNP-07).

## 4. Chuẩn hoá và hash

- JSON chuẩn hoá theo job: sắp xếp khoá, sắp xếp shape theo `(frame, cvat_shape_id)`, toạ độ làm tròn với số chữ số cố định. Số chữ số cụ thể: **TBD-20**. Khi đã chốt thì **không đổi** nữa, vì nó là một phần của version thuật toán hash.
- Mỗi job có `job_hash = SHA-256(JSON chuẩn hoá)`. Hash tổng là SHA-256 của danh sách `(cvat_job_id, job_hash)` đã sắp xếp (FR-SNP-03).
- CVAT không có "annotation revision" chính thức. Revision trong LabelX là hash do LabelX tính (A §21).

## 5. Phát hiện drift

| Cơ chế | Trạng thái | Nguồn |
|---|---|---|
| Đọc lại `updated_date` của từng job trước khi khoá; khác lần đọc đầu thì không khoá, báo danh sách job bị drift | **Bắt buộc** | FR-SNP-04; SD-1 |
| Polling có checkpoint cho job có issue mở | Phương án dự phòng khi không có webhook | R cấu hình "CVAT"; T §6 |
| Webhook `update:job` | Tuỳ chọn; chỉ dùng khi instance hỗ trợ và đã kiểm (TBD-01) | A §21 |
| Dự phòng nếu API không cho kiểm drift tin cậy | Tạm khoá quyền sửa trên scope trong lúc export | RK-06; R B-02 phương án B (không chọn, chỉ là dự phòng) |

Khi annotator báo "Đã sửa", adapter export lại job bị ảnh hưởng. Nếu `job_hash` không đổi, API trả 409 `REVISION_UNCHANGED` (FR-RWK-03).

## 6. Deep link

- Mỗi frame và issue có URL mở đúng job và frame trên CVAT (FR-SNP-08, FR-REV-12).
- Mẫu A §21 có dạng `{CVAT_BASE_URL}/tasks/{task_id}/jobs/{job_id}?frame={n}`. Tham số URL **phụ thuộc phiên bản**, nên phải kiểm trên instance thật (TBD-01).
- Link chỉ được sinh tại một hàm duy nhất trong `cvat_adapter`, để khi đổi phiên bản chỉ cần sửa một chỗ.
- Khi CVAT không truy cập được: tắt nút "Mở trong CVAT" và hiển thị trạng thái đồng bộ (A §26.5).

## 7. Định danh và self-review

- Snapshot lưu assignee của từng job tại thời điểm snapshot (`snapshot_job.assignee_cvat_user_id`) (FR-SNP-05).
- Bảng `identity_mapping` nối tài khoản LabelX với người dùng CVAT. Backend dùng bảng này để từ chối self-review (FR-SEC-02, 03).
- CVAT không lưu tin cậy người tạo từng shape, nên căn cứ self-review là assignee của job (A §21; R B-12).

## 8. Lỗi và timeout

| Tình huống | Xử lý |
|---|---|
| Timeout, 5xx, lỗi mạng | Retry với backoff, theo **TBD-14**. Timeout đọc CVAT đặt riêng (**TBD-13**) |
| 401/403 từ CVAT | Không retry. Snapshot `failed` (`export_error`) và ghi rõ là lỗi quyền service account |
| Ảnh không tải được | Ledger ghi `failed` (`media_error`) cho các đơn vị liên quan; không reject annotation |

## 9. Việc phải làm trước khi build adapter (TBD-01)

1. Chủ CVAT cung cấp URL, phiên bản, edition và service account chỉ đọc.
2. Kiểm trên instance thật: đọc annotation, ảnh và frame mapping; hash ổn định qua hai lần đọc; phát hiện được drift (R mục 7, "Adapter + snapshot").
3. Pin phiên bản và client, rồi cập nhật tài liệu này cùng DEC-001 (bằng một decision mới, không sửa DEC-001).
