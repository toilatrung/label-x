---
id: architecture-diagram-component
title: Sơ đồ thành phần LabelX QC
type: reference
domain: architecture
module: quality-control
tags: [architecture, diagram, component, mermaid]
priority: 2
---
# Sơ đồ thành phần

Sơ đồ dựa trên SRS `fig:components` ([10-architecture.tex](../../label-x_system-requirement-specification/sections/10-architecture.tex)) và nguồn L (`docs/00-project/sources/mermaid-diagram.png`). Một số khối của L đã được lược bỏ hoặc hoãn theo quyết định chốt:

- **Guideline / RAG** và **Vector Index** bị thay bằng tra cứu trực tiếp rule (B-13).
- **Classifier** không bật (B-07).
- **VLM Verification** đề xuất không bật trong pilot (TBD-08).
- **Release Management** nằm ngoài phạm vi M13 (FR-GTE-04).

```mermaid
flowchart TB
    subgraph Client["Web client (Next.js)"]
        FE["Review Queues · Workspace · Escalations<br/>Evaluation · Report · Snapshot · Execution History"]
    end

    CVAT[("CVAT (hiện có)<br/>editor duy nhất")]

    subgraph Mono["Django + DRF — Modular Monolith"]
        ADP["cvat_adapter<br/>chỉ đọc · deep link"]
        SNP["snapshots<br/>hash · drift · khoá"]
        ORC["qc (Orchestrator)<br/>run · shard · ledger"]
        AGG["issues (Aggregation)<br/>candidate → issue"]
        RNK["ranking<br/>q_i · h(f) · s(f)"]
        REV["review<br/>lease · decision · rework"]
        EVL["evaluation<br/>reference · KPI · effort"]
        SEC["access · guidelines · gate · reports<br/>RBAC · audit · rule lookup"]
    end

    subgraph Workers["Celery workers"]
        CPU["CPU: Schema · Geometry · Duplicate<br/>Matching · Aggregation · Ranking"]
        GPU["GPU: Detector baseline"]
    end

    REDIS[("Redis<br/>broker · result backend")]
    PG[("PostgreSQL<br/>nguồn chuẩn trạng thái")]
    OS[("Object Storage<br/>ảnh · evidence · báo cáo")]
    MA[("Model artifact<br/>checksum · mapping")]

    FE <-->|REST/JSON| Mono
    FE -. deep link .-> CVAT
    ADP -->|HTTPS đọc| CVAT
    Mono <--> REDIS
    REDIS <--> CPU
    REDIS <--> GPU
    Mono <--> PG
    CPU <--> PG
    GPU <--> PG
    CPU <--> OS
    GPU <--> OS
    MA --> GPU
```

Ranh giới: worker AI (Detector) chỉ ghi Candidate và Evidence. Không có đường gọi nào từ worker tới quyết định, gate hay phân xử (A ADR-07; R-02).

Xem thêm: [system-design.md](../system-design.md), [deployment.md](deployment.md), [data-flow.md](data-flow.md).
