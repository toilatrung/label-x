---
id: business-requirements
title: Yêu cầu nghiệp vụ và hệ thống — SRS M13
type: reference
domain: business
module: requirements
tags: [requirements, functional, non-functional, kpi, m13]
priority: 1
---

# Yêu cầu nghiệp vụ và hệ thống — SRS M13

## Purpose

Tóm tắt có thể tra cứu của các yêu cầu trong SRS M13 của LabelX (người dùng chấp nhận nội dung 05/10/2026, chờ ký theo vai trò): mục tiêu, KPI, phạm vi, yêu cầu chức năng, phi chức năng và tiêu chí nghiệm thu, giữ nguyên mã định danh.

Nguồn chuẩn: [labelX.html](labelX.html) (bản HTML) và `docs/label-x_system-requirement-specification/` (bản LaTeX), SRS M13 v1.0, 05/10/2026. Khi có khác biệt, bản LaTeX là gốc; HTML được sinh lại bằng `python3 scripts/srs_tex2html.py`.

## Phạm vi

| Nhóm | Nội dung |
|---|---|
| **Lõi — nghiệm thu** | Đọc annotation và ảnh từ CVAT, tạo snapshot bất biến; chạy các engine phát hiện nghi vấn cho Bounding box; hợp nhất candidate; tính điểm rủi ro frame và xếp hạng; hàng đợi ưu tiên; Review Workspace hiển thị bằng chứng; quyết định xác nhận/bác bỏ/chưa chắc chắn; phân xử; đo Recall@20% và mức giảm công sức review; báo cáo hiệu quả. |
| **Hỗ trợ — mức cần thiết** | Tra cứu guideline theo rule ID/version; yêu cầu sửa (rework) và kiểm lại sau sửa; phân quyền và nhật ký kiểm toán; Quality Gate tối thiểu để không phát hành dữ liệu chưa xác minh. |
| **Ngoài phạm vi bản đầu** | Temporal/track, polygon, polyline, video (B-09); ghi annotation ngược vào CVAT (B-18); Diff/pre-label, vehicle profile, feedback loop (B-16); Classifier thứ hai (B-07); Guideline RAG (B-13); phát hành dataset đầy đủ và quản trị nền tảng ngoài mức tối thiểu. |
| **Đề xuất thu hẹp — cần duyệt** | Engine mô hình thị giác – ngôn ngữ (VLM) không bật trong pilot M13. Đây là *đề xuất thu hẹp cho pilot M13, cần Product Owner duyệt*; nó không kế thừa từ B-08. Quyết định B-08 (pipeline candidate → chọn theo policy → worker kiểm chọn lọc) vẫn là kiến trúc đã chốt. Nếu đề xuất bị bác, VLM chạy theo B-08 với hạn mức 400 candidate/run, tối đa 3 lần thử, và hết hạn mức thì ghi phần chưa kiểm (TBD-08). |

## Mục tiêu và chỉ số thành công

| Mã | Chỉ số | Định nghĩa | Ngưỡng |
|---|---|---|---|
| KPI-1 | Recall lỗi trong top 20% frame | Số lỗi đã xác minh nằm trong 20% frame đầu / tổng số lỗi đã xác minh của tập held-out. Đo *khả năng xếp hạng*. Chỉ tính khi $\|E\| \ge E_{min}$; dưới ngưỡng ghi "không đủ mẫu", không kết luận đạt/trượt. | TBD-K1; $E_{min}$ TBD-K4 |
| KPI-2 | Mức giảm công sức review | $1 - T_A/T_B$, effort gồm review, xử lý cảnh báo sai, phân xử, kiểm lại sau sửa. | TBD-K2 |
| KPI-2b | Recall phát hiện thực tế | Chỉ số phụ đo trong thí nghiệm KPI-2: số lỗi reference reviewer thực sự xác nhận / tổng số lỗi reference của phần dữ liệu đó, theo từng nhánh. | Báo cáo, không có ngưỡng |
| G-1 | Chất lượng tương đương | Non-inferiority một phía ($\alpha = 0,025$): cận trên khoảng tin cậy 95% của $\rho_A - \rho_B$ nhỏ hơn $\delta$. | $\delta$ TBD-K3 |
| G-2 | Gate: lỗi nghiêm trọng | Số issue mức nghiêm trọng đã xác nhận còn mở trên run cuối. | 0 (cấu hình pilot) |
| G-2b | Thí nghiệm: lỗi nghiêm trọng | Lỗi nghiêm trọng của reference còn lại (kể cả chưa có issue) ở assisted không nhiều hơn baseline. | Không nhiều hơn |
| G-5 | Thí nghiệm: box thừa | Box thừa (BR-06) trong annotation cuối của assisted không nhiều hơn baseline quá $\delta_{fp}$. | $\delta_{fp}$ TBD-K3 |
| G-3 | Đồng thuận reviewer | Số quyết định của reviewer trùng kết luận adjudicator / tổng quyết định được chấm, trên tập case chuẩn (theo H, PerformanceEvaluation). Quyết định "Chưa chắc chắn" tính là không trùng; mỗi reviewer tính riêng rồi báo cáo cả trung vị. Không thay thế accuracy của engine. | $\ge 90%$ (cấu hình pilot) |
| G-4 | Residual vận hành | Tỉ lệ frame còn lỗi ước lượng từ lát kiểm tra ngẫu nhiên (theo H), dùng khi không có reference toàn tập. Khác $\rho$ của thí nghiệm. | $\le 5%$ (cấu hình pilot) |

Ngưỡng G-2, G-3, G-4 là cấu hình khởi điểm pilot đã chốt (nguồn R); ngưỡng KPI-1/KPI-2 chốt từ đo baseline trước khi chạy held-out (B-14).

## Yêu cầu chức năng

Ưu tiên MoSCoW: M = Must, S = Should, C = Could.

### SNP — CVAT Adapter và Snapshot

| Mã | Yêu cầu | Ưu tiên | Truy vết |
|---|---|---|---|
| `FR-SNP-01` | Adapter phải chỉ dùng thao tác đọc của CVAT API (project, task, job, frame meta, annotation, media). Không có đường gọi nào tạo/sửa/xoá annotation trên CVAT. | M | UC-01; B-18 |
| `FR-SNP-02` | Token CVAT phải lưu ở backend (secret store), không gửi xuống client. | M | UC-01; B-12 |
| `FR-SNP-03` | Hệ thống phải chuẩn hoá annotation từng job thành JSON chuẩn (sắp xếp khoá, toạ độ làm tròn cố định) và tính hash SHA-256 từng job và hash tổng. | M | UC-01; B-02; R-01 |
| `FR-SNP-04` | Trước khi khoá, hệ thống phải đọc lại thông tin cập nhật của từng job; nếu khác lần đọc đầu thì không khoá và báo danh sách job bị drift. | M | UC-01; B-02 |
| `FR-SNP-05` | Snapshot phải lưu: ảnh và checksum, mapping frame (job/task/frame nguồn), assignee từng job tại thời điểm snapshot, taxonomy version, guideline version, người tạo. | M | UC-01; B-12 |
| `FR-SNP-06` | Snapshot đã khoá là bất biến; mọi thay đổi annotation tạo snapshot mới có `parent_snapshot`. | M | B-02, B-03 |
| `FR-SNP-07` | Shape không phải Bounding box phải được bỏ qua và đếm trong báo cáo snapshot là "ngoài phạm vi". | M | Phạm vi M13 |
| `FR-SNP-08` | Hệ thống phải tạo deep link mở đúng job và frame trên CVAT cho mỗi frame/issue. | M | UC-07; B-18 |
| `FR-SNP-09` | Hệ thống nên hỗ trợ tạo snapshot gia tăng chỉ cho các job bị ảnh hưởng bởi rework. | S | UC-07 |

### ENG — Engine phân tích nghi vấn

| Mã | Yêu cầu | Ưu tiên | Truy vết |
|---|---|---|---|
| `FR-ENG-01` | QC Run phải ghi: snapshot, config version, seed, version từng engine, model artifact + checksum, người chạy, thời điểm. | M | UC-02; R-01 |
| `FR-ENG-02` | **Schema/Taxonomy** phải kiểm: lớp thuộc taxonomy version; thuộc tính bắt buộc có giá trị hợp lệ; sinh cảnh báo cấu trúc có rule ID, expected/actual. | M | UC-02 |
| `FR-ENG-03` | **Geometry** phải kiểm: $x_1<x_2, y_1<y_2$; toạ độ trong ảnh với dung sai 2 px; diện tích ≥ 24 px$^2$ (G-014). Không kiểm độ khít biên (G-009 giữ Not checked). | M | UC-02; B-06 |
| `FR-ENG-04` | **Duplicate/Overlap** phải sinh candidate E3 cho cặp annotation có IoU $\ge 0,85$ (D-002), kèm IoU và lớp của hai box. Candidate chỉ là nghi vấn. | M | UC-02; E3 |
| `FR-ENG-05` | **Mô hình độc lập** phải chạy một Detector baseline đã freeze (artifact, version, checksum, mapping lớp sang 10 lớp BDD100K) trên mọi frame trong phạm vi áp dụng. | M | UC-02; B-07 |
| `FR-ENG-06` | Matching dự đoán–annotation phải theo mục tương ứng trong labelX.html: không phụ thuộc lớp, loại cạnh dưới $\tau_m$ trước khi tối ưu, tối đa số cặp rồi tổng IoU, phá hoà tất định. | M | B-21 |
| `FR-ENG-07` | Dự đoán không ghép với confidence $\ge \tau_{E1}$ sinh candidate E1; cặp ghép khác lớp với confidence lớp dự đoán $\ge \tau_{E2}$ sinh candidate E2. Ngưỡng có version, chọn trên tập hiệu chỉnh. | M | E1, E2 |
| `FR-ENG-08` | Evidence của candidate phải gồm: box và lớp dự đoán, confidence, IoU, cặp ambiguous (nếu có), crop ảnh, rule liên quan. | M | R-02 |
| `FR-ENG-09` | Nếu không có Detector khả dụng, engine Mô hình độc lập phải ở trạng thái Not checked; không được sinh ranking giả từ engine thiếu. | M | B-07, B-19 |
| `FR-ENG-10` | Engine VLM: đề xuất không bật trong pilot M13, cần Product Owner duyệt (TBD-08). Nếu đề xuất bị bác hoặc VLM được bật, phải theo B-08: pipeline candidate → chọn theo policy → worker kiểm chọn lọc; tối đa 400 candidate mỗi run; tối đa 3 lần thử tổng cộng mỗi lượt kiểm (tính cả retry); hết hạn mức thì ghi phần chưa kiểm, không pass/reject; timeout cụ thể lấy từ đo pilot; ảnh không gửi ra ngoài khi chưa được phép. | C | B-08 |

### AGG — Candidate, Issue và Coverage ledger

| Mã | Yêu cầu | Ưu tiên | Truy vết |
|---|---|---|---|
| `FR-AGG-01` | Candidate và Issue phải là hai thực thể riêng; candidate không bao giờ bị sửa sau khi ghi. | M | B-10 |
| `FR-AGG-02` | Mỗi đơn vị xử lý phải có khoá idempotent (snapshot, engine, config, model, shard); retry không tạo candidate hay issue trùng. | M | B-10; R-01 |
| `FR-AGG-03` | Candidate được gộp thành issue theo `dedup_key` = (snapshot, frame, đối tượng tham chiếu, nhóm lỗi), có version policy gộp. | M | B-10; BR-08 |
| `FR-AGG-04` | Coverage ledger phải ghi theo từng engine: đơn vị áp dụng, số đơn vị eligible, completed, failed, not checked, kèm lý do; không loại đơn vị lỗi khỏi mẫu số. | M | B-04; R-06 |
| `FR-AGG-05` | Trạng thái công khai của engine chỉ gồm Checked, Partial, Failed, Not checked, Running; không có trạng thái nào được hiển thị như "đạt" khi engine chưa hoàn tất. | M | B-19 |
| `FR-AGG-06` | Ghi candidate, evidence và cập nhật ledger của một shard phải trong cùng transaction. | M | R-01 |

### RNK — Chấm điểm rủi ro và xếp hạng

| Mã | Yêu cầu | Ưu tiên | Truy vết |
|---|---|---|---|
| `FR-RNK-01` | Hệ thống phải tính $s(f)$ cho *mọi* frame của snapshot trong phạm vi run, kể cả frame không có candidate. | M | UC-03; KPI-1 |
| `FR-RNK-02` | Công thức điểm (đặc trưng, tham số, mô hình nền, ngưỡng) phải có version, lưu kèm mỗi ranking, và không đổi được sau khi khoá. | M | UC-03; R-01 |
| `FR-RNK-03` | Với cùng snapshot, config, score version và seed, ranking phải tái lập giống hệt. | M | R-01 |
| `FR-RNK-04` | Phá hoà phải tất định theo hash(frame_key, seed). | M | KPI-1 |
| `FR-RNK-05` | Hệ thống phải lưu đóng góp $n_i q_i$ của từng issue và điểm nền $h(f)$ vào $s(f)$ để hiển thị "vì sao frame được xếp cao". | M | UC-04; R-02 |
| `FR-RNK-06` | Frame có engine bắt buộc ở trạng thái Not checked/Failed phải mang cờ "thiếu bằng chứng" trong hàng đợi, không được ẩn. | M | B-19; R-06 |
| `FR-RNK-07` | Hệ thống phải tạo lát kiểm tra ngẫu nhiên $r%$ frame (TBD-10) bằng seed cố định, độc lập với ranking, hiển thị ở hàng đợi riêng và báo cáo riêng. | M | R-04 |
| `FR-RNK-08` | Hệ thống phải tạo được các ranking đối chứng trên cùng snapshot: ngẫu nhiên (nhiều seed) và heuristic (số annotation giảm dần; max confidence). | M | UC-09; KPI-1 |
| `FR-RNK-09` | Hệ thống nên hỗ trợ biến thể xếp hạng theo kỳ vọng lỗi trên thời gian review ước lượng $s(f)/\hat t(f)$ để tối ưu KPI-2. | C | KPI-2 |
| `FR-RNK-10` | Hiệu chỉnh xác suất phải được kiểm bằng dự đoán ngoài fold (cross-validation theo video) trên tập hiệu chỉnh: Brier score và đường reliability theo E1/E2/E3; kết quả lưu cùng score version. | M | KPI-1 |
| `FR-RNK-11` | Trước khi khoá score version, chạy ablation trên tập hiệu chỉnh: bỏ điểm nền, bỏ từng nhóm đặc trưng, so với `score_v0` và heuristic; chọn version theo Recall@20% ngoài fold. | M | KPI-1; B-14 |
| `FR-RNK-12` | Mỗi issue lưu neo và $n_i$ theo bảng tương ứng trong labelX.html; quy tắc tạo neo có version cùng policy gộp. | M | BR-01…BR-04 |

### REV — Hàng đợi và Review Workspace

| Mã | Yêu cầu | Ưu tiên | Truy vết |
|---|---|---|---|
| `FR-REV-01` | Review Queues phải có ít nhất hai hàng đợi tách theo nguồn: *Theo rủi ro* (thứ tự rank) và *Kiểm tra ngẫu nhiên*; lọc theo nhóm lỗi, nguồn, phạm vi. | M | UC-04; H |
| `FR-REV-02` | Mỗi dòng hàng đợi hiển thị: frame, rank, số issue theo nhóm, nguồn, mức ưu tiên, trạng thái, reviewer giữ lease. | M | UC-04 |
| `FR-REV-03` | *Bắt đầu review* cấp lease frame kế tiếp chưa có người giữ, bỏ qua frame mà reviewer là assignee tại snapshot. | M | UC-04; B-12 |
| `FR-REV-04` | Lease có thời hạn TBD-09, gia hạn khi có thao tác; hết hạn thì frame về hàng đợi. | M | UC-04 |
| `FR-REV-05` | Workspace phải hiển thị ảnh với annotation (nét liền) và dự đoán Detector (nét đứt), bật/tắt từng lớp hiển thị, phóng to và di chuyển. | M | UC-05; H |
| `FR-REV-06` | Workspace phải có hai chế độ: *Issue Review* (theo từng issue) và *Frame Review* (toàn frame). | M | UC-05; H |
| `FR-REV-07` | Panel issue phải hiển thị evidence (FR-ENG-08), trạng thái từng engine (kể cả Failed/Not checked), guideline và case tương tự (UC-12). | M | UC-05; R-02 |
| `FR-REV-08` | Quyết định gồm: Xác nhận lỗi, Bác bỏ, Chưa chắc chắn, Chuyển cấp trên, Yêu cầu sửa; xác nhận bắt buộc chọn nhóm lỗi và mức độ; bác bỏ, chưa chắc chắn và chuyển cấp bắt buộc lý do. | M | UC-05; R-02 |
| `FR-REV-09` | Reviewer phải tạo được issue thủ công bằng cách chọn object hoặc vẽ vùng trên ảnh, nguồn ghi là "reviewer". | M | UC-05; E1 |
| `FR-REV-10` | Mọi quyết định lưu actor, thời điểm, revision, lý do, rule ID và ghi audit trong cùng transaction. | M | R-05; B-12 |
| `FR-REV-11` | Phím tắt cho các quyết định và chuyển frame/issue. | S | KPI-2 |
| `FR-REV-12` | Nút *Mở trong CVAT* mở deep link đúng job/frame. | M | B-18 |
| `FR-REV-13` | *Đã review xong* chỉ cho phép khi mọi issue của frame đã có quyết định hoặc đang chờ phân xử; khi lưu, hệ thống trả lease và dừng ghi effort của frame. | M | UC-05 |
| `FR-REV-14` | Backend từ chối lưu mọi quyết định khi lease đã hết hạn hoặc thuộc người khác (409), và khi reviewer là assignee của job tại snapshot (403), kể cả khi mở frame trực tiếp bằng URL. | M | UC-05; B-12 |

### ESC — Chuyển cấp và phân xử

| Mã | Yêu cầu | Ưu tiên | Truy vết |
|---|---|---|---|
| `FR-ESC-01` | Escalations phải liệt kê issue Chưa chắc chắn/Chuyển cấp, kèm quyết định từng reviewer và evidence. | M | UC-06 |
| `FR-ESC-02` | Kết luận phân xử: Xác nhận lỗi, Bác bỏ, Guideline còn thiếu; bắt buộc rule áp dụng, nhãn đúng (nếu có), lý do. | M | UC-06 |
| `FR-ESC-03` | Người phân xử phải khác người đã chuyển cấp. | M | B-12 |
| `FR-ESC-04` | Phân xử được lưu thành Decision Case có version, tra cứu được ở UC-12. | M | B-13 |
| `FR-ESC-05` | *Guideline còn thiếu* tạo Guideline Gap gắn rule; issue chờ đến khi guideline có version mới. | S | UC-06 |

### RWK — Rework và kiểm lại

| Mã | Yêu cầu | Ưu tiên | Truy vết |
|---|---|---|---|
| `FR-RWK-01` | Yêu cầu sửa gồm: issue, việc cần sửa, annotator, hạn, mức độ, deep link. | M | UC-07 |
| `FR-RWK-02` | Annotator chỉ thấy yêu cầu sửa của mình; sửa trên CVAT, bấm *Đã sửa* trên LabelX. | M | UC-07; B-18 |
| `FR-RWK-03` | Khi *Đã sửa*, hệ thống tạo snapshot mới cho job bị ảnh hưởng; nếu revision không đổi thì từ chối với thông báo "chưa có thay đổi". | M | UC-07; B-02 |
| `FR-RWK-04` | Hệ thống chạy lại các engine liên quan trên frame đã sửa (re-check) và hiển thị kết quả cho reviewer. | M | UC-07; R-03 |
| `FR-RWK-05` | Issue chỉ chuyển Đã đóng khi reviewer verify đạt trên revision mới; người verify khác annotator đã sửa. | M | R-03; H |
| `FR-RWK-06` | Khi mọi yêu cầu sửa trong phạm vi đã đóng, hệ thống tạo snapshot toàn phạm vi trên revision đã sửa và QC run cuối (`is_final`), liên kết các verification trước đó. Run gốc giữ nguyên để kiểm toán. | M | B-03; R-03 |
| `FR-RWK-08` | Báo cáo và gate chỉ chuyển sang trỏ run cuối khi run cuối Completed và coverage engine bắt buộc đạt theo ledger. Run cuối Partial/Failed/Cancelled hoặc phát sinh issue mới: issue mới vào hàng đợi, gate chưa đạt, phạm vi chưa hoàn tất. | M | B-03, B-15 |
| `FR-RWK-07` | Rework Tracking hiển thị: chờ sửa, chờ xác minh, hoàn thành, tỉ lệ đóng, quá hạn. | S | H |

### GDL — Tra cứu guideline

| Mã | Yêu cầu | Ưu tiên | Truy vết |
|---|---|---|---|
| `FR-GDL-01` | Lưu guideline theo version với rule ID, section, nội dung trích; nội dung soạn và duyệt ở nơi soạn guideline. | S | B-13 |
| `FR-GDL-02` | QC Admin cấu hình mapping (nhóm lỗi, lớp, cặp lớp) → rule ID. | S | B-13 |
| `FR-GDL-03` | Workspace hiển thị rule theo mapping, version đang áp dụng cho snapshot và các Decision Case cùng rule. | S | UC-12 |
| `FR-GDL-04` | Không dùng retrieval ngữ nghĩa/RAG trong M13. | M | B-13 |

### EVL — Reference, đo lường và effort

| Mã | Yêu cầu | Ưu tiên | Truy vết |
|---|---|---|---|
| `FR-EVL-01` | Hệ thống phải nhập được hai bản GT độc lập cho một snapshot đánh giá và ghép chúng theo matching mục tương ứng trong labelX.html. Pilot (v1.1, CR-101): nhập một GT là nhãn gốc BDD100K từ tệp, khoá theo checksum; nhập hai GT để giai đoạn sau. | M | UC-08; BR-11 |
| `FR-EVL-02` | Người được giao lập GT/xác minh của tập đánh giá không có quyền xem ranking, risk score, candidate của tập đó. | M | BR-10 |
| `FR-EVL-03` | Hệ thống suy ra $E$ theo BR-01…BR-07 và hiển thị để duyệt; sửa mapping thì suy lại, không xoá lỗi trực tiếp. | M | UC-08; BR-14 |
| `FR-EVL-04` | Khoá reference cùng: GT version, snapshot đầu vào, mapping, $\tau_m$, $a_{min}$, version thuật toán. | M | BR-13; B-20 |
| `FR-EVL-05` | Chống rò rỉ dữ liệu: (a) tập hiệu chỉnh và held-out không giao nhau theo video nguồn; hệ thống từ chối dùng held-out để học tham số điểm; (b) đối chiếu danh sách ảnh huấn luyện của Detector với held-out, có giao nhau thì chặn đánh giá (AS-03); (c) loại case guideline/hiệu chỉnh khỏi GT held-out (BR-16). Kết quả kiểm lưu cùng evaluation run. | M | AS-03; BR-16 |
| `FR-EVL-06` | Effort log tự động ghi theo frame và hoạt động (xem frame, xử lý issue, phân xử, re-check/verify) với thời gian hoạt động thực; khoảng không thao tác quá $t_{idle}$ (TBD-11) không tính. | M | UC-05; KPI-2 |
| `FR-EVL-07` | Tính Recall@k theo phương trình tương ứng trong labelX.html với $k$ cấu hình (mặc định 0,2), làm tròn $\lceil kN \rceil$. | M | UC-09; KPI-1 |
| `FR-EVL-08` | Báo cáo kèm: recall theo nhóm lỗi, theo slice (ngày/đêm, thời tiết, kích thước), recall theo frame có lỗi, đường Recall@k với $k$ từ 5% đến 100%. | M | UC-09 |
| `FR-EVL-09` | Tính khoảng tin cậy 95% bằng bootstrap theo cụm video nguồn ($B \ge 1000$ lần lặp), và hiệu số so với từng ranking đối chứng. | M | UC-09 |
| `FR-EVL-10` | Không tính KPI khi $\|E\| < E_{min}$; ghi "không đủ mẫu". | M | KPI-1 |
| `FR-EVL-11` | Tạo thí nghiệm effort: phân reviewer vào nhánh theo thiết kế chéo, khoá quy tắc dừng, $\delta$, cỡ mẫu trước khi bắt đầu. | M | UC-10; KPI-2 |
| `FR-EVL-12` | Ở nhánh baseline, Workspace phải ẩn ranking, risk score và evidence của engine; frame theo thứ tự gốc. | M | UC-10 |
| `FR-EVL-13` | Tính $T_A, T_B$, KPI-2, KPI-2b, residual $\rho_A, \rho_B$ trên reference và kiểm định non-inferiority theo mục tương ứng trong labelX.html. | M | UC-10 |
| `FR-EVL-14` | Evaluation run lưu provenance: snapshot, run, score version, reference version, thí nghiệm, tham số, thời điểm, người chạy. | M | B-05; R-04 |
| `FR-EVL-15` | Metric engine (Precision/Recall của Detector theo lớp) chỉ tính trên GT đã khoá; thiếu GT thì Not checked. | S | B-05 |
| `FR-EVL-16` | Tính đồng thuận reviewer (G-3) theo định nghĩa ở bảng tương ứng trong labelX.html trên tập case chuẩn. | S | G-3 |

### RPT — Báo cáo hiệu quả

| Mã | Yêu cầu | Ưu tiên | Truy vết |
|---|---|---|---|
| `FR-RPT-01` | Báo cáo hiệu quả hiển thị KPI-1, KPI-2, KPI-2b, G-1…G-4, mỗi chỉ số có cỡ mẫu, mẫu số, phương pháp, khoảng tin cậy. | M | UC-11 |
| `FR-RPT-02` | Kết quả kiểm tra ngẫu nhiên và theo rủi ro được báo cáo riêng, không gộp. | M | R-04; H |
| `FR-RPT-03` | Chỉ số chưa đủ dữ liệu hiển thị Not checked/không đủ mẫu; không hiển thị 0% hay đạt. | M | B-05, B-19 |
| `FR-RPT-04` | Coverage hiển thị theo từng engine với mẫu số áp dụng; coverage chung chỉ là tiến độ. | M | B-04 |
| `FR-RPT-05` | Xuất PDF, CSV, JSON; tệp xuất ghi version snapshot, run, score, reference. | S | H |
| `FR-RPT-06` | Báo cáo trỏ QC run cuối khi run cuối thoả FR-RWK-08; nếu chưa thì ghi rõ đang dùng run gốc và lý do. | M | B-03 |

### SEC — Phân quyền và kiểm toán

| Mã | Yêu cầu | Ưu tiên | Truy vết |
|---|---|---|---|
| `FR-SEC-01` | Phân quyền theo vai trò và scope dataset theo bảng tương ứng trong labelX.html; backend kiểm mọi request. | M | UC-13; R-05 |
| `FR-SEC-02` | Identity mapping giữa tài khoản LabelX và người dùng CVAT được lưu và dùng cho kiểm self-review. | M | B-12 |
| `FR-SEC-03` | Backend từ chối quyết định review khi reviewer là assignee của job tại snapshot. | M | B-12 |
| `FR-SEC-04` | Người duyệt (waiver, khoá reference, phân xử) khác người yêu cầu; không được dùng tài khoản khác của cùng người. | M | B-11, B-12 |
| `FR-SEC-05` | Audit log append-only, ghi trong cùng transaction với thao tác: actor, hành động, đối tượng, trước/sau, revision, lý do. | M | B-12; R-05 |
| `FR-SEC-06` | Ghi đè của Super Admin bắt buộc lý do, gắn nhãn trong audit, vẫn chịu self-review và tách nhiệm vụ. | M | H |
| `FR-SEC-07` | Màn hình xem audit lọc theo actor, đối tượng, thời gian. | S | UC-13 |

### GTE — Quality Gate tối thiểu

| Mã | Yêu cầu | Ưu tiên | Truy vết |
|---|---|---|---|
| `FR-GTE-01` | Gate tính trên QC run cuối với các điều kiện cấu hình pilot: coverage engine bắt buộc ≥ 95% (mẫu số theo ledger), lỗi nghiêm trọng chưa đóng = 0, rework bắt buộc verify 100%, residual ≤ 5%, đồng thuận reviewer ≥ 90%. | M | B-15; R-06 |
| `FR-GTE-02` | Điều kiện thiếu dữ liệu (cỡ mẫu chưa đủ, engine Not checked) là *chưa đạt*, không tự đạt. | M | B-15, B-19 |
| `FR-GTE-03` | Waiver theo policy từng điều kiện: lý do, evidence, hạn hiệu lực, người duyệt khác người yêu cầu; chỉ hiệu lực sau duyệt; hết hạn thì điều kiện trở lại chưa đạt. | S | B-11 |
| `FR-GTE-04` | Phát hành dataset đầy đủ nằm ngoài phạm vi; M13 chỉ hiển thị kết quả gate. | M | Phạm vi |

## Yêu cầu phi chức năng

Các con số là đề xuất khởi điểm; ngưỡng nghiệm thu chốt sau khi đo pilot (B-14).

| Mã | Nhóm | Yêu cầu | Cách kiểm |
|---|---|---|---|
| `NFR-01` | Hiệu năng UI | Mở frame kế tiếp trong Workspace (ảnh + annotation + issue): đề xuất p95 ≤ 1,5 s, cache ấm (TBD-13). | Đo log client trong pilot. |
| `NFR-02` | Hiệu năng UI | Lưu quyết định review: đề xuất p95 ≤ 500 ms (TBD-13). | Đo log API trong pilot. |
| `NFR-03` | Thông lượng | Thời gian QC Run cho 10.000 frame (CPU engine + Detector + xếp hạng) ≤ TBD-13 trên phần cứng chốt ở TBD-02. | Đo trên pilot. |
| `NFR-04` | Tái lập | Cùng input, config, version, seed cho kết quả giống hệt (hash). Detector chạy chế độ suy luận tất định hoặc lưu prediction để tái dùng. | AC-01. |
| `NFR-05` | Tin cậy | Shard lỗi được retry tối đa TBD-14 lần với backoff; lỗi còn lại ghi Failed cho đơn vị đó, không làm hỏng run; worker chết giữa chừng không mất kết quả đã commit. | Kiểm thử ép lỗi. |
| `NFR-06` | Toàn vẹn | Blob (ảnh, crop evidence) được upload lên Object Storage *trước*, với khoá theo hash nội dung (ghi lại là idempotent); sau đó metadata candidate, evidence, ledger của shard được commit trong một transaction PostgreSQL. Blob không có metadata trỏ tới sau $t_{gc}$ được job dọn dẹp xoá. Quyết định và audit ghi trong một transaction. | Kiểm thử ngắt giữa upload và commit. |
| `NFR-07` | Bảo mật | Token CVAT chỉ ở backend; HTTPS; mật khẩu/secret không xuất hiện trong log; phân quyền kiểm ở backend cho mọi endpoint. | Rà soát bảo mật, kiểm thử API. |
| `NFR-08` | Kiểm toán, lưu trữ | Audit log append-only (không có API sửa/xoá). Audit, evidence, snapshot và reference được giữ chừng nào dataset còn cần quản lý hoặc đối chiếu; việc kết thúc lưu do người quản lý dữ liệu xác nhận và được ghi audit. Thời hạn tối thiểu TBD-15. | Kiểm thử API, rà soát DB grant. |
| `NFR-09` | Riêng tư dữ liệu | Ảnh BDD100K chỉ lưu trong Object Storage nội bộ; không gửi ảnh ra dịch vụ ngoài trong pilot. | Rà soát cấu hình. |
| `NFR-10` | Khả dụng | Giao diện theo LabelX Design System: trung tính, table-first, trạng thái dùng nhãn chữ (không chỉ màu), tương phản WCAG AA. | Review UI. |
| `NFR-11` | Khả dụng | Đề xuất: reviewer mới hoàn thành đúng quy trình một frame có 3 issue sau buổi làm quen (thời lượng TBD-11). | Quan sát trong buổi làm quen (EX-08). |
| `NFR-12` | Quan sát | Log có cấu trúc kèm run_id, snapshot_id, request_id; metric hàng đợi Celery, thời gian shard, tỉ lệ lỗi. | Kiểm tra dashboard vận hành. |
| `NFR-13` | Khả năng mở rộng | Engine được đăng ký qua interface chung (input, output, trạng thái, ledger) để thêm engine (VLM, Classifier, temporal) mà không sửa luồng review. | Review kiến trúc. |
| `NFR-14` | Tính đúng của số liệu | Mọi số liệu hiển thị có provenance truy về run, snapshot, version; không hiển thị số liệu không có nguồn. | AC-10. |
| `NFR-15` | Đồng thời | Không có hai reviewer giữ cùng lease ở mọi mức tải; số reviewer đồng thời mục tiêu lấy từ kế hoạch pilot (đề xuất 10). | Kiểm thử tải. |
| `NFR-16` | Sao lưu | Sao lưu PostgreSQL và Object Storage (bật versioning) theo cùng lịch; khôi phục được snapshot, ảnh, evidence, quyết định, reference, effort log nhất quán với nhau. RPO/RTO TBD-17. | Diễn tập khôi phục. |

## Tiêu chí nghiệm thu

| Mã | Tiêu chí | Mục tiêu | Yêu cầu |
|---|---|---|---|
| AC-01 | Tạo hai lần QC Run cùng snapshot, config, score version, seed cho ra candidate, issue, ranking giống hệt: so hash của nội dung đã chuẩn hoá (bỏ ID sinh tự động, thời điểm, run_id; sắp theo khoá tự nhiên). | R-01 | FR-AGG-02, FR-RNK-03 |
| AC-02 | Ép lỗi một shard rồi retry: số issue không đổi, không có bản trùng. | R-01 | FR-AGG-02 |
| AC-03 | Sửa annotation trên CVAT trong lúc tạo snapshot: snapshot không được khoá, báo job drift. | R-01 | FR-SNP-04 |
| AC-04 | Mọi candidate hiển thị trong Workspace có evidence; không issue nào được đóng hoặc xác nhận mà không có quyết định của người. | R-02 | FR-REV-07, FR-REV-08 |
| AC-05 | Reviewer là assignee của job tại snapshot gửi quyết định qua API: bị từ chối, có audit. | R-05 | FR-SEC-03 |
| AC-06 | Issue chỉ Đã đóng sau verify trên revision mới; báo cáo trỏ QC run cuối. | R-03 | FR-RWK-05, FR-RWK-06 |
| AC-07 | Engine Not checked/Failed hiển thị đúng trạng thái; gate không đạt khi thiếu dữ liệu. | R-06 | FR-AGG-05, FR-GTE-02 |
| AC-08 | Recall@20% trên held-out đạt tiêu chí mục tương ứng trong labelX.html, kèm đối chứng và khoảng tin cậy. Chỉ đánh giá được sau khi TBD-K1, TBD-K4 đã chốt; trước đó trạng thái là "chưa xác định". | KPI-1, R-04 | FR-EVL-07…10 |
| AC-09 | Thí nghiệm effort đạt tiêu chí mục tương ứng trong labelX.html. Chỉ đánh giá được sau khi TBD-K2, TBD-K3, TBD-12 đã chốt; trước đó trạng thái là "chưa xác định". | KPI-2, R-07 | FR-EVL-11…13 |
| AC-10 | Báo cáo hiệu quả có đủ cỡ mẫu, mẫu số, phương pháp, provenance; random và risk báo cáo riêng. | R-04 | FR-RPT-01…04 |
| AC-11 | Audit log có đủ actor, đối tượng, trước/sau, lý do cho mọi quyết định, phân xử, waiver, khoá reference. | R-05 | FR-SEC-05 |

## Giả định và phụ thuộc

| Mã | Giả định / phụ thuộc | Nếu sai thì |
|---|---|---|
| AS-01 | CVAT cho phép đọc job, frame, annotation, media qua API với token backend; xác định được thay đổi giữa hai lần đọc. | Không khoá được snapshot nhất quán; chặn toàn bộ luồng. |
| AS-02 | Có Detector baseline chạy được trên ảnh BDD100K với mapping đủ 10 lớp; artifact cố định được checksum. Pilot (v1.1): Faster R-CNN R-50-FPN 3x của model zoo BDD100K, huấn luyện trên tập `train`. | Engine Mô hình độc lập Not checked; không sinh được candidate E1/E2. |
| AS-03 | Detector không được huấn luyện trên ảnh của tập held-out (kiểm theo danh sách ảnh huấn luyện). Pilot (v1.1): danh sách ảnh huấn luyện là toàn bộ BDD100K `train`; ảnh thuộc `train` bị loại khỏi tập đánh giá. | Recall bị thổi phồng do rò rỉ dữ liệu; kết quả không hợp lệ. |
| AS-04 | QA Lead và ít nhất hai người xác minh độc lập sẵn sàng lập reference trước khi đo. Pilot (v1.1, CR-101): GT là nhãn gốc BDD100K; QA Lead duyệt và khoá reference, không cần người xác minh. | Không đo được KPI-1/KPI-2 (B-20). |
| AS-05 | Có ít nhất 4 reviewer tham gia thí nghiệm effort, trình độ tương đương. | Không cân bằng được hai nhánh; KPI-2 kém tin cậy. |
| AS-06 | Guideline gán nhãn BDD100K của dự án có rule ID và version. | Workspace chỉ hiện guideline dạng văn bản, không truy vết rule. |

## Tham số còn mở

| Mã | Nội dung | Người chốt | Hạn chốt |
|---|---|---|---|
| TBD-01 | Phiên bản CVAT được pin, URL, quyền token, danh sách endpoint thật. | Chủ CVAT, Tech Lead | Trước build adapter |
| TBD-02 | Cấu hình phần cứng app server, GPU server. | Tech Lead | Trước build |
| TBD-03 | Danh sách ảnh BDD100K, $N$ của tập hiệu chỉnh và held-out. | Data Owner, QA Lead | Trước lập reference |
| TBD-04 | Nguồn annotation cần review; có dùng lỗi chèn hay không. **Đã chốt:** tệp người học gán sẵn, không chèn lỗi (DEC-003). | Product Owner, QA Lead | Trước lập reference |
| TBD-05 | $\tau_m$, $\tau_{amb}$ cho matching. | QA Lead, đội mô hình | Trước lập reference |
| TBD-06 | $a_{min}$ và quy tắc ignore theo occlusion/truncation. | QA Lead | Trước lập reference |
| TBD-07 | Định nghĩa mức độ nghiêm trọng theo lớp và kích thước. | QA Lead | Trước pilot |
| TBD-08 | Duyệt đề xuất không bật VLM trong pilot M13. | Product Owner | Trước pilot |
| TBD-09 | Thời hạn lease và quy tắc gia hạn. | Product Owner | Trước build review |
| TBD-10 | Tỉ lệ lát kiểm tra ngẫu nhiên $r$. | QA Lead | Trước pilot |
| TBD-11 | Ngưỡng không thao tác $t_{idle}$; thời lượng buổi làm quen. | Product Owner | Trước thí nghiệm |
| TBD-12 | Cỡ mẫu thí nghiệm effort (frame, reviewer). Pilot (v1.1, CR-101): theo nguồn lực reviewer ngoài, khoá trong preregistration, không chạy pilot nhỏ. | Product Owner | 19/10/2026 |
| TBD-13 | Mục tiêu thời gian QC Run và độ trễ UI (NFR-01…03). | Tech Lead | Sau đo pilot |
| TBD-14 | Số lần retry và backoff. | Tech Lead | Sau đo pilot |
| TBD-15 | Thời hạn lưu audit log. | Product Owner | Trước triển khai |
| TBD-16 | $n_{min}$ issue dương mỗi nhóm để học score. | Đội mô hình | Trước khoá score |
| TBD-17 | RPO/RTO cho sao lưu PostgreSQL và Object Storage. | Tech Lead | Trước triển khai |
| TBD-19 | Danh sách điều kiện gate được phép waiver và policy từng điều kiện (B-11). | Product Owner, QA Lead | Trước pilot |
| TBD-20 | Tham số kỹ thuật phụ: timeout mỗi lượt kiểm VLM (nếu bật), $t_{gc}$ dọn blob mồ côi, $\varepsilon$ của `score_v0`, số chữ số làm tròn toạ độ khi chuẩn hoá hash. | Tech Lead, đội mô hình | Trước build tương ứng |
| TBD-21 | Đặc tả chi tiết Model Orchestrator (đầu vào, đầu ra, provenance) cho tổng hợp kết quả đánh giá engine (B-05). | Đội mô hình | Trước đo Metric engine |
| TBD-18 | Xác nhận giấy phép và điều khoản sử dụng BDD100K cho mục đích pilot và lưu trữ nội bộ. | Data Owner | Trước nạp dữ liệu |
| TBD-K1 | Ngưỡng đạt KPI-1. | Product Owner | Trước chạy held-out |
| TBD-K2 | Ngưỡng đạt KPI-2. | Product Owner | Trước thí nghiệm |
| TBD-K3 | Biên non-inferiority $\delta$ và $\delta_{fp}$. | Product Owner, QA Lead | Trước thí nghiệm |
| TBD-K4 | $E_{min}$, $E_{min,g}$. | QA Lead | Trước chạy held-out |

## Rủi ro

| Mã | Rủi ro | Khả năng | Tác động | Giảm thiểu |
|---|---|---|---|---|
| RK-01 | Detector baseline yếu trên ảnh đêm, đối tượng nhỏ ⇒ ít candidate E1/E2 đúng, KPI-1 thấp. | TB | Cao | Báo cáo theo slice; điểm nền $h(f)$ dùng đặc trưng ngày/đêm; cân nhắc Detector khác sau pilot (B-07). |
| RK-02 | Detector đã thấy ảnh held-out khi huấn luyện ⇒ recall bị thổi phồng. | TB | Cao | FR-EVL-05(b); chọn held-out từ phần chắc chắn không dùng huấn luyện. |
| RK-03 | Reference chậm hoặc tốn công (hai người gán toàn bộ). | Cao | Cao | Bắt đầu sớm (B-20); giới hạn $N$ theo power analysis; dùng CVAT task riêng cho người xác minh. |
| RK-04 | Reviewer ở nhánh assisted tin máy quá mức (automation bias), bỏ qua lỗi không có candidate. | TB | Cao | Lát ngẫu nhiên; Frame Review luôn hiển thị toàn ảnh; đo KPI-2b và residual. |
| RK-05 | Effort log sai do reviewer bỏ máy, mở nhiều tab. | TB | TB | Ngưỡng $t_{idle}$; một lease mỗi reviewer; loại phiên bất thường theo quy tắc khoá trước. |
| RK-06 | CVAT API không cho kiểm drift tin cậy. | Thấp | Cao | Thử adapter trên CVAT thật trước build (B-02); phương án dự phòng: tạm khoá sửa phạm vi khi export. |
| RK-07 | Ít lỗi E3 tự nhiên ⇒ không đủ mẫu kết luận theo nhóm. | Cao | Thấp | $E_{min,g}$; chỉ kết luận KPI tổng; lỗi chèn báo cáo riêng (BR-15). |
| RK-08 | Guideline BDD100K của dự án chưa có rule ID rõ. | TB | TB | QA Lead chuẩn hoá rule tối thiểu cho 10 lớp trước pilot (AS-06). |
| RK-09 | Thay đổi tham số sau khi thấy kết quả held-out. | TB | Cao | Pre-registration (bảng tương ứng trong labelX.html); audit mọi thay đổi version. |
