---
id: business-use-cases
title: Use case — SRS M13
type: reference
domain: business
module: use-cases
tags: [use-cases, actors, m13]
priority: 1
---

# Use case — SRS M13

## Purpose

Danh sách và đặc tả 14 use case của chức năng M13 (Reviewer Prioritization Assistant) trong LabelX. Sơ đồ use case, sequence diagram và state machine nằm trong [labelX.html](labelX.html) chương 4–5.

Nguồn chuẩn: [labelX.html](labelX.html) (bản HTML) và `docs/label-x_system-requirement-specification/` (bản LaTeX), SRS M13 v1.0, 05/10/2026. Khi có khác biệt, bản LaTeX là gốc; HTML được sinh lại bằng `python3 scripts/srs_tex2html.py`.

## Danh sách

| Mã | Tên | Actor chính | Ưu tiên | Mục tiêu |
|---|---|---|---|---|
| UC-01 | Tạo snapshot từ CVAT | QA Lead (chạy), QC Admin (cấu hình) | M | R-01 |
| UC-02 | Chạy phân tích nghi vấn | QA Lead (chạy), QC Admin (cấu hình) | M | R-01, R-02 |
| UC-03 | Chấm điểm và xếp hạng frame | Hệ thống | M | KPI-1 |
| UC-04 | Làm việc theo hàng đợi ưu tiên | Reviewer | M | KPI-2 |
| UC-05 | Xem bằng chứng và quyết định | Reviewer | M | R-02, KPI-2 |
| UC-06 | Chuyển cấp và phân xử | QA Lead | M | R-02 |
| UC-07 | Rework và kiểm lại sau sửa | Reviewer, Annotator | M | R-03 |
| UC-08 | Lập và khoá reference | QA Lead | M | R-04 |
| UC-09 | Đo Recall@20% | QA Lead | M | KPI-1, R-04 |
| UC-10 | Đo effort baseline/assisted | Product Owner | M | KPI-2, R-07 |
| UC-11 | Xem và xuất báo cáo hiệu quả | Product Owner, QA Lead | M | KPI-1, KPI-2 |
| UC-12 | Tra cứu guideline | Reviewer | S | R-02 |
| UC-13 | Quản lý quyền và audit | QC Admin | M | R-05 |
| UC-14 | Kiểm Quality Gate tối thiểu | QA Lead | S | R-03, R-06 |

## Đặc tả

### UC-01 · Tạo snapshot từ CVAT

| Mục | Nội dung |
|---|---|
| Actor | QA Lead (khởi tạo); QC Admin (cấu hình phạm vi, kết nối); CVAT (hệ thống nguồn). |
| Mô tả | Đọc annotation, metadata và ảnh của phạm vi đã chọn từ CVAT, chuẩn hoá, tính hash và khoá thành snapshot bất biến. |
| Tiền điều kiện | Token CVAT được cấu hình ở backend; actor có quyền chạy phân tích trên dataset (QA Lead) theo scope; phạm vi (project/task/job) đã chọn. |
| Luồng chính | • Actor chọn dataset và phạm vi, bấm *Tạo snapshot*. • Hệ thống đọc danh sách job, frame, annotation và ảnh qua CVAT API (chỉ đọc). • Hệ thống chuẩn hoá JSON annotation theo job, tính hash từng job và hash tổng. • Hệ thống đọc lại dấu thời gian/hash cập nhật của từng job để kiểm drift. • Không có drift: hệ thống lưu ảnh, checksum, assignee từng job, taxonomy và guideline version; khoá snapshot. • Hệ thống ghi audit và hiển thị snapshot với revision hash. |
| Luồng thay thế | **4a.** Có drift: hệ thống huỷ khoá, báo các job đã đổi, cho phép thử lại; không tạo snapshot một phần. **2a.** Annotation không phải Bounding box: bỏ qua, ghi số lượng vào báo cáo snapshot (ngoài phạm vi). |
| Ngoại lệ | CVAT không phản hồi hoặc từ chối quyền: snapshot ở trạng thái Failed, ghi lỗi, không ảnh hưởng snapshot cũ. Actor không có quyền trong scope: backend từ chối (403), ghi audit. |
| Hậu điều kiện | Snapshot bất biến, có hash; có thể chạy UC-02. |
| Yêu cầu | `FR-SNP-01`…`FR-SNP-08` |

### UC-02 · Chạy phân tích nghi vấn

| Mục | Nội dung |
|---|---|
| Actor | QA Lead (chạy); QC Admin (cấu hình engine, ngưỡng); Detector (hệ thống). |
| Mô tả | Chạy các engine MVP trên một snapshot, sinh candidate kèm evidence, cập nhật coverage ledger. |
| Tiền điều kiện | Snapshot đã khoá; cấu hình phân tích (engine, ngưỡng, seed, model artifact) có version. |
| Luồng chính | • Actor chọn snapshot và cấu hình, xem ước lượng thời gian và phạm vi áp dụng từng engine, bấm *Chạy*. • Hệ thống tạo QC Run (Queued), chia shard theo frame, đưa vào hàng đợi CPU/GPU. • Worker CPU chạy Schema/Taxonomy, Geometry, Duplicate/Overlap. • Worker GPU chạy Detector theo lô; worker CPU chạy matching với annotation. • Mỗi shard ghi candidate, evidence và cập nhật ledger (eligible/completed units) trong cùng transaction. • Khi mọi shard xong, hệ thống gộp candidate thành issue (dedup) và kích hoạt UC-03. |
| Luồng thay thế | **4a.** Detector lỗi trên một số frame: retry tối đa theo cấu hình; còn lỗi thì frame đó Failed cho engine này, run ở trạng thái Partial. **1a.** Không có Detector khả dụng: engine Mô hình độc lập Not checked; run vẫn chạy các engine khác. |
| Ngoại lệ | Actor huỷ run: dừng nhận shard mới, giữ kết quả đã xong, run Cancelled. Actor không có quyền chạy hoặc sửa cấu hình: backend từ chối (403). Metric engine: chỉ chạy khi có GT đã khoá cho phạm vi (B-05, B-20); thiếu GT thì Not checked, không hiển thị accuracy. |
| Hậu điều kiện | Run Completed/Partial/Failed/Cancelled; ledger phản ánh đúng phần chưa kiểm. |
| Yêu cầu | `FR-ENG-01`…`FR-ENG-10`, `FR-AGG-01`…`FR-AGG-06` |

### UC-03 · Chấm điểm và xếp hạng frame

| Mục | Nội dung |
|---|---|
| Actor | Hệ thống (tự động sau UC-02); QC Admin (chọn version công thức). |
| Mô tả | Tính điểm rủi ro $s(f)$ cho mọi frame trong snapshot, xếp hạng, lưu đóng góp từng candidate để giải thích. |
| Tiền điều kiện | Run ở trạng thái Completed hoặc Partial; công thức điểm có version đã kích hoạt. |
| Luồng chính | • Hệ thống tính xác suất hiệu chỉnh $q_i$ cho từng issue theo nhóm lỗi (mục tương ứng trong labelX.html). • Hệ thống tính $s(f)$ theo công thức (mục tương ứng trong labelX.html), kể cả frame không có candidate (điểm nền). • Hệ thống sắp xếp giảm dần, phá hoà bằng khoá cố định, lưu rank và version. • Hệ thống chọn lát kiểm tra ngẫu nhiên độc lập với ranking (seed cố định). • Hệ thống đánh dấu frame chưa được engine bắt buộc kiểm (Not checked/Failed) để hiển thị riêng. |
| Luồng thay thế | **2a.** Run Partial: frame thiếu kết quả engine vẫn có điểm nhưng mang cờ "thiếu bằng chứng"; không được coi là điểm thấp an toàn. |
| Hậu điều kiện | Mỗi frame có đúng một (score, rank, score_version) cho run. |
| Yêu cầu | `FR-RNK-01`…`FR-RNK-09` |

### UC-04 · Làm việc theo hàng đợi ưu tiên

| Mục | Nội dung |
|---|---|
| Actor | Reviewer. |
| Mô tả | Reviewer nhận frame/issue theo thứ tự ưu tiên; hệ thống cấp lease để tránh trùng việc. |
| Tiền điều kiện | Đã có ranking; reviewer có quyền Review trong scope; frame không do reviewer gán nhãn. |
| Luồng chính | • Reviewer mở Review Queues, chọn hàng đợi *Theo rủi ro* hoặc *Kiểm tra ngẫu nhiên*. • Hệ thống hiển thị danh sách frame theo rank với số issue, nhóm lỗi, lý do xếp hạng. • Reviewer bấm *Bắt đầu review*; hệ thống cấp lease frame kế tiếp chưa có người giữ. • Hệ thống mở Review Workspace (UC-05) và bắt đầu ghi effort. |
| Luồng thay thế | **3a.** Frame kế tiếp do chính reviewer gán nhãn: hệ thống bỏ qua và cấp frame sau (self-review). **3b.** Lease hết hạn (thời hạn TBD-09, gia hạn khi có thao tác): frame trở về hàng đợi. **3c.** Hai reviewer cùng bấm: lease được cấp nguyên tử (một transaction, khoá dòng); người thứ hai nhận frame kế tiếp. **2a.** Hàng đợi rỗng hoặc mọi frame còn lại là self-review: hiển thị "không còn việc hợp lệ". |
| Hậu điều kiện | Frame ở trạng thái Đang review, có lease. |
| Yêu cầu | `FR-REV-01`…`FR-REV-04`, `FR-SEC-03` |

### UC-05 · Xem bằng chứng và quyết định

| Mục | Nội dung |
|---|---|
| Actor | Reviewer. |
| Mô tả | Reviewer xem frame với annotation hiện tại và đề xuất của Detector, đọc evidence của từng issue, ra quyết định có lý do; có thể tạo issue mới cho lỗi không có candidate. |
| Tiền điều kiện | Reviewer giữ lease frame. |
| Luồng chính | • Hệ thống hiển thị ảnh, annotation (nét liền), dự đoán Detector (nét đứt), danh sách issue của frame. • Reviewer chọn issue; hệ thống hiển thị evidence (lớp, confidence, IoU, rule vi phạm), guideline liên quan và case tương tự. • Reviewer chọn *Xác nhận lỗi*, *Bác bỏ*, *Chưa chắc chắn* hoặc *Chuyển cấp trên*; với xác nhận chọn nhóm lỗi và mức độ. • Reviewer có thể bấm *Yêu cầu sửa* cho lỗi đã xác nhận (UC-07). • Reviewer đánh dấu frame *Đã review xong*; hệ thống lưu quyết định, actor, revision, lý do, thời gian; trả lease. |
| Luồng thay thế | **3a.** Lỗi không có candidate: reviewer bấm vào vùng ảnh/object để tạo issue thủ công (nguồn = reviewer). **3b.** Chuyển cấp trên: issue sang UC-06. |
| Ngoại lệ | Snapshot bị thay bởi revision mới trong lúc review: quyết định vẫn gắn revision cũ; hệ thống cảnh báo. Lease đã hết hạn hoặc đã cấp cho người khác: backend từ chối lưu, yêu cầu nhận lại frame. Reviewer là assignee của job tại snapshot (mở trực tiếp qua URL): backend từ chối lưu quyết định (self-review, B-12). |
| Ghi chú KPI | Chỉ lỗi thuộc E1–E3 được đối chiếu với reference để tính KPI. Cảnh báo cấu trúc, box thừa (BR-06), lỗi độ khít biên được ghi nhận nhưng không tính KPI. |
| Hậu điều kiện | Mọi issue của frame có quyết định hoặc đang chờ phân xử; effort được ghi. |
| Yêu cầu | `FR-REV-05`…`FR-REV-12`, `FR-EVL-06` |

### UC-06 · Chuyển cấp và phân xử

| Mục | Nội dung |
|---|---|
| Actor | QA Lead (adjudicator); Reviewer (người chuyển). |
| Mô tả | Phân xử issue chưa đủ căn cứ hoặc reviewer bất đồng; ghi Guideline Gap khi guideline thiếu. |
| Tiền điều kiện | Issue ở trạng thái Chuyển cấp trên hoặc Chưa chắc chắn. |
| Luồng chính | • QA Lead mở Escalations, chọn case. • Hệ thống hiển thị quyết định từng reviewer, evidence, rule áp dụng. • QA Lead chọn *Xác nhận lỗi*, *Bác bỏ* hoặc *Guideline còn thiếu*, chọn nhãn đúng và rule, nhập lý do. • QA Lead chọn *Tạo yêu cầu sửa* hoặc *Chỉ ghi nhận*. • Hệ thống lưu phân xử, lưu thành Decision Case (có version) để tra cứu ở UC-12. |
| Luồng thay thế | **3a.** Guideline còn thiếu: tạo Guideline Gap gắn rule; issue giữ trạng thái chờ đến khi guideline có version mới. |
| Hậu điều kiện | Issue có kết luận cuối hoặc gắn Guideline Gap. |
| Yêu cầu | `FR-ESC-01`…`FR-ESC-05` |

### UC-07 · Rework và kiểm lại sau sửa

| Mục | Nội dung |
|---|---|
| Actor | Reviewer (yêu cầu, xác minh); Annotator (sửa); CVAT. |
| Mô tả | Lỗi đã xác nhận được sửa trên CVAT; hệ thống tạo snapshot mới, chạy lại engine bị ảnh hưởng, reviewer xác minh; cuối cùng chạy QC run cuối trên revision đã sửa (B-03). |
| Tiền điều kiện | Issue ở trạng thái Đã xác nhận. |
| Luồng chính | • Reviewer tạo yêu cầu sửa: việc cần làm, mức độ, hạn, annotator. • Annotator mở deep link sang đúng job/frame trên CVAT, sửa, bấm *Đã sửa* trên LabelX. • Hệ thống tạo snapshot mới cho các job bị ảnh hưởng, chạy lại engine liên quan trên frame đã sửa (re-check). • Reviewer xem kết quả re-check và frame mới, chọn *Đạt* hoặc *Chưa đạt*. • Khi mọi yêu cầu sửa của phạm vi đã đạt, hệ thống tạo snapshot toàn phạm vi trên revision mới và QC run cuối (is_final), liên kết các verification trước đó. • Chỉ khi run cuối Completed và ledger đủ coverage engine bắt buộc, báo cáo và gate (UC-14) mới trỏ run này. |
| Luồng thay thế | **4a.** Chưa đạt: yêu cầu mở lại (Reopened), quay về bước 2. **3a.** Re-check phát hiện lỗi mới do sửa: tạo issue mới gắn revision mới. **6a.** Run cuối Partial/Failed/Cancelled hoặc phát sinh issue mới: gate chưa đạt; issue mới vào hàng đợi; không coi phạm vi đã hoàn tất. **2a.** Người verify là annotator đã sửa: backend từ chối. |
| Hậu điều kiện | Issue Resolved chỉ khi verify trên revision đã sửa; snapshot gốc giữ nguyên. |
| Yêu cầu | `FR-RWK-01`…`FR-RWK-07` |

### UC-08 · Lập và khoá reference

| Mục | Nội dung |
|---|---|
| Actor | QA Lead; hai người xác minh. |
| Mô tả | Lập GT độc lập cho tập đánh giá, suy ra tập lỗi, duyệt và khoá version (mục tương ứng trong labelX.html). |
| Tiền điều kiện | Snapshot tập đánh giá đã khoá; người xác minh không có quyền xem ranking, risk score và candidate của tập này (BR-10). |
| Luồng chính | • QA Lead tạo phiên reference, chọn snapshot, giao hai người xác minh. • Mỗi người gán GT độc lập (trong CVAT, task riêng) và nhập vào LabelX. • Hệ thống matching hai bản GT, đưa phần không khớp cho QA Lead phân xử. • Hệ thống suy ra $E$ theo BR-01…BR-07, hiển thị để duyệt. • QA Lead duyệt; nếu sửa mapping thì hệ thống suy lại (BR-14); QA Lead khoá version. • Hệ thống báo cáo tỉ lệ khớp hai bản GT trước phân xử (BR-11) và kiểm tập đánh giá không chứa case đã dùng hiệu chỉnh (BR-16). |
| Ngoại lệ | Người xác minh là annotator của frame: hệ thống chặn giao việc. |
| Hậu điều kiện | GT và $E$ khoá version cùng mapping, ngưỡng, thuật toán. |
| Yêu cầu | `FR-EVL-01`…`FR-EVL-05` |

### UC-09 · Đo Recall@20%

| Mục | Nội dung |
|---|---|
| Actor | QA Lead. |
| Mô tả | Tính KPI-1 trên tập held-out, so với ranking đối chứng, kèm khoảng tin cậy. |
| Tiền điều kiện | Reference khoá; ranking của held-out đã tính bằng version công thức đã khoá trên tập hiệu chỉnh. |
| Luồng chính | • QA Lead chọn run, reference version, $k$ (mặc định 20%). • Hệ thống kiểm $\|E\| \ge E_{min}$; tính Recall@k, recall theo nhóm lỗi, theo slice, recall theo frame có lỗi. • Hệ thống tính các đường đối chứng (ngẫu nhiên nhiều seed, heuristic) và khoảng tin cậy bootstrap. • Hệ thống lưu evaluation run với đầy đủ provenance. |
| Luồng thay thế | **2a.** $\|E\| < E_{min}$: ghi "không đủ mẫu", không kết luận. |
| Quy tắc | Chỉ đếm lỗi E1–E3 theo BR-01…BR-07; loại đối tượng ignore khỏi tử số và mẫu số; box thừa, cảnh báo cấu trúc và độ khít biên báo cáo riêng. Recall@20% đo khả năng xếp hạng, không thay thế phép đo accuracy của engine. Accuracy của Detector (Metric engine) đo riêng trên GT đã khoá; Model Orchestrator tổng hợp kết quả có provenance (B-05). |
| Yêu cầu | `FR-EVL-07`…`FR-EVL-10`, `FR-EVL-15` |

### UC-10 · Đo effort baseline/assisted

| Mục | Nội dung |
|---|---|
| Actor | Product Owner (thiết kế thí nghiệm); Reviewer (tham gia); QA Lead (giám sát). |
| Mô tả | Chạy thí nghiệm hai nhánh theo thiết kế ở mục tương ứng trong labelX.html, ghi effort tự động, tính KPI-2 và kiểm định chất lượng tương đương. |
| Tiền điều kiện | Thiết kế thí nghiệm (phân nhóm, quy tắc dừng, $\delta$) đã khoá; reference của dữ liệu thí nghiệm đã khoá. |
| Luồng chính | • Product Owner tạo thí nghiệm, gán reviewer vào nhánh theo thiết kế chéo. • Nhánh baseline: Workspace ẩn ranking và evidence, frame theo thứ tự gốc. • Nhánh assisted: Workspace hiển thị ranking và evidence, dừng theo quy tắc đã khoá. • Hệ thống ghi effort theo hoạt động (review, cảnh báo sai, phân xử, re-check). • Kết thúc: hệ thống tính $T_A, T_B, \rho_A, \rho_B$, KPI-2, KPI-2b và kiểm định non-inferiority. |
| Yêu cầu | `FR-EVL-11`…`FR-EVL-16` |

### UC-11 · Xem và xuất báo cáo hiệu quả

| Mục | Nội dung |
|---|---|
| Actor | Product Owner, QA Lead. |
| Mô tả | Xem báo cáo KPI-1, KPI-2, guardrail, coverage, có ghi cỡ mẫu và phương pháp; xuất PDF/CSV/JSON. |
| Luồng chính | • Actor chọn evaluation run/thí nghiệm. • Hệ thống hiển thị: đường Recall@k, bảng theo nhóm lỗi và slice, effort hai nhánh, residual, guardrail, coverage từng engine. • Actor xuất báo cáo; tệp xuất ghi version của snapshot, run, công thức, reference. |
| Quy tắc | Chỉ số chưa đủ dữ liệu hiển thị Not checked/không đủ mẫu, không hiển thị 0% hay đạt. |
| Yêu cầu | `FR-RPT-01`…`FR-RPT-06` |

### UC-12 · Tra cứu guideline (hỗ trợ)

| Mục | Nội dung |
|---|---|
| Actor | Reviewer. |
| Mô tả | Từ issue, xem rule guideline liên quan theo rule ID + version + section và các Decision Case đã duyệt (B-13); không dùng RAG. |
| Luồng chính | Hệ thống tra mapping (nhóm lỗi, lớp) → rule ID; hiển thị trích đoạn, version, section; liệt kê case đã phân xử cùng rule. |
| Yêu cầu | `FR-GDL-01`…`FR-GDL-04` |

### UC-13 · Quản lý quyền và audit (hỗ trợ)

| Mục | Nội dung |
|---|---|
| Actor | QC Admin; Super Admin (ghi đè có lý do). |
| Mô tả | Gán vai trò theo scope dataset; xem nhật ký kiểm toán append-only. |
| Quy tắc | Backend luôn kiểm quyền; ẩn nút chỉ để thuận tiện. Người duyệt khác người yêu cầu. Ghi đè của Super Admin phải có lý do và gắn nhãn trong audit. |
| Yêu cầu | `FR-SEC-01`…`FR-SEC-07` |

### UC-14 · Kiểm Quality Gate tối thiểu (hỗ trợ)

| Mục | Nội dung |
|---|---|
| Actor | QA Lead (xem, đề nghị waiver); người có quyền duyệt ngoại lệ (khác người đề nghị). |
| Mô tả | Tính từng điều kiện gate trên QC run cuối; hiển thị nguồn, cỡ mẫu, kết quả; xử lý waiver theo policy. Không bao gồm phát hành dataset đầy đủ. |
| Tiền điều kiện | Có QC run cuối (UC-07) hoặc run gốc nếu chưa có rework (ghi rõ). |
| Luồng chính | • Hệ thống tính từng điều kiện theo FR-GTE-01, mỗi điều kiện có nguồn, mẫu số, cỡ mẫu. • Điều kiện thiếu dữ liệu hoặc engine bắt buộc Not checked/Partial/Failed: *chưa đạt*. • QA Lead xem kết quả; nếu có điều kiện chưa đạt và policy cho phép, tạo đề nghị waiver với lý do, evidence, hạn. • Người duyệt khác người đề nghị duyệt/từ chối; waiver chỉ hiệu lực sau duyệt. |
| Ngoại lệ | Người duyệt trùng người đề nghị: backend từ chối. Waiver hết hạn: điều kiện trở lại chưa đạt. |
| Yêu cầu | `FR-GTE-01`…`FR-GTE-04` |
