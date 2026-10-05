---
id: labelx-environment-setup
title: Hướng dẫn khởi tạo môi trường phát triển LabelX
type: reference
domain: development
module: repository
tags: [onboarding, environment, windows, ubuntu, wsl]
priority: 1
---
# Khởi tạo môi trường phát triển LabelX

Hướng dẫn dành cho dev chưa có môi trường. Chọn **Windows** hoặc **Ubuntu/WSL** dưới đây. Cần mạng để tải công cụ, dependency và Docker image. Máy Windows phải đáp ứng yêu cầu Docker Desktop; Ubuntu được hỗ trợ: 22.04, 24.04, 26.04.

## 1. Make, Makefile và Bash khác nhau thế nào?

| Tên | Ý nghĩa | Có cần trước khi khởi tạo? |
|---|---|---|
| Make | Chương trình chạy các target như `make dev-backend` | Không. Windows chạy PowerShell; Ubuntu/WSL chạy Bash trực tiếp |
| Makefile | File chứa danh sách lệnh cho Make; không phải phần mềm để cài | Đã nằm ở root project, include `scripts/init-develop-environment.mk` |
| Bash | Shell chạy file `.sh`, thường có sẵn trên Ubuntu/WSL | Có nếu chọn hướng Ubuntu/WSL; không phụ thuộc Make |
| PowerShell | Shell chạy file `.ps1`, có sẵn trên Windows | Có nếu chọn hướng Windows |

**Thiếu Make không làm Bash mất khả năng chạy script.** Không chạy file `.mk` bằng Bash hoặc PowerShell. Windows chưa có Bash dùng `.ps1`; không cần cài Git Bash chỉ để setup.

## 2. Lấy source khi chưa có Git

Nhờ nhóm cung cấp ZIP source, giải nén vào thư mục của bạn; ví dụ `D:\label-x` trên Windows hoặc `~/label-x` trên Ubuntu. Thư mục đó phải có `src/`, `scripts/`, `infrastructure/` và các lockfile. Khi script cài Git xong, dùng repository URL thật do nhóm cung cấp để clone cho công việc commit/PR. ZIP không có lịch sử Git.

Nếu Git đã có, clone bằng URL nhóm cung cấp rồi chuyển terminal vào root project. Các lệnh bên dưới chạy ở **root project**, không phải trong `scripts/`.

## 3. Windows: khởi tạo bằng PowerShell, không cần Make/Bash

Mở PowerShell bằng tài khoản dev bình thường. Chỉ chấp thuận yêu cầu Administrator của installer khi cần; không cần chạy cả project với quyền Administrator.

```powershell
cd D:\label-x
# Xem kế hoạch, không cài hay sửa gì:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\init-develop-environment.ps1 -Mode Plan
# Cài công cụ thiếu và khởi tạo project:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\init-develop-environment.ps1 -InstallGlobal
```

`-InstallGlobal` cho phép cài Git, Node.js LTS nếu thiếu hoặc Node <22, uv, Docker Desktop qua WinGet. Nếu chưa có WinGet, script thử khôi phục bằng module Microsoft.WinGet.Client ở phạm vi người dùng. Installer có thể yêu cầu quyền quản trị hoặc khởi động lại. Nếu chính sách công ty chặn WinGet/PowerShell, nhờ quản trị viên cấp công cụ; script không vượt chính sách đó.

`-ExecutionPolicy Bypass` chỉ áp dụng cho tiến trình PowerShell này, không đổi chính sách toàn máy. Chỉ dùng với source đã kiểm tra của nhóm. Chính sách Group Policy vẫn có thể chặn; khi đó nhờ quản trị viên hỗ trợ.

Script thử mở Docker Desktop và chờ tối đa 120 giây. Nếu là lần chạy đầu, hoàn thành bước khởi tạo của Docker Desktop, chọn **Linux containers**, bật backend WSL2 nếu máy dùng WSL2. Nếu Docker yêu cầu bật virtualization/WSL hoặc reboot, thực hiện rồi chạy lại cùng lệnh. Script không tự bật tính năng Windows hay tự reboot.

Khi công cụ đã có, lần sau không cần `-InstallGlobal`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\init-develop-environment.ps1
# Kiểm tra môi trường đã cài, không cài/migrate/build lại:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\init-develop-environment.ps1 -Mode Check
```

Đợi dòng `SETUP PASSED` mới coi quá trình setup đã thành công. `CHECK PASSED` kiểm tra công cụ, dependency cần thiết, kết nối dịch vụ, Django check và migrations; không thay thế frontend build hoặc toàn bộ kiểm thử dự án.

## 4. Ubuntu hoặc WSL: khởi tạo bằng Bash, không cần Make

Nếu đã có Ubuntu, mở Terminal. Nếu Windows chưa có WSL mà muốn phát triển worker theo Linux, mở PowerShell **Administrator** và cài Ubuntu:

```powershell
wsl --install -d Ubuntu
```

Khởi động lại nếu Windows yêu cầu, mở ứng dụng Ubuntu, tạo tài khoản Linux. Cài/mở Docker Desktop trên Windows theo mục 3 hoặc hướng dẫn chính thức; vào **Settings → Resources → WSL Integration**, bật cho Ubuntu. Chỉ cài WSL chưa cung cấp Docker Desktop. Script Ubuntu không cài Docker Engine thứ hai trong WSL.

Trong Ubuntu/WSL, dùng checkout riêng ở thư mục Linux, ví dụ `~/label-x`; tránh dùng chung `.venv` và `node_modules` với checkout Windows.

```bash
cd ~/label-x
bash scripts/init-develop-environment.sh --plan
bash scripts/init-develop-environment.sh --install-global
```

Ubuntu đã có Bash. Nếu đang gõ `bash` ở PowerShell và bị báo không tìm thấy, chọn script Windows hoặc cài/mở WSL trước. Không cần Make hay `chmod +x` cho lệnh `bash scripts/...sh`.

Script dùng `sudo` để cài Git, curl, Make và công cụ build qua apt; cài Node 22 bằng nvm nếu thiếu/phiên bản quá thấp; cài uv trong tài khoản dev. Trên Ubuntu chạy trực tiếp, script cài Docker Engine + Compose từ repository chính thức nếu Docker chưa có. Script dừng khi thấy package Docker cũ xung đột, không tự gỡ chúng. MacOS và distro khác chưa có bootstrap tự động.

Trên Ubuntu trực tiếp, Docker mới cài có thể yêu cầu cấp quyền socket. Nếu Docker báo permission denied, quản trị viên có thể cấu hình theo [hướng dẫn Docker](https://docs.docker.com/engine/install/linux-postinstall/). Cách phổ biến, chỉ dùng khi bạn chấp thuận quyền quản trị máy thông qua nhóm Docker:

```bash
sudo usermod -aG docker "$USER"
# Đăng xuất/đăng nhập lại để nhận quyền, rồi:
docker info
bash scripts/init-develop-environment.sh --install-global
```

Script không tự thêm tài khoản vào nhóm Docker. Không chạy toàn bộ script bằng `sudo`, vì sẽ cài dependency và tạo file của project cho root.

Khi đã có công cụ:

```bash
bash scripts/init-develop-environment.sh
bash scripts/init-develop-environment.sh --check
```

Make là tiện ích **tùy chọn**. Nếu chỉ thiếu Make và muốn dùng các target hằng ngày:

```bash
sudo apt-get update
sudo apt-get install -y make
make help
```

## 5. Script cài gì, theo thứ tự nào?

| Phạm vi | Việc làm |
|---|---|
| Công cụ máy/tài khoản dev | Git, Node ≥22/npm, uv, Docker/Compose; Ubuntu thêm Make/build tools. Cài khi chọn InstallGlobal/--install-global, giữ công cụ hiện có đạt yêu cầu |
| Python người dùng | uv tải/quản lý Python 3.12; không thay Python hệ thống |
| Kiểm tra project | Đủ lockfile; không dùng `.venv` của OS khác; không có override trỏ sang dịch vụ khác hoặc Docker remote |
| Cấu hình project | Tạo backend `.env`, frontend `.env.local` từ `.env.example` nếu thiếu; secret mới ngẫu nhiên; file đã có được giữ nguyên |
| Dependency project | `uv sync --frozen --python 3.12` trong backend; `npm ci` trong frontend. npm ci dựng lại node_modules theo lockfile; lockfile không cập nhật |
| Dịch vụ local | Compose bật PostgreSQL 17, Redis 7, SeaweedFS; đợi healthy, chạy job tạo ba S3 bucket |
| Kiểm chứng | Kết nối PostgreSQL/Redis và ba bucket qua settings của Django, chạy migrations và Django check, build frontend |

Setup hỗ trợ cấu hình Compose local có trong repo. Nếu `.env` đang trỏ database/storage khác hoặc frontend API khác, script dừng để bạn kiểm tra, không tự ghi đè hay migrate sang môi trường đó. Cổng local: 5432 (PostgreSQL), 6379 (Redis), 9000 (S3), 8000 (API khi chạy), 3000 (frontend khi chạy).

Compose không có CVAT. Setup không tạo tài khoản admin, reference, model artifact hoặc quyền CVAT. Nhóm phải cấp thông tin CVAT/model riêng. Credential Compose là credential dev local, không dùng cho production. Docker volume và `.env` được giữ khi chạy lại; migrations có thể thay schema **database local**.

## 6. Chạy ứng dụng sau khi setup

Trên Windows, mở hai terminal ở root project:

```powershell
# Terminal 1
cd src\backend
uv run --frozen python manage.py runserver 127.0.0.1:8000
```

```powershell
# Terminal 2
cd src\frontend
npm.cmd run dev
```

Windows chỉ phù hợp phát triển API/frontend trực tiếp. Celery không hỗ trợ Windows; để phát triển worker dùng Ubuntu/WSL. Không coi worker `--pool=solo` trên Windows là môi trường được bảo đảm.

Trên Ubuntu/WSL, mở ba terminal:

```bash
make dev-backend
make dev-worker
make dev-frontend
```

Nếu chưa cài Make, dùng lệnh tương đương trong từng thư mục:

```bash
# Terminal 1, từ root
cd src/backend && uv run --frozen python manage.py runserver 127.0.0.1:8000
# Terminal 2, từ root
cd src/backend && uv run --frozen celery -A config worker -l info
# Terminal 3, từ root
cd src/frontend && npm run dev
```

API docs: `http://localhost:8000/api/docs/`. Frontend: `http://localhost:3000`. Khi cần tài khoản Django admin, chạy thủ công `uv run --frozen python manage.py createsuperuser` trong backend. Kiểm thử đầy đủ trên Ubuntu/WSL: `make check`; bộ kiểm thử setup riêng: `node --test scripts/development/tests/*.test.cjs` từ root.

## 7. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `make: command not found` | Chạy `.ps1`/`bash ...sh` trực tiếp; Ubuntu muốn Make thì cài bằng apt ở mục 4 |
| WinGet không chạy/installer yêu cầu reboot | Khởi động lại hoặc mở terminal mới, chạy lại; nếu WinGet recovery thất bại, nhờ IT cài App Installer/các package chính thức |
| Có Docker nhưng `docker info` lỗi | Mở Docker Desktop, hoàn thành first-start, bật Linux containers/WSL Integration; Ubuntu kiểm tra service/quyền socket |
| Cổng 5432/6379/9000 đã dùng | Xác định dịch vụ đang dùng cổng trước; không tự tắt database của project khác. Nếu cần đổi cổng, cập nhật Compose và cấu hình tương ứng, setup hiện chỉ hỗ trợ bundle mặc định |
| `.venv` thuộc OS khác | Dùng checkout riêng; hoặc tự đổi tên `.venv` thành `.venv.backup` trong backend rồi chạy lại. Không xóa nếu chưa biết dữ liệu trong đó |
| `.env` còn `DJANGO_SECRET_KEY=change-me` | Giữ bản backup riêng tư, tự cập nhật secret ngẫu nhiên hoặc đổi tên `.env` rồi chạy setup để tạo file mới; chuyển các cấu hình cần giữ vào file mới |
| Dependency/download/build thất bại | Kiểm tra mạng/proxy/quyền ghi; chạy lại cùng lệnh. Không coi Plan hoặc chỉ cài package thành công là setup xong |
| Thiếu Ground Truth/CVAT/model | Nhóm dự án phải cấp; script môi trường không tự tạo dữ liệu chuẩn hay quyền truy cập |

Không commit `.env`, `.env.local`, token hoặc các bản backup chứa secret. Không chạy `make infra-reset` trừ khi chủ ý xóa dữ liệu dev: lệnh đó xóa Docker volumes. `make infra-down` chỉ dừng hạ tầng và giữ dữ liệu.

## 8. File và nguồn hướng dẫn

- [Script Windows](scripts/init-develop-environment.ps1), [script Ubuntu/WSL](scripts/init-develop-environment.sh), [target Make](scripts/init-develop-environment.mk).
- [WinGet installation/recovery](https://learn.microsoft.com/en-us/windows/package-manager/winget/), [WinGet install](https://learn.microsoft.com/en-us/windows/package-manager/winget/install).
- [Docker Desktop Windows](https://docs.docker.com/desktop/setup/install/windows-install/), [Docker WSL Integration](https://docs.docker.com/desktop/features/wsl/), [Docker Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
- [Cài WSL](https://learn.microsoft.com/en-us/windows/wsl/install), [uv](https://docs.astral.sh/uv/getting-started/installation/), [nvm](https://github.com/nvm-sh/nvm), [Celery platform support](https://docs.celeryq.dev/en/stable/faq.html#does-celery-support-windows).

`scripts/Makefile` được đổi tên thành `scripts/init-develop-environment.mk`; `Makefile` gốc vẫn có tên chuẩn để GNU Make nhận diện. Tham chiếu tên cũ trong quyết định đã phê duyệt như DEC-001 là dấu vết lịch sử, không phải đường dẫn hiện tại.
