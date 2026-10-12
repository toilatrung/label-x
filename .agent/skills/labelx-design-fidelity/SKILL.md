---
name: labelx-design-fidelity
description: Bắt buộc dùng khi dựng, sửa hoặc đánh giá bất kỳ màn hình frontend LabelX nào. Ép giao diện Next.js khớp 1:1 với bản thiết kế chuẩn trong docs/design/screens (24 màn hình .dc.html) và Design System lx-*; chức năng chưa có backend vẫn dựng đủ giao diện kèm cảnh báo "Chức năng vẫn chưa được kết nối với server". Dùng cùng labelx-design.
---

# LabelX design fidelity

Mục tiêu: giao diện chạy thật (`src/frontend`) phải **trông và hoạt động như bản thiết kế** trong `docs/design/screens/`. Không "diễn giải lại", không tự chế layout. `labelx-design` cho nguyên tắc chung; skill này cho **quy trình bắt buộc và tiêu chí đạt/không đạt**.

## Nguồn chuẩn (đọc trước khi viết dòng code UI nào)

1. Màn hình đích: `docs/design/screens/<Tên>.dc.html` (mỗi màn hình một file; mở bằng `docs/design/screens/preview.html` để xem tương tác). Dữ liệu minh họa: `review-data.js` và `defaults` trong chính file.
2. Khung dùng chung: `TopBar.dc.html`, `FlowNav.dc.html`, `ContextBarStates.dc.html`, `NavigationMenu.dc.html`.
3. Token và class: `docs/design/design-system/tokens.json`, `components/bundle.css`, README từng component. Bản frontend: `src/frontend/src/styles/tokens.css`, `labelx.css`. Hai bản phải trùng nhau; nếu thiếu class thì thêm vào Design System trước, rồi mới chép sang frontend.
4. Tài liệu: `docs/design/design-system.html`, `docs/design/README.html`.

Khi bản thiết kế và code khác nhau, **bản thiết kế đúng**, trừ khi có change request được duyệt.

## Bản đồ màn hình thiết kế → route frontend

| Thiết kế (`.dc.html`) | Route frontend | Ghi chú |
| --- | --- | --- |
| Main, Dashboard | `/` | Quality Control Home, Quality Summary |
| Snapshot, SnapshotHistory | `/analysis/snapshots` | bước 1; lịch sử mở bằng nút |
| AnalysisConfig | `/analysis/config` | bước 2 |
| ExecutionHistory | `/analysis/history` | bước 3 |
| ReviewQueues | `/review` | bước 1 |
| ReviewWorkspace | `/review/workspace` | bước 2, giữ nguyên Issue/Frame Review |
| ReworkTracking | `/review/rework` | bước 3 |
| Escalations | `/escalations` | một trang, các tab |
| PerformanceEvaluation, Benchmark, AuditSampling, Calibration | `/calibration/<performance|benchmark|audit-sampling|calibration>` | dropdown Calibration & Audit |
| QualityReport, QualityGate, ReleaseHistory | `/reports`, `/reports/gate`, `/reports/releases` | 3 bước |
| RulesThresholds | `/configuration/rules-thresholds` | |
| ModelsGuidelines | `/configuration/guidelines` | |
| WorkflowPermissions | `/configuration` | |
| ContextBarStates | `ContextBar` | mọi màn hình |

Route chưa tồn tại thì **tạo route** đúng bảng này, không gộp bừa vào trang khác.

## Quy trình bắt buộc cho mỗi màn hình

1. **Đọc** file `.dc.html` đích và liệt kê: vùng (header, tab, toolbar, bảng, panel, modal), cột bảng, nút, trạng thái rỗng/lỗi/đang tải, dữ liệu minh họa.
2. **Dựng đủ mọi vùng** trong danh sách đó với đúng class `lx-*`, thứ tự, nhãn tiếng Việt, icon. Không bỏ vùng nào vì "chưa có API".
3. **Nối dữ liệu thật** nơi API đã có. Nơi chưa có: xem mục "Chức năng chưa kết nối" bên dưới.
4. **So sánh** với thiết kế (mở `preview.html` cạnh trang chạy, hoặc chụp bằng Playwright ở 1440 px và 390 px). Ghi kết quả vào PR: bảng vùng đạt/lệch.
5. Chạy `node docs/design/tools/verify-design.cjs` nếu sửa `docs/design/`; chạy `make check` trước khi báo xong.

## Chức năng chưa kết nối server

Giao diện **luôn hoàn thiện**, kể cả khi backend chưa có. Với mọi chức năng, nút, tab, cột hoặc biểu đồ mà thiết kế có nhưng API chưa có:

- Vẫn dựng đúng như thiết kế, dùng dữ liệu minh họa lấy từ thiết kế (đã nhất quán giữa các màn hình).
- Hiển thị cảnh báo ngay trong vùng đó, đúng nguyên văn: **"Chức năng vẫn chưa được kết nối với server"**. Dùng một component duy nhất `NotConnectedNotice` (tạo ở `src/frontend/src/components/ui/`, class `lx-notice lx-notice--warning`, icon cảnh báo 16px, chữ không viết tắt). Một cảnh báo cho mỗi vùng, không rải từng ô.
- Hành động ghi (lưu, gửi, xác nhận, xuất) bị chặn có chủ đích: nút vẫn hiện, bấm ra cảnh báo trên, **không** gọi API giả, không báo thành công giả, không lưu vào localStorage như thể là dữ liệu thật.
- Dữ liệu minh họa phải có nhãn rõ (badge trung tính "Dữ liệu minh họa"), không để lẫn với số liệu thật.
- Đánh dấu trong code `// TODO(backend): <tên endpoint cần có>` và ghi vào blocker/report trong `.agent/` danh sách endpoint còn thiếu. Khi backend xong chỉ cần thay nguồn dữ liệu, không đụng layout.
- Ranh giới cứng giữ nguyên: adapter CVAT chỉ đọc; sửa annotation bằng deep link sang CVAT; quyền project/job kiểm ở API.

## Tiêu chí không đạt (reviewer phải chặn PR)

- Màu, bo góc, bóng, cỡ chữ hard-code thay vì token; bo tròn ở card/bảng/nút/input (chỉ badge 4px, chip pill, switch, avatar, dot, dropdown 6px).
- Dùng thư viện UI khác (MUI, shadcn, Ant, Tailwind component) hoặc class tự đặt thay cho `lx-*`.
- Thiếu thanh điều hướng graphite, context bar, FlowNav ở bước của flow, hoặc thêm hàng điều hướng thứ hai.
- Trạng thái chỉ bằng màu/chấm (trừ dot của Quality Control Run), viết tắt QC/IoU/GT, dấu chấm than, emoji, gradient, glow.
- Bỏ vùng có trong thiết kế; đổi thứ tự cột; đổi nhãn nút; mất trạng thái rỗng/lỗi/tải.
- Hiển thị dữ liệu giả như dữ liệu thật, hoặc báo "thành công" cho thao tác chưa gọi server.
- Số liệu lệch bộ dữ liệu chuẩn trong `labelx-design` (12,500 frame; coverage 92.4%...).
- Không có bằng chứng so sánh với thiết kế trong PR.

## Kiểm toán màn hình hiện có (để thiết kế lại)

Khi được yêu cầu liệt kê màn hình đã hoàn thiện cần làm lại, với **từng** màn hình trong bảng bản đồ:

1. Route tồn tại? Có đăng nhập/phân quyền đúng?
2. Chức năng đã nối API thật chưa (ghi endpoint)?
3. Đối chiếu với `.dc.html`: vùng thiếu, vùng lệch, vi phạm "Tiêu chí không đạt".
4. Xếp mức: **A** khớp thiết kế (chỉ chỉnh nhỏ), **B** chạy được nhưng lệch layout (thiết kế lại giao diện, giữ logic), **C** chưa có hoặc sơ sài (dựng mới theo thiết kế + `NotConnectedNotice`).
5. Ghi kết quả thành báo cáo HTML trong `.agent/reports/` từ `.agent/templates/implementation-report-template.html` (không tạo `.md`), một bảng: màn hình | route | thiết kế | trạng thái API | mức A/B/C | việc cần làm | task đề xuất. Chạy `make validate-kit`. Chỉ làm việc có task được duyệt: đề xuất task, chưa tự sửa code khi chưa được duyệt.
