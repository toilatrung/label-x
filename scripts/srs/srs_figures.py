"""Hình của SRS M13 dạng Mermaid/SVG, khớp các hình TikZ trong bản LaTeX (theo nhãn \\label)."""
from __future__ import annotations

import html


def mm(src: str) -> str:
    return '<pre class="mermaid">' + html.escape(src.strip("\n"), quote=False) + "</pre>"


FIGURES: dict[str, str] = {}

FIGURES["scopeflow"] = mm("""
flowchart LR
  A["Annotation<br>từ CVAT"] --> B["Phân tích<br>nghi vấn"] --> C["Xếp hạng<br>frame"] --> D["Reviewer xem bằng chứng<br>& phân xử"] --> E["Báo cáo<br>hiệu quả"]
""")

FIGURES["fig:context"] = mm("""
flowchart LR
  RV(["👤 Reviewer"]) -- "review, quyết định" --> SYS
  AN(["👤 Annotator"])
  SYS -- "yêu cầu sửa, deep link" --> AN
  QL(["👤 QA Lead"]) -- "chạy phân tích, phân xử, reference" --> SYS
  QA(["👤 QC Admin"]) -- "cấu hình, quyền" --> SYS
  PO(["👤 Product / Data Owner"]) -. "đọc báo cáo hiệu quả" .- SYS
  SYS["<b>LabelX</b><br>Module Quality Control<br>M13 Reviewer Prioritization"]
  CVAT[("CVAT<br>nguồn annotation, editor")] -- "đọc, chỉ đọc" --> SYS
  SYS <--> OS[("Object Storage<br>ảnh, evidence")]
  SYS <-- "inference" --> DET[["Detector baseline<br>GPU worker"]]
  AN -. "sửa annotation" .-> CVAT
""").replace("👤 ", "")

FIGURES["fig:functions"] = mm("""
flowchart LR
  M1["<b>1. Thu thập</b><br>CVAT Adapter chỉ đọc<br>Snapshot & hash<br>Kiểm drift"] --> M2["<b>2. Phân tích nghi vấn</b><br>Schema/Taxonomy<br>Geometry · Duplicate<br>Detector + Matching"]
  M2 --> M3["<b>3. Hợp nhất & xếp hạng</b><br>Candidate → Issue<br>Risk score s f<br>Ranking + audit slice"]
  M3 --> M4["<b>4. Review & phân xử</b><br>Hàng đợi ưu tiên<br>Workspace + evidence<br>Escalation"]
  M4 --> M5["<b>5. Đo & báo cáo</b><br>Reference & Recall@k<br>Effort log<br>Báo cáo hiệu quả"]
  S1["<b>Hỗ trợ</b><br>Guideline lookup<br>Rework + re-check<br>Gate tối thiểu"]
  S2["<b>Nền tảng</b><br>RBAC · Lease<br>Audit append-only<br>Coverage ledger"]
  M4 -.-> S1 -.-> M1
  S2 -.- M3
""")

FIGURES["fig:split"] = mm("""
flowchart LR
  P["Ảnh BDD100K trong phạm vi<br>nhóm theo video nguồn"] --> CAL["<b>Tập hiệu chỉnh</b><br>chọn trọng số, ngưỡng, k*"]
  P --> HO["<b>Tập held-out</b><br>chỉ dùng đo nghiệm thu"]
  CAL --> LOCK["Reference tập hiệu chỉnh → học,<br>khoá công thức điểm, ngưỡng, quy tắc dừng"]
  HO --> REF["Reference held-out độc lập<br>được duyệt & khoá riêng"]
  LOCK -- "áp dụng 1 lần" --> REF
  CAL ~~~ NOTE["Hai tập không giao nhau theo video nguồn"]
""")

FIGURES["fig:reference"] = mm("""
flowchart LR
  S["Snapshot tập đánh giá<br>ảnh, đã khoá"] --> V1["Người xác minh 1<br>gán GT toàn bộ frame"]
  S --> V2["Người xác minh 2<br>gán GT toàn bộ frame"]
  V1 --> D{"Khớp?"}
  V2 --> D
  D -- "có" --> GT["GT<br>khoá version"]
  D -- "không" --> ADJ["QA Lead<br>phân xử"] --> GT
  GT --> DER["Suy ra tập lỗi E<br>GT vs annotation đang review"]
  DER --> RV["Duyệt danh sách lỗi<br>sửa mapping nếu sai"]
  RV -. "suy lại khi sửa mapping" .-> DER
  RV --> LK["Tập lỗi khoá version<br>+ mapping, ngưỡng"]
  N["Người xác minh không xem<br>ranking, candidate, risk score"] -.- D
""")

FIGURES["fig:errorexamples"] = """
<svg class="fig" viewBox="0 0 900 230" role="img" aria-label="Minh hoạ ba nhóm lỗi">
  <rect x="1" y="1" width="898" height="228" fill="#f3f4f6" stroke="#e3e6ea"/>
  <g font-size="13" text-anchor="middle">
    <text x="90" y="30" font-weight="600">E1 thiếu box</text>
    <rect x="35" y="55" width="110" height="110" fill="none" stroke="#146c43" stroke-width="3"/>
    <text x="90" y="195" fill="#146c43">GT car</text>
    <text x="270" y="30" font-weight="600">Đúng</text>
    <rect x="215" y="55" width="110" height="110" fill="none" stroke="#146c43" stroke-width="3"/>
    <rect x="221" y="61" width="110" height="110" fill="none" stroke="#1d5ea8" stroke-width="2" stroke-dasharray="6 4"/>
    <text x="270" y="195" fill="#1d5ea8">annotation car</text>
    <text x="450" y="30" font-weight="600">E2 sai lớp</text>
    <rect x="395" y="55" width="110" height="110" fill="none" stroke="#146c43" stroke-width="3"/>
    <rect x="401" y="61" width="110" height="110" fill="none" stroke="#b42318" stroke-width="2" stroke-dasharray="6 4"/>
    <text x="450" y="195" fill="#b42318">GT truck / annotation car</text>
    <text x="640" y="30" font-weight="600">E3 trùng box</text>
    <rect x="585" y="55" width="110" height="110" fill="none" stroke="#146c43" stroke-width="3"/>
    <rect x="591" y="61" width="110" height="110" fill="none" stroke="#1d5ea8" stroke-width="2" stroke-dasharray="6 4"/>
    <rect x="579" y="49" width="110" height="110" fill="none" stroke="#b42318" stroke-width="2" stroke-dasharray="6 4"/>
    <text x="640" y="195" fill="#b42318">box dư = 1 lỗi</text>
    <text x="810" y="30" font-weight="600">Box thừa</text>
    <rect x="765" y="75" width="90" height="70" fill="none" stroke="#6b7280" stroke-width="2" stroke-dasharray="6 4"/>
    <text x="810" y="195" fill="#6b7280">ngoài KPI (BR-06)</text>
  </g>
</svg>"""

FIGURES["fig:erd"] = mm("""
erDiagram
  DATASET ||--|{ SNAPSHOT : "1..*"
  SNAPSHOT ||--|{ QCRUN : "1..*"
  QCRUN ||--|{ ENGINE_RESULT : "1..*"
  SNAPSHOT ||--|{ FRAME : "1..*"
  FRAME ||--o{ ANNOTATION : "0..*"
  QCRUN ||--o{ CANDIDATE : "0..*"
  CANDIDATE ||--|{ EVIDENCE : "1..*"
  ISSUE ||--|{ CANDIDATE : "gộp *..1"
  CANDIDATE }o--|| FRAME : "thuộc frame"
  FRAME ||--o{ FRAME_RISK : "1 bản ghi mỗi run"
  QCRUN ||--o{ FRAME_RISK : "ranking của run"
  ISSUE ||--o{ REVIEW_DECISION : "0..*"
  ISSUE ||--o| REWORK_REQUEST : "0..1"
  FRAME ||--o{ GT_REF_ERROR : "0..*"
  FRAME_RISK ||--o{ EFFORT_LOG : "effort theo frame"
  REVIEW_DECISION ||--|{ AUDIT_LOG : "ghi cùng transaction"
  DATASET { string cvat_project_id string taxonomy_version string guideline_version }
  SNAPSHOT { string revision_hash string created_by datetime locked_at json assignee_map string parent_snapshot }
  QCRUN { string config_version int seed json engine_versions string status bool is_final }
  ENGINE_RESULT { string engine string status int eligible_units int completed_units }
  FRAME { string frame_key string image_uri string image_checksum string weather string scene string timeofday }
  ANNOTATION { string cvat_shape_id string label json bbox json attributes }
  CANDIDATE { string engine string family json features float score string dedup_key }
  EVIDENCE { string type string payload_uri json pred_bbox float conf float iou }
  ISSUE { string family string severity string state string lease_owner string priority }
  FRAME_RISK { float score int rank string score_version json contributions }
  REVIEW_DECISION { string actor string decision string reason string rule_id datetime started_at datetime ended_at }
  REWORK_REQUEST { string assignee string deep_link string fixed_revision string verified_by }
  GT_REF_ERROR { string ref_version string gt_object_or_extra_ann string family string mapping_ver }
  EFFORT_LOG { string actor string arm string frame string activity int active_ms }
  AUDIT_LOG { string actor string action json before_after string revision string reason }
""")

FIGURES["fig:usecase"] = mm("""
flowchart LR
  RV(["Reviewer"]); AN(["Annotator"]); QA(["QC Admin"]); QL(["QA Lead"]); PO(["Product / Data Owner"])
  CVAT[["«system» CVAT"]]; DET[["«system» Detector"]]
  subgraph SYS["LabelX — M13 Reviewer Prioritization"]
    U1(["UC-01 Tạo snapshot từ CVAT"]); U2(["UC-02 Chạy phân tích nghi vấn"]); U3(["UC-03 Chấm điểm & xếp hạng frame"])
    U4(["UC-04 Làm việc theo hàng đợi ưu tiên"]); U5(["UC-05 Xem bằng chứng & quyết định"]); U6(["UC-06 Chuyển cấp & phân xử"])
    U7(["UC-07 Rework & kiểm lại sau sửa"]); U8(["UC-08 Lập & khoá reference"]); U9(["UC-09 Đo Recall@20%"])
    U10(["UC-10 Đo effort baseline/assisted"]); U11(["UC-11 Xem & xuất báo cáo hiệu quả"])
    U12(["UC-12 Tra cứu guideline"]); U13(["UC-13 Quản lý quyền & audit"]); U14(["UC-14 Kiểm Quality Gate tối thiểu"])
  end
  QA --- U1 & U2 & U3 & U13
  QL --- U1 & U2 & U6 & U8 & U9 & U11 & U14
  RV --- U4 & U5 & U6 & U7 & U12
  AN --- U7
  PO --- U10 & U11
  CVAT --- U1 & U7
  DET --- U2
  U2 -. "include" .-> U1
  U3 -. "include" .-> U2
  U5 -. "include" .-> U4
  U6 -. "extend" .-> U5
  U7 -. "extend" .-> U5
  U12 -. "extend" .-> U5
  U9 -. "include" .-> U8
  U14 -. "include" .-> U7
  classDef sup fill:#fdf2d8,stroke:#8a5300
  class U12,U13,U14 sup
""")

FIGURES["fig:workflow"] = mm("""
flowchart LR
  subgraph L0["CVAT"]
    C1["API đọc job,<br>annotation, ảnh"]
  end
  subgraph L5["Annotator"]
    N1["Sửa trên CVAT<br>qua deep link"]
  end
  subgraph L1["Vận hành QC: QA Lead chạy, QC Admin cấu hình"]
    ST((" ")) --> A1["Chọn phạm vi<br>tạo snapshot"]
    A2["Chọn cấu hình<br>chạy QC Run"]
  end
  subgraph L2["Hệ thống LabelX"]
    S1["Chuẩn hoá, hash<br>kiểm drift, khoá"]
    S2["Engine + Detector<br>matching, ledger"]
    S3["Gộp issue, tính s f,<br>xếp hạng"]
    S4["Snapshot mới<br>re-check"]
    S5["QC run cuối<br>gate, báo cáo"]
  end
  subgraph L3["Reviewer"]
    R1["Nhận frame<br>theo hàng đợi"] --> R2["Xem evidence<br>ra quyết định"]
    R3["Xác minh<br>sau sửa"]
  end
  subgraph L4["QA Lead phân xử"]
    Q1["Phân xử; Gap thì<br>chờ guideline mới"]
  end
  A1 -- "F-01" --> C1 --> S1
  S1 -- "F-02" --> A2 --> S2
  S2 -- "F-03" --> S3 -- "F-05" --> R1
  R2 -- "F-06" --> D1{"Cần<br>phân xử?"}
  D1 -- "có" --> Q1 --> D2
  D1 -- "không" --> D2{"Lỗi<br>cần sửa?"}
  D2 -- "có" --> N1 -- "F-07" --> S4 --> R3
  R3 -- "chưa đạt" --> N1
  R3 -- "đạt" --> S5
  D2 -- "không" --> S5
  S5 -- "F-08" --> EN(((" ")))
""")

FIGURES["fig:sd1"] = mm("""
sequenceDiagram
  actor ADM as QA Lead
  participant API as LabelX API
  participant WK as Snapshot worker
  participant CV as CVAT API
  participant OS as Object Storage
  participant DB as PostgreSQL
  ADM->>API: POST /snapshots, scope
  API->>DB: kiểm quyền, tạo bản ghi
  DB-->>API: Pending
  API-)WK: enqueue tạo snapshot
  API-->>ADM: 202 snapshot_id
  loop mỗi job trong scope
    WK->>CV: GET job, annotations, meta
    CV-->>WK: JSON, updated_date
    WK->>WK: chuẩn hoá + hash job
    WK->>CV: GET frame ảnh
    CV-->>WK: bytes
    WK->>OS: PUT ảnh + checksum
    OS-->>WK: uri
  end
  WK->>CV: GET job meta lần 2
  CV-->>WK: updated_date
  alt không drift
    WK->>DB: khoá snapshot, lưu hash, assignee
    DB-->>WK: Locked
  else có drift
    WK->>DB: đánh dấu DriftDetected
    DB-->>WK: Failed
  end
""")

FIGURES["fig:sd2"] = mm("""
sequenceDiagram
  actor ADM as QA Lead
  participant ORC as QC Orchestrator
  participant CPU as CPU worker
  participant GPU as GPU worker · Detector
  participant AGG as Aggregation
  participant RNK as Ranking
  participant DB as PostgreSQL
  ADM->>ORC: POST /runs: snapshot, config
  ORC-->>ADM: run_id, Queued
  loop mỗi shard frame, các shard chạy song song
    ORC->>CPU: schema, geometry, duplicate
    CPU->>DB: ghi candidate + ledger, 1 txn
    CPU-->>ORC: candidates
    ORC->>GPU: detect theo lô
    GPU-->>ORC: predictions
    ORC->>CPU: matching pred và ann
    CPU->>DB: ghi candidate + evidence + ledger
    CPU-->>ORC: E1/E2 candidates
  end
  opt shard lỗi
    ORC-)GPU: retry với khoá idempotent
  end
  ORC->>AGG: gộp candidate → issue
  AGG->>DB: upsert theo dedup_key
  ORC->>RNK: score: run, score_version
  RNK->>DB: lưu FrameRisk, audit slice
  ORC-)ADM: run Completed/Partial
""")

FIGURES["fig:sd3"] = mm("""
sequenceDiagram
  actor RV as Reviewer
  participant UI as Review Workspace
  participant API as LabelX API
  participant GD as Guideline lookup
  participant DB as PostgreSQL
  RV->>UI: Bắt đầu review
  UI->>API: POST /queue/next
  API->>DB: kiểm self-review, cấp lease
  API-->>UI: frame, lease
  UI-)API: effort start
  RV->>UI: chọn issue
  UI->>API: GET /issues/id/evidence
  API-->>UI: pred, conf, IoU
  UI->>GD: GET rule, case
  GD-->>UI: VEH-03 v1.2, cases
  RV->>UI: Xác nhận / Bác bỏ + lý do
  UI->>API: POST /decisions
  API->>DB: kiểm lease còn hạn, self-review theo assignee tại snapshot
  API->>DB: decision + audit, 1 txn
  API-->>UI: 201 hoặc 403/409
  RV->>UI: Đã review xong frame
  UI-)API: effort stop
  UI->>API: release lease
  UI-->>RV: frame kế tiếp
""")

FIGURES["fig:sd4"] = mm("""
sequenceDiagram
  actor RV as Reviewer
  participant API as LabelX API
  actor AN as Annotator
  participant CV as CVAT
  participant ORC as QC Orchestrator
  RV->>API: Yêu cầu sửa issue
  API-->>RV: RW-id
  API-)AN: thông báo + deep link
  AN->>CV: mở job/frame, sửa box
  AN->>API: Đã sửa RW-id
  API->>ORC: snapshot mới, job bị ảnh hưởng
  ORC->>ORC: re-check engine liên quan
  ORC-->>API: revision mới
  RV->>API: Xác minh trên revision mới
  API-->>RV: Resolved / Reopened
  opt mọi yêu cầu sửa của phạm vi đã Resolved
    API->>ORC: snapshot toàn phạm vi + QC run cuối is_final
    ORC->>ORC: liên kết verification trước đó
    API->>API: kiểm Completed + coverage engine bắt buộc
  end
  alt run cuối Partial/Failed hoặc có issue mới
    API-)RV: issue mới vào hàng đợi, gate chưa đạt
  end
""")

FIGURES["fig:sd5"] = mm("""
sequenceDiagram
  actor QL as QA Lead
  participant API as LabelX API
  participant EV as Evaluation service
  participant DB as PostgreSQL
  QL->>API: khoá reference GT và tập lỗi E
  API-->>QL: ref v
  QL->>API: POST /evaluations: run, ref, k
  API->>EV: evaluate
  EV->>DB: đọc ranking, tập lỗi, effort log
  DB-->>EV: dữ liệu
  EV->>EV: kiểm số lỗi ≥ E_min
  EV->>EV: Recall@k + đối chứng + bootstrap
  EV->>EV: KPI-2, non-inferiority
  EV->>DB: lưu evaluation run + provenance
  EV-->>API: kết quả
  API-->>QL: eval_id
""")

FIGURES["fig:runstate"] = mm("""
stateDiagram-v2
  [*] --> Queued
  Queued --> Running: worker nhận
  Running --> Completed: mọi shard ok
  Running --> Partial: có shard lỗi sau retry
  Running --> Failed: lỗi toàn cục
  Queued --> Cancelled: huỷ
  Running --> Cancelled: huỷ
  Partial --> Running: chạy lại shard lỗi
""")

FIGURES["fig:issuestate"] = mm("""
stateDiagram-v2
  state "Chờ review" as O
  state "Đang review" as IR
  state "Đã xác nhận" as CF
  state "Bác bỏ (cảnh báo sai)" as RJ
  state "Chờ phân xử" as ES
  state "Chờ sửa" as FP
  state "Chờ kiểm lại" as RC
  state "Đã đóng (Resolved)" as RS
  state "Mở lại" as RO
  [*] --> O
  O --> IR: cấp lease
  IR --> O: lease hết hạn
  IR --> CF: xác nhận
  IR --> RJ: bác bỏ
  IR --> ES: chưa chắc / chuyển cấp
  ES --> CF: QA Lead xác nhận
  ES --> RJ: QA Lead bác bỏ
  ES --> ES: Guideline Gap
  CF --> FP: yêu cầu sửa
  FP --> RC: annotator đã sửa
  RC --> RS: verify đạt
  RC --> RO: verify chưa đạt
  RO --> FP
  RS --> [*]
  RJ --> [*]
""")

FIGURES["fig:framestate"] = mm("""
stateDiagram-v2
  state "Chưa review" as U
  state "Đang review (có lease)" as L
  state "Đã review" as D
  state "Còn issue chờ phân xử / sửa" as W
  state "Hoàn tất (run cuối)" as V
  [*] --> U
  U --> L: cấp lease
  L --> U: lease hết hạn
  L --> D: xong
  D --> W: có issue mở
  W --> V: đóng hết + run cuối đạt
  D --> V: không còn issue
""")


def _poly(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{60 + x * 6.4:.1f},{300 - y * 2.6:.1f}" for x, y in points)


FIGURES["fig:recallcurve"] = f"""
<svg class="fig" viewBox="0 0 760 360" role="img" aria-label="Đường Recall@k minh hoạ">
  <g stroke="#e3e6ea">{''.join(f'<line x1="{60 + v * 6.4}" y1="40" x2="{60 + v * 6.4}" y2="300"/><line x1="60" y1="{300 - v * 2.6}" x2="700" y2="{300 - v * 2.6}"/>' for v in range(0, 101, 20))}</g>
  <g font-size="11" fill="#6b7280" text-anchor="middle">{''.join(f'<text x="{60 + v * 6.4}" y="316">{v}</text>' for v in range(0, 101, 20))}</g>
  <g font-size="11" fill="#6b7280" text-anchor="end">{''.join(f'<text x="52" y="{304 - v * 2.6}">{v}</text>' for v in range(0, 101, 20))}</g>
  <text x="380" y="340" font-size="12" text-anchor="middle" fill="#4b5262">Tỉ lệ frame đã review theo ranking (%)</text>
  <text x="16" y="170" font-size="12" text-anchor="middle" fill="#4b5262" transform="rotate(-90 16 170)">Tỉ lệ lỗi reference trong phần đã review (%)</text>
  <polyline fill="none" stroke="#6b7280" stroke-width="2" stroke-dasharray="6 4" points="{_poly([(0, 0), (100, 100)])}"/>
  <polyline fill="none" stroke="#8a5300" stroke-width="2" points="{_poly([(0, 0), (10, 17), (20, 31), (40, 52), (60, 70), (80, 86), (100, 100)])}"/>
  <polyline fill="none" stroke="#1d5ea8" stroke-width="3" points="{_poly([(0, 0), (5, 24), (10, 40), (20, 62), (40, 82), (60, 92), (80, 97), (100, 100)])}"/>
  <polyline fill="none" stroke="#146c43" stroke-width="1.5" points="{_poly([(0, 0), (5, 48), (10, 78), (15, 95), (20, 100), (100, 100)])}"/>
  <line x1="{60 + 20 * 6.4}" y1="40" x2="{60 + 20 * 6.4}" y2="300" stroke="#b42318" stroke-dasharray="4 4"/>
  <text x="{66 + 20 * 6.4}" y="290" font-size="12" fill="#b42318">k = 20%</text>
  <g font-size="12">
    <line x1="470" y1="200" x2="495" y2="200" stroke="#6b7280" stroke-width="2" stroke-dasharray="6 4"/><text x="502" y="204">Ngẫu nhiên (kỳ vọng)</text>
    <line x1="470" y1="220" x2="495" y2="220" stroke="#8a5300" stroke-width="2"/><text x="502" y="224">Heuristic mật độ (minh hoạ)</text>
    <line x1="470" y1="240" x2="495" y2="240" stroke="#1d5ea8" stroke-width="3"/><text x="502" y="244">Ranking M13 (minh hoạ)</text>
    <line x1="470" y1="260" x2="495" y2="260" stroke="#146c43" stroke-width="1.5"/><text x="502" y="264">Oracle (minh hoạ)</text>
  </g>
</svg>"""

FIGURES["fig:crossover"] = mm("""
flowchart LR
  D["Dữ liệu thí nghiệm<br>chia ngẫu nhiên D1, D2<br>phân tầng theo video, slice"]
  D --> A1["<b>Chuỗi AB · đợt 1</b><br>Baseline trên D1"] --> A2["<b>Chuỗi AB · đợt 2</b><br>Assisted trên D2"]
  D --> B1["<b>Chuỗi BA · đợt 1</b><br>Assisted trên D1"] --> B2["<b>Chuỗi BA · đợt 2</b><br>Baseline trên D2"]
  classDef base fill:#e7effa,stroke:#1d5ea8
  classDef asst fill:#e6f4ec,stroke:#146c43
  class A1,B2 base
  class A2,B1 asst
""")

FIGURES["fig:workspace"] = """
<svg class="fig" viewBox="0 0 900 520" role="img" aria-label="Phác thảo Review Workspace">
  <rect x="1" y="1" width="898" height="518" fill="#fff" stroke="#e3e6ea"/>
  <rect x="1" y="1" width="898" height="40" fill="#f3f4f6"/>
  <text x="14" y="26" font-size="13"><tspan font-weight="700">LabelX</tspan> · Review Workspace · Job 2272 · Frame 00428 / 00599 · rank 12 / 3.000</text>
  <rect x="770" y="10" width="118" height="22" fill="#fff" stroke="#8c93a0"/><text x="829" y="26" font-size="12" text-anchor="middle">Mở trong CVAT</text>
  <rect x="14" y="52" width="96" height="22" fill="#eef1f5" stroke="#1f2933"/><text x="62" y="68" font-size="12" text-anchor="middle">Issue Review</text>
  <rect x="116" y="52" width="100" height="22" fill="#fff" stroke="#8c93a0"/><text x="166" y="68" font-size="12" text-anchor="middle">Frame Review</text>
  <rect x="14" y="84" width="550" height="370" fill="#f3f4f6" stroke="#e3e6ea"/>
  <rect x="60" y="300" width="120" height="96" fill="none" stroke="#1d5ea8" stroke-width="2"/><text x="60" y="294" font-size="12" fill="#1d5ea8">car #12</text>
  <rect x="300" y="250" width="156" height="144" fill="none" stroke="#1d5ea8" stroke-width="2"/><text x="300" y="244" font-size="12" fill="#1d5ea8">car #18</text>
  <rect x="294" y="244" width="168" height="156" fill="none" stroke="#b42318" stroke-width="2" stroke-dasharray="6 4"/><text x="294" y="416" font-size="12" fill="#b42318">mô hình: truck · 0.81</text>
  <rect x="204" y="140" width="48" height="72" fill="none" stroke="#b42318" stroke-width="2" stroke-dasharray="6 4"/><text x="228" y="132" font-size="12" fill="#b42318" text-anchor="middle">E1? traffic sign · 0.74</text>
  <text x="14" y="476" font-size="12" fill="#6b7280">Nét liền: annotation · Nét đứt: Detector · Bấm object để tạo issue</text>
  <text x="14" y="500" font-size="12">‹ Frame trước     Frame sau ›</text>
  <rect x="580" y="84" width="306" height="370" fill="#fff" stroke="#e3e6ea"/>
  <g font-size="12">
    <text x="592" y="106"><tspan font-weight="700">QC-00128</tspan> · Issue 1/3 · <tspan fill="#b42318">Cao</tspan></text>
    <text x="592" y="126">Nghi sai lớp (E2): car hay truck</text>
    <text x="592" y="156" font-weight="700">Bằng chứng</text>
    <text x="592" y="174">Annotation: car</text>
    <text x="592" y="192">Detector: truck · conf 0.81 · IoU 0.93</text>
    <text x="592" y="210">Đóng góp vào s(f): 0.62 / 1.48</text>
    <text x="592" y="240" font-weight="700">Hướng dẫn · VEH-03 · v1.2 §3.2</text>
    <text x="592" y="258">Case tương tự: CASE-021, CASE-034</text>
    <text x="592" y="288" font-weight="700">Quyết định</text>
  </g>
  <g font-size="12">
    <rect x="592" y="300" width="96" height="24" fill="#fff" stroke="#8c93a0"/><text x="640" y="317" text-anchor="middle">Xác nhận lỗi</text>
    <rect x="696" y="300" width="96" height="24" fill="#fff" stroke="#8c93a0"/><text x="744" y="317" text-anchor="middle">Bác bỏ</text>
    <rect x="592" y="332" width="96" height="24" fill="#fff" stroke="#8c93a0"/><text x="640" y="349" text-anchor="middle">Chưa chắc chắn</text>
    <rect x="696" y="332" width="96" height="24" fill="#fff" stroke="#8c93a0"/><text x="744" y="349" text-anchor="middle">Yêu cầu sửa</text>
    <rect x="592" y="364" width="110" height="24" fill="#fff" stroke="#8c93a0"/><text x="647" y="381" text-anchor="middle">Chuyển cấp trên</text>
    <rect x="592" y="414" width="130" height="26" fill="#1f2933"/><text x="657" y="432" text-anchor="middle" fill="#fff">Đã review xong</text>
  </g>
</svg>"""

FIGURES["fig:components"] = mm("""
flowchart TB
  FE["<b>Web client · Next.js</b><br>Review Queues, Workspace,<br>Escalations, Evaluation, Report"]
  CVAT[("CVAT")]
  subgraph MONO["Django + DRF — Modular Monolith"]
    M1["CVAT Adapter<br>chỉ đọc"]; M2["Snapshot"]; M3["QC Orchestrator<br>run, shard, ledger"]; M4["Aggregation<br>candidate → issue"]
    M5["Ranking"]; M6["Review Workflow<br>lease, decision, rework"]; M7["Evaluation<br>reference, KPI, effort"]; M8["Auth, RBAC,<br>Audit, Guideline"]
  end
  CW["<b>Celery CPU workers</b><br>Schema, Geometry, Duplicate,<br>Matching, Ranking"]
  GW["<b>Celery GPU worker</b><br>Detector baseline"]
  RD["<b>Redis</b><br>broker, cache"]
  PG[("<b>PostgreSQL</b><br>snapshot, run, issue, lease,<br>decision, audit, effort")]
  OS[("<b>Object Storage</b><br>ảnh, evidence, báo cáo")]
  MR["<b>Model artifact</b><br>checksum, mapping"]
  FE <-- "REST/JSON" --> MONO
  CVAT -- "đọc" --> M1
  FE -. "deep link" .-> CVAT
  MONO <--> CW & GW & RD
  CW <--> PG
  MONO <--> PG
  GW <--> OS
  MR --> GW
""")

FIGURES["fig:deployment"] = mm("""
flowchart LR
  subgraph APP["App server Linux"]
    G["Gunicorn + Django/DRF"]; C["Celery CPU workers"]
  end
  subgraph GPU["GPU server"]
    GW["Celery GPU worker<br>Detector"]
  end
  subgraph DATA["Data"]
    PG[("PostgreSQL")]; RD[("Redis")]; OS[("Object Storage")]
  end
  CV["CVAT hiện có"] -- "HTTPS, đọc" --> APP
  BR["Trình duyệt reviewer"] <-- "HTTPS" --> APP
  APP <--> GPU
  GPU <--> DATA
  APP <--> DATA
""")
