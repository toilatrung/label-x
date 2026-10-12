Đã sửa FE-01 PR #181: M1 phục hồi số liệu chuẩn có SampleDataBadge/NotConnectedNotice, giữ Dataset/Task thật; M2 bỏ inline style FE-01, đồng bộ 3 CSS; M3 giữ TopBar/ContextBar/AppShell đúng develop-fe. F1 sync lặp giữ 1 notice; F2 dùng link Reports/Gate/History/Review thật.

Dataset và Dataset 2 Tasks GET 200; Task #1 đã tải xong trước 8 ảnh live/preview API503 tại 1440/390; 0 ghi ngoài đăng nhập. Số liệu tổng hợp vẫn là minh họa có nhãn. Kiểm tra trước đó: make check 0 trước restore TopBar; sau restore FE-01 22/22 và build 0 (có act warnings).

Blocker: `.agent/reports/implementation/blocker-fe01-missing-aggregation-endpoints.html`. Nhờ FE10 PR #183 nối Overview Quality Summary tới `/?view=summary`. Kính nhờ leader chạy lại QA; nghiệm thu, CI mới và pixel 1:1 vẫn đang chờ.
