# scripts — công cụ dev, CI và tài liệu

| Đường dẫn | Dùng cho | Gọi từ |
|---|---|---|
| `init-develop-environment.{sh,ps1,mk}` | Bootstrap máy dev và toàn bộ target Make | `Makefile`, CI `framework` |
| `dev-stack.sh` | Bật/dừng cả stack dev không CVAT, `refresh` nạp lại code sửa từ Windows | `make up`, `make down`, `make refresh`, `make status` |
| `validate-framework.py`, `kit_html.py` | Kiểm cấu trúc agentic-sdlc-kit (`.agent/`, `docs/`); đường dẫn cố định theo kit | `make validate-kit`, CI |
| `ci/` | Quality gate, render test plan, kiểm file riêng của agent, xuất evidence (+ `ci/tests/`) | `ci.yml`, `cd.yml`, `phase-testing.yml` |
| `development/` | Môi trường dev, CVAT local, nạp dữ liệu mẫu, audit annotation, `m03_readiness.py` (+ `development/tests/`) | `make cvat-*`, `make env`, CI |
| `frontend/` | Chạy và kiểm tra giao diện không cần backend — xem `frontend/README.md` | Thủ công |
| `srs/` | Sinh `docs/01-business/*.html` từ SRS LaTeX | CI kiểm bản sinh khớp bản commit |
| `worker/` | GPU Worker độc lập: cấu hình checkpoint/token, build, start/stop, health; không cần backend | PowerShell/Bash/Python — xem `worker/README.md` |
| `archive/<task>/` | Script dùng một lần của task đã đóng (M-02, T-018, T-039, T-046, M-04); giữ để chạy lại bằng chứng trong báo cáo `.agent/reports/` | Thủ công |

Script mới dùng một lần cho task nào thì để ở `archive/<task>/`, không để trong `development/`.
