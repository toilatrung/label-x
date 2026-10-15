# Máy GPU Worker độc lập

Chạy tại **máy có GPU**, không phải server Label-X. Không cần Django, Node,
database hay `.env` backend. Yêu cầu Python **3.10+**, Docker Compose v2 hỗ trợ
`up --wait`, GPU NVIDIA đã chạy được trong container. Windows dùng Docker Desktop
Linux containers/WSL2 và driver phù hợp. Script không tự cài hoặc restart Docker/WSL.

## 1. Chuẩn bị và cấu hình

Checkout đúng bản code này trên máy GPU. Chuẩn bị checkpoint chính thức tại một
đường dẫn ngoài Git. Tên file và SHA-256 phải khớp
`src/detector_worker/model-manifest.json`; không tải model tự động.

PowerShell, từ root repository:

```powershell
.\scripts\worker\gpu-worker.ps1 configure --checkpoint 'D:\models\faster_rcnn_r50_fpn_3x_det_bdd100k.pth'
.\scripts\worker\gpu-worker.ps1 build
.\scripts\worker\gpu-worker.ps1 start
.\scripts\worker\gpu-worker.ps1 check
```

Bash/Linux, từ root repository:

```bash
bash scripts/worker/gpu-worker.sh configure --checkpoint /srv/models/faster_rcnn_r50_fpn_3x_det_bdd100k.pth
bash scripts/worker/gpu-worker.sh build
bash scripts/worker/gpu-worker.sh start
bash scripts/worker/gpu-worker.sh check
```

Hoặc `python scripts/worker/worker.py <command>` trên cả hai hệ điều hành.
Nếu PowerShell chặn `.ps1` theo ExecutionPolicy, dùng lệnh Python trực tiếp;
không cần hạ chính sách bảo mật hệ thống.
`build` là thao tác tải/cài dependencies nặng, chạy có chủ đích; `start` không tự
build hoặc pull image. Image riêng `labelx-detector-worker:gpu`, Compose project
riêng `labelx-gpu-worker`. Khi cập nhật code worker, chạy lại `build` rồi `start`.

`configure` xác minh hash trước khi lưu; sinh token ngẫu nhiên nếu chưa có và giữ
token cũ khi chạy lại. Có thể cung cấp **file chỉ chứa token** qua `--token-file`;
không truyền token trực tiếp trên command line. Profile/token nằm trong
`.cache/gpu-worker/{config.json,worker.env}` đã bị Git bỏ qua. Linux ghi mode 0600;
Windows kế thừa ACL: giới hạn quyền đọc thư mục này cho tài khoản vận hành.
Không gửi token qua chat, báo cáo hay commit.

Mặc định `--device cuda:0 --port 8501`. Nếu port đã bị container khác chiếm, script
không dừng container đó; chọn port khác, ví dụ thêm `--port 8502` khi configure.
`--device cpu` chỉ debug; backend remote không coi CPU là GPU ready.
Trên Linux checkpoint/thư mục cha phải cho UID 10001 trong container đọc/traverse;
không giải quyết bằng `chmod 777` hay chạy worker root.

## 2. Nối riêng qua Tailscale

Cài/đăng nhập Tailscale trên hai máy theo chính sách của bạn; bật HTTPS cho tailnet.
Kiểm tra Serve config đang có trước khi thay đổi. Script sau **chỉ in lệnh**:

```bash
python scripts/worker/worker.py tailscale-command
# Tự chạy trên GPU host, sau khi kiểm tra cấu hình/grants:
tailscale serve --bg http://127.0.0.1:8501
tailscale serve status
```

Nếu đổi port, dùng port do script in ra. Giới hạn grants/ACL cho server Label-X
truy cập worker. **Không dùng Funnel, không publish port lên 0.0.0.0**, không bỏ
Bearer token. Xem [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve).
Compose chỉ publish **127.0.0.1:port**; HTTPS do Serve kết thúc ở máy GPU.

Trên **server Label-X**, cấu hình `.env` (các giá trị dưới đây chỉ minh họa):

```dotenv
GPU_WORKER_ALLOWED_HOSTS=gpu-host.your-tailnet.ts.net
GPU_WORKER_CREDENTIALS={"gpu-primary":"<token-that-matches-GPU-host>"}
```

Lấy token bằng trình soạn thảo local từ `.cache/gpu-worker/worker.env` rồi chuyển
qua kênh quản lý secret của bạn. Không commit file hoặc dùng token minh họa.
Restart backend và Celery sau đổi env; apply migration mới theo quy trình deploy.
Admin toàn hệ thống → `/configuration/guidelines` → **GPU Worker** → nhập URL
`https://gpu-host.your-tailnet.ts.net`, chọn alias `gpu-primary`, lưu rồi probe.
Server kiểm tra online, CUDA, version, checksum và đủ 10 lớp trước run/shard.
Đăng ký artifact bằng `manage.py check_detector --register` có chủ đích; sau đó
vào **Models & Guidelines → Mô hình → chỉnh Detector**, chọn artifact đã đăng ký
và lưu để tạo/phát hành ConfigVersion mới. Tại **Analysis**, chọn phiên bản vừa
phát hành để chạy; không nhập cấu hình model ở Analysis. Checkpoint không cần
nằm trên server. Run cũ giữ nguyên model/ConfigVersion đã ghim.

Đổi máy GPU: cấu hình máy mới/token/allowlist, restart các process server rồi lưu
revision UI mới. Run cũ giữ revision cũ; duy trì host/token cũ đến khi run cũ xong.

## 3. Vận hành và kiểm tra nhẹ

```bash
python scripts/worker/worker.py status
python scripts/worker/worker.py logs    # 100 dòng gần nhất, không follow
python scripts/worker/worker.py check   # health local có auth; không inference/ghi DB
python scripts/worker/worker.py stop    # chỉ project GPU, không xóa checkpoint/volume
python -m unittest discover -s scripts/worker/tests -v
```

`stop` không thay đổi Tailscale Serve, không dừng Label-X/CVAT/Redis/PostgreSQL.
Không chạy đồng thời các lệnh lifecycle/configure trên cùng profile.
Không dùng `docker compose config`/`inspect` để chia sẻ output vì có thể lộ secret.
Docker administrators có thể đọc container env; đây không phải secret vault.

Nếu start thất bại: kiểm tra Docker/GPU/image đã build, port trống, checkpoint đúng
và quyền đọc; xem `logs`. Health mismatch/401/timeout không được coi là ready.
Unit test không chứng minh GPU/Tailscale hai máy chạy thật. Manual test tiếp theo:
probe UI → run BDD100K locked → ngắt worker để kiểm tra lỗi/retry → đổi revision.

Các lệnh `make detector-*` cũ dành cho môi trường local backend; không dùng thay
cho script độc lập này. `scripts/dev-stack.sh` của PR #346 quản lý stack dev,
không quản lý project GPU Worker riêng.
