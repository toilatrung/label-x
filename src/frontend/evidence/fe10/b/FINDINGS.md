# FE-10 nghiệm thu thị giác, nhóm B

Phạm vi: `/escalations` (3 tab), `/calibration/{performance,benchmark,audit-sampling,calibration}`, `/reports`, `/reports/gate`, `/reports/releases`, `/configuration`, `/configuration/rules-thresholds`, `/configuration/guidelines`.
Nền: `origin/develop-fe` tại `2387fca` (đã gồm #183). Chỉ evidence, không đổi mã.

## Cách làm và giới hạn

- Chụp bằng `scripts/frontend/screenshot.sh --role qalead --start` (mock auth + mock-api) ở 1440 px và 390 px, thêm một lượt Playwright chụp tab không mặc định ở 1440. Đo cuộn ngang bằng `scrollWidth` của trang.
- Đối chiếu với thiết kế **bằng nội dung `docs/design/screens/*.dc.html`** (vùng, cột, nhãn, số liệu), **không so điểm ảnh với `preview.html`** (chưa chụp preview).
- Chỉ vai trò `qalead`; 6 vai trò khác chưa chụp (quyền menu đã kiểm ở QA #183).
- Dữ liệu là dữ liệu giả lập của `mock-api.cjs`, không phải backend thật.
- Tiết lộ xung đột: người chụp là tác giả FE-07 (4 màn `/calibration/*`) và FE-08 (`/reports*`); mức A cho các route này là tự đánh giá, nên có người khác xác nhận lại.
- Ảnh trong thư mục này (20 ảnh, đã nén PNG 128 màu) là bản chọn lọc; ảnh đầy đủ nằm ở `src/frontend/evidence/shots/qalead/` (đã gitignore).

## Bảng theo route

| Route | Mức | Lệch so với thiết kế | Việc cần sửa |
| --- | --- | --- | --- |
| `/escalations` tab Guideline Gaps | A | Khớp: tiêu đề, mô tả, nút "Tạo Guideline Gap", đếm trên tab, 5 cột Mã / Nội dung còn thiếu / Quy tắc / Case liên quan / Trạng thái, nút mũi tên. Có SampleDataBadge + 1 NotConnectedNotice | Không |
| `/escalations` tab Decision Cases | A | Khớp 5 cột Mã / Tình huống / Quy tắc / Quyết định / Phiên bản. 1 notice | Không |
| `/escalations` tab Adjudication | B | Thiết kế: danh sách "Chờ phân xử 18 case" (4 mục, "Xem thêm") + khung chi tiết luôn hiện (bảng quyết định reviewer, bằng chứng, hướng dẫn liên quan, 3 lựa chọn "Kết luận phân xử"). Thực tế: danh sách 6 case có thêm ô "Lọc theo Quality Control Run ID" + "Áp dụng" và nút "Mở phân xử" mỗi dòng; khung phải chỉ có dòng "Chọn một issue ở danh sách bên trái..." nên không thấy bố cục phân xử cho tới khi chọn; thêm thẻ "Tra cứu Decision Case" không có trong thiết kế; nhãn tiếng Anh thô ("engine · escalated", "critical", "medium", "Thiếu box · critical"); không có cảnh báo (tab dùng API thật) | Khi chưa chọn issue, hiện khung chi tiết theo thiết kế với dữ liệu minh họa + SampleDataBadge + 1 notice; việt hoá trạng thái/mức độ; ghi rõ vùng thêm (lọc Run, tra cứu) trong bảng lệch của PR |
| `/calibration/performance` | A* | Khớp 4 metric, bảng 3 luồng lấy mẫu, danh sách việc hiệu chỉnh, 2 select (khoá, có notice). 390 px: bảng cuộn trong thẻ | Không (1 notice cho cả trang thay vì mỗi vùng; chấp nhận) |
| `/calibration/benchmark` | A* | Khớp bảng 3 phiên bản, panel v1.2, callout, 2 nút | Không |
| `/calibration/audit-sampling` | A* | Khớp 2 tab, 4 trường, bảng 4 frame; tab rủi ro đã kiểm ở mã nguồn | Không |
| `/calibration/calibration` | A* | Khớp 2 tab, bảng reviewer, chân bảng | Không |
| `/reports` | B | Nội dung khớp (4 metric, 3 tab, menu xuất). **Lỗi bố cục toàn cục**: trang cuộn ngang 1514/1440 và 525/390 do tooltip FlowNav (xem X-1); ở 390 px FlowNav bị cắt chữ và chồng bước (X-2) | Sửa X-1, X-2 |
| `/reports/gate` | B | Nội dung khớp (6 điều kiện, panel phê duyệt/waiver, 2 notice cho 2 vùng). Cuộn ngang 1533/1440, 544/390 (X-1, X-2) | Sửa X-1, X-2 |
| `/reports/releases` | B | Nội dung khớp (bảng 4 lần phát hành, manifest v1.3, 2 notice). Cuộn ngang 1510/1440, 522/390 (X-1, X-2) | Sửa X-1, X-2 |
| `/configuration` (Workflow và Permissions) | B | Thiết kế: ma trận 8 chức năng (Quality Summary, Quality Analysis, Review Queues và Workspace, Rework, Adjudication, Calibration và Audit, Phê duyệt phát hành, Configuration) với chữ quyền như "Xem", "Đầy đủ", "Chạy / xem", "Giới hạn"; 4 công tắc quy tắc (Không tự review, Ghi đè Super Admin phải có lý do, Mọi thao tác ghi nhật ký kiểm toán, Yêu cầu xác minh sau khi sửa). Thực tế: 7 hàng khác (Xem Snapshot và lịch sử, Tạo Snapshot, Tạo QC run...) chỉ "Được phép/Không"; ô "Không" cũng tô xanh như "Được phép" (trạng thái chỉ khác nhau ở chữ, màu gây hiểu nhầm); 3 công tắc khác (Không tự duyệt, Lease frame, Adapter CVAT chỉ đọc) kèm badge "ĐÃ ÁP DỤNG"; viết tắt "QC run" | Đổi hàng/nhãn theo thiết kế khi API cho phép, hoặc dựng đủ ma trận thiết kế bằng dữ liệu minh họa + notice; ô "Không" dùng màu trung tính; bỏ viết tắt |
| `/configuration/rules-thresholds` | B | Ba tab đúng thiết kế (5 quy tắc, 5 ngưỡng, chính sách lấy mẫu), nút "Lưu thành v8", "Cấu hình hiện tại v7", 1 notice mỗi tab. Lệch: hai khối API thật ("Ngưỡng kiểm tra engine", "Mapping guideline") lặp lại dưới **cả 3 tab** dù không thuộc tab nào trong thiết kế; callout "Trạng thái trong cấu hình" dùng nền đỏ (đỏ chỉ dành cho trạng thái chặn); viết tắt "IoU", "VLM", "QC run" trong bảng và chân bảng | Đưa hai khối thật vào một tab/khu riêng (hoặc chỉ ở tab phù hợp); callout dùng `lx-callout--info`; viết đầy đủ Intersection over Union, mô hình thị giác – ngôn ngữ, Quality Control Run |
| `/configuration/guidelines` | B | Hai tab đúng thiết kế (3 mô hình, 3 phiên bản guideline), chân bảng, 1 notice mỗi tab. Lệch: khối "Rule guideline" (API thật) thêm dưới cả hai tab; cột "Mục" hẹp làm chữ ngắt dòng ("Phương / tiện") | Tách khối thật, nới cột Mục |

`A*` = tự đánh giá của tác giả (xem phần giới hạn).

## Finding toàn cục

| # | Mức | Mô tả | Việc cần sửa |
| --- | --- | --- | --- |
| X-1 | major | Mọi trang có FlowNav (reports, analysis, review) cuộn ngang cả ở 1440 và 390. Đo được `scrollWidth` 1510–1544/1440 và 492–618/390; khi tắt `.lx-flow__arrow::after` (tooltip của mũi tên Bước trước/sau) còn 1440/1440 ở 1440 px và 390–397 ở 390 px. Tooltip nằm ngoài mép phải nên làm rộng trang dù ẩn (`opacity: 0`). `/escalations`, `/calibration/*`, `/configuration*` không có FlowNav nên không bị | Neo tooltip của mũi tên sau vào trong (`right: 0; left: auto`) hoặc `overflow` phù hợp, rồi chạy lại `screenshot.sh` (không còn "CÓ" ở cột cuộn ngang) |
| X-2 | minor | Ở 390 px FlowNav quá chật: nhãn bước 1 và 2 bị cắt ("Qual Repo", "Quali Gate"), các bước chồng lên nhau, mũi tên sau tràn ra ngoài (còn dư 6–7 px sau khi sửa X-1) | Xuống dòng hoặc ẩn nhãn các bước không chọn ở màn hẹp |
| X-3 | observation | Ở 390 px TopBar (3 hàng) + ContextBar (4 hàng) chiếm khoảng 380/844 px chiều cao trước khi tới nội dung | Cân nhắc gộp ContextBar thành một hàng cuộn ngang hoặc thu gọn ở màn hẹp |
| X-4 | observation | Tab dài ở 390 px bị cắt chữ ("Adju…", "Nguyên nhân…") nhưng cuộn ngang trong thanh tab nên dùng được | Không chặn |
| X-5 | observation | Bảng có `min-width` cuộn ngang bên trong thẻ ở 390 px (đúng thiết kế); ma trận quyền ở `/configuration` hiện được ~3/6 cột trước khi cuộn | Không chặn |

## Danh sách ảnh (20)

`escalations-gaps-1440`, `escalations-adjudication-1440`, `escalations-390`, `calibration-performance-1440`, `calibration-performance-390`, `calibration-benchmark-1440`, `calibration-audit-sampling-1440`, `calibration-audit-sampling-390`, `calibration-calibration-1440`, `reports-1440`, `reports-390`, `reports-gate-1440`, `reports-gate-390`, `reports-releases-1440`, `configuration-1440`, `configuration-390`, `configuration-rules-thresholds-1440`, `configuration-rules-thresholds-390`, `configuration-guidelines-1440`, `configuration-guidelines-versions-1440`.
Ghi chú: ảnh 1440 của `/reports*` rộng hơn 1440 px vì chính lỗi X-1; ảnh `calibration-audit-sampling-390` chụp ở lượt chuẩn nhưng chưa được xem kỹ.
