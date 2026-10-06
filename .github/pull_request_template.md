<!-- Base phải là `develop` (CR-104); chỉ PO mở PR vào `main`. Mô tả ngắn thay đổi và lý do. Viết tiếng Việt; giữ nguyên thuật ngữ domain (Snapshot, Issue, Rework...). -->

## Thay đổi

-

## Truy vết

- Task / epic: <!-- vd TASK-xxx, E-xx trong .agent/ -->
- Yêu cầu SRS: <!-- vd FR-SNP-04, UC-05, AC-03 -->
- Change request / decision (nếu đổi phạm vi, contract, kiến trúc): <!-- CR-xxx, DEC-xxx -->

## Kiểm tra

- [ ] `make check` pass cục bộ (lint, typecheck, test, validate-kit)
- [ ] Đã thêm/cập nhật test cho hành vi mới (`src/backend/tests/`)
- [ ] Tài liệu trong `docs/`, `.agent/` viết bằng HTML có `<meta name="labelx:*">` (CR-103); `make validate-kit` pass
- [ ] Sửa SRS LaTeX thì đã chạy `scripts/srs_tex2html.py` và `scripts/srs_tex2docs.py`
- [ ] Không commit secret (`.env`, `.env.local`, token CVAT)

## Duyệt (CR-102)

PR không phải của PO cần Trịnh Quang Trung hoặc Nguyễn Đức Hà review; thông qua thì người duyệt comment đúng câu `Đã xem và duyệt`. Đẩy thêm commit sau đó thì phải duyệt lại.

## Ràng buộc đã giữ

- [ ] Adapter CVAT chỉ đọc; sửa annotation bằng deep link (B-18)
- [ ] Celery task idempotent khi retry (B-10)
- [ ] Quyền project/job kiểm ở API; không self-review (B-12)
- [ ] UI theo Design System LabelX (`lx-*`)
