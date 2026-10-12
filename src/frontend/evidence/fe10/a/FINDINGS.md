# FE-10 nghiệm thu thị giác — nhóm A (Home, Quality Analysis, Review Center)

Người kiểm: phiên label-x-08 (cũ label-x-03). Ngày: 2026-10-12.

## Phạm vi và cách làm

- Mã nguồn: `origin/develop-fe` tại `2214235` (đã gồm #181, #182, #185; **chưa gồm #183 điều hướng và #177 FE-03**).
- Chạy `scripts/frontend/screenshot.sh --start` (mock auth + `mock-api.cjs`, không có backend thật). Vai trò `qalead` cho `/`, `/?view=summary`, `/analysis*`, `/review/rework`; vai trò `reviewer` cho `/review`, `/review/workspace`.
- Thiết kế: `docs/design/screens/preview.html#<Màn hình>` do Playwright chụp cùng viewport 1440 px và 390 px (Main, Dashboard, Snapshot, SnapshotHistory, AnalysisConfig, ExecutionHistory, ReviewQueues, ReviewWorkspace, ReworkTracking).
- Cả 9 route ở cả hai kích thước: **không có cuộn ngang trang** (script `shot.cjs` báo "không"). Ảnh 390 px xem trực tiếp cho `/`, `/analysis`, `/review`, `/review/workspace`; các ảnh 390 px còn lại chỉ kiểm bằng script (không cuộn ngang), chưa xem từng vùng.
- Chấm mức: **A** khớp (chỉ chỉnh nhỏ), **B** lệch nhẹ (sửa giao diện, giữ logic), **C** lệch lớn.
- Số liệu hiển thị trong ảnh là của `mock-api.cjs` (ví dụ Dataset tên "Urban Driving 2026Q3", mã `SNP-14`), không phải số liệu chuẩn; các lệch do dữ liệu giả được ghi riêng ở cuối.
- Biểu tượng chữ "N" tròn ở góc dưới trái ảnh là công cụ dev của Next.js, không thuộc giao diện.

## Khung chưa tính (chờ #183)

Khác biệt chung ở TopBar, ContextBar, FlowNav không tính vào mức từng route:

- ContextBar: thiết kế có mũi tên chọn ở chip Dataset, Quality Control Run, Phạm vi, biểu tượng khoá ở Snapshot và không có chip "Vai trò"; bản chạy thấy chip "Vai trò" ở bên phải, không có chip Phạm vi, không có mũi tên chọn ở các trang ngoài `/` (ví dụ `/analysis/config` hiện "Dataset mẫu #1").
- FlowNav: bản chạy có thêm chú thích dưới từng bước ("Chốt dữ liệu", "Chọn engine và ngưỡng"...) và đặt tên bước tiếng Việt ("Cấu hình phân tích", "Lịch sử thực thi") trong khi thiết kế ghi "Analysis Configuration", "Execution History" và không có chú thích; `/analysis/snapshots` có FlowNav còn thiết kế không có.

## Bảng tổng hợp

| Route | Mức | Lệch chính | Việc cần sửa |
| --- | --- | --- | --- |
| `/` Quality Control Home | B | Bảng Dataset thiếu chip phiên bản (`v1.4`...) và dòng phụ "chỉ xem"; cột hành động cuối luôn là mũi tên (thiết kế: đồng hồ cho bản chỉ xem, dấu cộng cho Dataset chưa có Run); chỉ 2 dòng thật còn thiết kế 4 dòng; mọi số tổng hợp là minh họa trộn với tên Dataset thật (có badge + 1 cảnh báo, đúng quy tắc); ở 390 px bảng cuộn ngang bên trong thẻ nên cột Frame, Run bị cắt khỏi tầm nhìn ban đầu | Thêm chip phiên bản khi có `taxonomy_version`/version, icon theo trạng thái; cân nhắc thẻ dòng ở 390 px (FE-10 hoặc FE-14) |
| `/?view=summary` Quality Summary | A | Khớp thiết kế về bố cục, số liệu chuẩn (12,500; 92.4%/95%; 384; 126), 6 engine, khối lượng review 124/50/18/242, 5 thanh loại lỗi. Nhưng có 1 cảnh báo đầu trang + 4 cảnh báo vùng (5), 6 badge "Dữ liệu minh họa": nặng hơn thiết kế. Theo Task trộn tên Task thật (`Task #118`) với số minh họa | Gộp cảnh báo (1 vùng đầu trang + các vùng chính); gắn nhãn minh họa cho cả dòng Theo Task |
| `/analysis` Snapshot | B | Bảng "Phạm vi kiểm tra" liệt kê cả Task lẫn từng Job (thiết kế: chỉ Task, mỗi dòng 1 ô chọn); khi chọn tất cả các ô bị khoá và mờ; ô seed bị khoá (thiết kế sửa được); số frame ở dòng Job không có dấu phân cách hàng nghìn (`3000`, `2900`) trong khi dòng Task có (`6,000`, `5,900`); thẻ "Snapshot đang dùng": hash revision dài 40 ký tự và thời gian `2026-10-08T07:30:00Z` hiển thị nguyên dạng chuẩn ISO (thiết kế: revision 6 ký tự, giờ `2026-10-04 06:50`); 1 cảnh báo ở form + 1 ở thẻ phải (2, hợp lý vì 2 vùng); ở 390 px tiêu đề cột "Người thực hiện · Giai đoạn" bị cắt trong khung cuộn | Định dạng số theo `toLocaleString('en-US')` cho mọi cột Frame; rút gọn revision (6 ký tự, tooltip bản đầy đủ); định dạng thời gian `YYYY-MM-DD HH:mm`; gom Job vào hàng mở rộng của Task |
| `/analysis/snapshots` | B | Có FlowNav (thiết kế không có, lịch sử chỉ mở bằng nút); thêm ô chọn Dataset trong thẻ (có chủ đích, đã khai); mã snapshot `SNP-14` không đệm số 0 như `SNP-014`; revision đầy đủ 40 ký tự; cột Quality Control Run luôn "—" kèm 1 cảnh báo (đúng); trạng thái dùng nhãn thật (Đã khoá/Thất bại) khác "Đang dùng/Đã thay thế" (đã khai) | Bỏ FlowNav hoặc xác nhận với PO; rút gọn revision; đệm mã `SNP-0xx` nếu backend trả số |
| `/analysis/config` (hiện trạng, #177 đang sửa) | C | Chưa dựng theo thiết kế: là form 3 ô chọn gốc của trình duyệt + ô JSON ngưỡng, không có bảng Engine kiểm tra (Bật/Engine/Cấu hình hiện tại, thanh bật tắt), không có khối Lấy mẫu, không có khối "Sẵn sàng chạy" (Snapshot, Phạm vi, Engine, Thời gian dự kiến, nút "Chạy phân tích"); nút "Lịch sử thực thi" đặt lạc dưới FlowNav; dùng viết tắt "QC run" (nút "Tạo QC run"); không có cảnh báo chưa kết nối (0) nên không rõ phần nào là giả | Dựng lại theo `AnalysisConfig.dc.html` (FE-03/#177), giữ logic tạo run; viết đầy đủ "Quality Control Run" |
| `/analysis/history` (hiện trạng, #177 đang sửa) | C | Bảng chỉ có 4 cột (Quality Control Run, Snapshot, Bắt đầu, Trạng thái) + nút "Chi tiết"; thiếu cột Coverage, thiếu panel chi tiết engine (thanh tiến độ từng engine, ghi chú, khối Candidate), thiếu nút "Chạy phân tích mới" ở đầu trang và "Chạy lại engine lỗi", "Mở Review Queues"; mã Run `QC-12` thay `#QC-091`; thời gian `07:30:00 8/10/2026` thay `2026-10-04 06:58`; viết tắt "QC run"/"QC-"; ô chọn Dataset gốc trình duyệt | Dựng theo `ExecutionHistory.dc.html` (FE-03/#177) |
| `/review` Review Queues | B | Vùng minh họa khớp thiết kế (3 thẻ, tìm kiếm, lọc ưu tiên/cảnh báo, chân trang); phía trên có khung chọn Dataset + "Mã QC Run (Run ID)" + nút "Tải hàng đợi" (dùng cho dữ liệu thật, thiết kế không có) và hộp thông tin xanh "Vui lòng nhập Mã QC Run..."; nhãn "Bộ dữ liệu (Dataset)" trộn Việt–Anh, "QC Run" viết tắt; thiếu badge "3 ảnh mẫu" ở đầu trang; thiếu dòng chú thích cuối thiết kế ("Dữ liệu và ảnh mẫu để đối chiếu...") | Gộp chọn Dataset/Run vào ContextBar (theo thiết kế) hoặc thu gọn khung; sửa nhãn "Mã Quality Control Run" |
| `/review/workspace` (không `frame_id`) | A | Khớp thiết kế 1:1 (Issue/Frame Review, annotation, bằng chứng, Guideline, 5 quyết định, loại lỗi, mức độ, lý do); gợi ý "Job 2272 · validation · <tên người dùng>" (thiết kế "An Nguyễn"); thêm badge + 1 cảnh báo (đúng quy tắc) và dòng chú thích | Không cần sửa |
| `/review/workspace?frame_id=428` (dữ liệu thật, chế độ chỉ xem) | B | Khung gần thiết kế nhưng: banner chỉ xem dùng thuật ngữ nội bộ ("LeaseGrant", "T-034 handoff"); callout vàng/xanh trong form quyết định nêu "snapshot revision", "pending_review", "in_review", "Plain Reviewer", đường dẫn API; có khối "Tra cứu Decision Case" (Issue ID, Rule ID, Case version bằng tiếng Anh) nằm giữa panel, trùng chức năng với "Case tương tự đã phân xử (0)"; còn nút +/-/Reset thu phóng, "Hoàn tất review frame", "Issue tiếp"; nhãn tiếng Anh "Annotation class", "Loại neo (Anchor)", "Rule: VEH-02"; canvas mock không phải ảnh thật | Việt hoá thông điệp, bỏ thuật ngữ nội bộ khỏi giao diện; đưa "Tra cứu Decision Case" sang Escalations hoặc thu gọn; rà nhãn tiếng Anh |
| `/review/rework` | A | Khớp thiết kế: 4 ô chỉ số (86; 5; 7; 86.0%), 3 tab (Chờ sửa 5, Chờ xác minh 7, Đã đóng 74), bảng 7 cột đúng thứ tự và dữ liệu; thêm badge + 1 cảnh báo (đúng quy tắc) | Không cần sửa |

## Việc làm theo thứ tự ưu tiên

1. `/analysis/config` và `/analysis/history` (mức C): dựng theo thiết kế, đã có #177.
2. Chuẩn hoá định dạng dữ liệu dùng chung (ảnh hưởng nhiều route): số có dấu phân cách hàng nghìn, thời gian `YYYY-MM-DD HH:mm`, revision 6 ký tự, mã `SNP-0xx`.
3. `/analysis` bảng phạm vi theo Task (gom Job) và seed sửa được.
4. `/review/workspace` có `frame_id`: bỏ thuật ngữ nội bộ khỏi banner và form quyết định.
5. `/review`: thu gọn khung chọn Dataset/Run; viết đầy đủ "Quality Control Run".
6. `/` và Summary: chip phiên bản, icon hành động; gộp cảnh báo ở Summary.

## Giới hạn

- Chưa có backend thật nên số liệu, mã, thời gian là của mock-api.
- Chưa xem từng vùng ở ảnh 390 px của `/?view=summary`, `/analysis/snapshots`, `/analysis/config`, `/analysis/history`, `/review/rework` (chỉ kiểm không cuộn ngang).
- Chưa chạy Playwright cho 7 vai trò và các trạng thái rỗng, lỗi, tải của từng route trong đợt này; các trạng thái đó đã được QA từng PR trước.
- Chụp trước khi #183 merge; cần chụp lại phần khung sau khi merge.

## Ảnh (19 tệp, `impl-*` là bản chạy, `design-*` là thiết kế)

`impl-home-1440`, `impl-summary-1440`, `impl-analysis-snapshot-1440`, `impl-analysis-snapshots-1440`, `impl-analysis-config-1440`, `impl-analysis-history-1440`, `impl-review-1440`, `impl-review-workspace-sample-1440`, `impl-review-workspace-real-1440`, `impl-review-rework-1440`, `impl-home-390`, `impl-summary-390`, `impl-analysis-snapshot-390`, `impl-review-390`, `impl-review-workspace-sample-390`, `impl-review-rework-390`, `design-snapshot-1440`, `design-analysis-config-1440`, `design-execution-history-1440`.
