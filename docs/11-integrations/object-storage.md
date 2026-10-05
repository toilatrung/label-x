---
id: integration-object-storage
title: Tích hợp Object Storage
type: reference
domain: integrations
module: object-storage
tags: [integrations, object-storage, s3, evidence, gc]
priority: 2
---
# Tích hợp Object Storage

## 1. Vai trò

Object Storage lưu dữ liệu nhị phân bất biến:

- ảnh frame của snapshot;
- crop evidence;
- báo cáo xuất.

Metadata nằm trong PostgreSQL. Môi trường thật dùng **Object Storage S3-compatible hiện có**. Dev local dùng SeaweedFS (nguồn: DEC-001; R cấu hình MVP "Backend"; SRS ch.10).

## 2. Bucket

Theo [docker-compose.dev.yml](../../infrastructure/docker-compose.dev.yml) (service `seaweedfs-init`):

| Bucket | Nội dung | Ghi bởi | Yêu cầu |
|---|---|---|---|
| `labelx-snapshots` | Ảnh frame tải từ CVAT lúc tạo snapshot | Task `snapshots.export_job` | FR-SNP-05 |
| `labelx-evidence` | Crop ảnh, overlay, payload evidence của candidate; tệp evidence của waiver | Task engine (`match_unit`…), API waiver | FR-ENG-08; FR-GTE-03 |
| `labelx-reports` | Báo cáo PDF/CSV/JSON | Task `reports.export_report` | FR-RPT-05 |

Bucket mặc định của `STORAGES["default"]` trong [settings.py](../../src/backend/config/settings.py) là `labelx-evidence` (biến `OBJECT_STORAGE_BUCKET`). Ngoài `default`, settings có ba storage tương ứng ba bucket: `storages["snapshots"]` (`OBJECT_STORAGE_BUCKET_SNAPSHOTS`), `storages["evidence"]` (`OBJECT_STORAGE_BUCKET_EVIDENCE`), `storages["reports"]` (`OBJECT_STORAGE_BUCKET_REPORTS`); mặc định là tên bucket trong compose.

Vị trí lưu **model artifact** (L: "Model Registry") chưa có bucket trong compose và chưa chốt. Yêu cầu tối thiểu là lưu được checksum và mapping lớp (FR-ENG-05).

## 3. Khoá theo hash nội dung

```text
<bucket>/sha256/<2 ký tự đầu>/<sha256>.<ext>
ví dụ: labelx-snapshots/sha256/9f/9f86d081…0a08.jpg
```

- Khoá được tính từ SHA-256 của chính nội dung. Ghi lại cùng nội dung sẽ ra cùng khoá, nên **ghi lặp là idempotent** (NFR-06).
- Cùng một ảnh xuất hiện trong nhiều snapshot (snapshot gia tăng, run cuối) chỉ được lưu một lần. Mỗi dòng `frame` vẫn ghi `image_sha256` riêng.
- `frame.image_sha256` chính là checksum mà FR-SNP-05 yêu cầu. Worker kiểm lại checksum khi đọc ảnh để chạy engine.
- Cấu hình: storage `snapshots` và `evidence` đặt `file_overwrite=True`, vì `file_overwrite=False` của django-storages sẽ **tự đổi tên** khi khoá đã tồn tại và phá cơ chế content-addressed; ghi lại cùng khoá hash là ghi cùng nội dung nên idempotent. `reports` và `default` giữ `False`. Vẫn nên `HEAD` trước khi ghi blob lớn để tránh upload thừa. Kiểm bằng `src/backend/tests/test_settings.py`.

## 4. Upload trước, commit sau

Thứ tự bắt buộc khi worker ghi kết quả (NFR-06):

1. Tính SHA-256 của blob, rồi `PUT` lên bucket (bỏ qua nếu đã có).
2. Mở transaction PostgreSQL: ghi `candidate`, `evidence(payload_key, payload_sha256)` và `ledger_entry`; cập nhật `work_unit` → COMMIT.
3. Nếu worker chết sau bước 1 nhưng trước bước 2, blob trở thành mồ côi. Task chạy lại sẽ ghi đúng blob đó (cùng khoá) rồi commit. Blob nào không bao giờ được commit sẽ bị GC dọn.

Không có thứ tự ngược lại (commit trước, upload sau), vì như vậy DB có thể trỏ tới blob không tồn tại.

## 5. Dọn rác (GC) và lưu trữ

| Loại | Chính sách | Nguồn |
|---|---|---|
| Blob mồ côi | Task định kỳ `storage.gc_orphan_blobs` xoá blob không được `frame.image_sha256`, `evidence.payload_sha256`, `waiver.evidence_key` hay `report_export.sha256` nào tham chiếu, sau `t_gc` kể từ lúc tạo. `t_gc`: **TBD-20** | NFR-06 |
| Snapshot, evidence nguồn, reference, báo cáo | **Không xoá** khi dataset còn cần quản lý hoặc đối chiếu. Việc kết thúc lưu do QA Lead và người quản lý dữ liệu xác nhận, và được audit. Chưa đặt số ngày | R "retention"; NFR-08; TBD-15 |
| Cache, crop tạm | Chỉ dọn khi không còn công việc dùng và có thể tái tạo từ nguồn giữ nguyên | R "retention" |
| Versioning bucket | Bật ở môi trường thật; sao lưu cùng lịch với PostgreSQL. RPO/RTO **TBD-17** | NFR-16 |

## 6. Bảo mật

- Ảnh chỉ lưu trong Object Storage nội bộ; không gửi ảnh ra dịch vụ ngoài trong pilot (NFR-09). Chưa được nạp ảnh BDD100K trước khi Data Owner xác nhận giấy phép và điều khoản lưu trữ nội bộ (**TBD-18**).
- Client không nhận credential của storage. Ảnh và crop được phục vụ qua API có kiểm quyền, hoặc qua presigned URL ngắn hạn sinh sau khi đã kiểm scope. Thời hạn presigned URL **chưa chốt**.
- Credential nằm trong biến môi trường `OBJECT_STORAGE_*` và không được ghi vào log (NFR-07).
