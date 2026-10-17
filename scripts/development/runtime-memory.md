# Giới hạn RAM cho stack dev Label-X

Khi Label-X chạy chung với CVAT trên WSL, số CPU không phản ánh lượng RAM còn
trống. Celery tự chọn theo CPU đã mở 16 process trong môi trường 9,5 GiB RAM;
log ngày 15/10/2026 ghi nhận worker và Django autoreloader cùng lỗi
`Cannot allocate memory`, sau đó frontend nhận `ECONNREFUSED` từ API.

`dev-stack.sh` và `make dev-worker` mặc định dùng các giới hạn sau:

| Biến môi trường shell | Mặc định | Ý nghĩa |
|---|---:|---|
| `LABELX_WORKER_CONCURRENCY` | 2 | Số process Celery xử lý song song |
| `LABELX_WORKER_MAX_TASKS_PER_CHILD` | 20 | Thay worker con sau khi hoàn thành đủ task |
| `LABELX_WORKER_MAX_MEMORY_KIB` | 393216 | Thay worker con sau task nếu RSS vượt 384 MiB |
| `LABELX_DJANGO_AUTORELOAD` | 1 | Với dev-stack: đặt 0 để bỏ quét file tự reload Django |

Giới hạn bộ nhớ của Celery **không phải hard cap**: task đang chạy vẫn có thể
vượt ngưỡng; worker con được thay sau khi task hoàn thành. Vì vậy, giảm
concurrency và đo RAM trong run thực tế vẫn là bước chính. Thay worker con sau
task không sửa trạng thái, cấu hình hay model của run. Máy mạnh hơn có thể tăng
concurrency với cùng các biến trên.

Các biến này được đọc bởi shell, không phải từ file `.env` của Django. Có thể
export trong terminal trước khi chạy stack; thay đổi chỉ có hiệu lực với process
khởi động tiếp theo. `refresh be` chạy dependency/migration như trước; dùng
`restart be` khi chỉ cần khởi động lại process.

Ví dụ cho máy đang chạy CVAT và thiếu RAM:

```bash
export LABELX_WORKER_CONCURRENCY=1
export LABELX_WORKER_MAX_TASKS_PER_CHILD=20
export LABELX_WORKER_MAX_MEMORY_KIB=393216
export LABELX_DJANGO_AUTORELOAD=0
bash scripts/dev-stack.sh restart be
```

Khi tắt autoreload, sửa backend xong cần chủ động restart để nạp code mới.
Worker và beat cũng được restart theo hành vi hiện có của `restart be`; chọn
thời điểm phù hợp vì script dừng cả nhóm backend. Không chạy lệnh này giữa run
quan trọng. Áp dụng PR không tự thực hiện restart hoặc thay đổi Docker/CVAT.

Sau khi áp dụng, xác nhận log worker ghi `concurrency: 1` hoặc `2`, API phản hồi
và theo dõi `free -h` trong run thật. Unit test chỉ xác minh lệnh launch, giới hạn
và validation; không chứng minh peak RAM của detector/GPU/WSL hay việc khôi phục
run đang bị lỗi. Giảm concurrency đánh đổi throughput để giảm số task đồng thời.

Tham khảo cơ chế pool/recycle chính thức:
[Celery Workers Guide](https://docs.celeryq.dev/en/stable/userguide/workers.html).

Kiểm tra độc lập, không cần Docker/Django và không khởi động dịch vụ:

```bash
bash -n scripts/dev-stack.sh
python3 -m unittest discover -s scripts/development/tests -p test_runtime_memory.py -v
```
