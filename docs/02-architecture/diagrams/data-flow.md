---
id: architecture-diagram-data-flow
title: Sơ đồ luồng dữ liệu F-01 đến F-08
type: reference
domain: architecture
module: quality-control
tags: [architecture, diagram, data-flow, sequence, mermaid]
priority: 2
---
# Sơ đồ luồng dữ liệu

Các sơ đồ dưới đây chuyển SD-1…SD-4 trong SRS §5.2 ([05-dynamics.tex](../../label-x_system-requirement-specification/sections/05-dynamics.tex)) sang Mermaid. Mã F-xx theo nguồn R mục 5.

## Tổng quan F-01 → F-08

```mermaid
flowchart LR
    F1["F-01 Chọn scope<br/>đọc CVAT"] --> F2["F-02 Export · hash<br/>khoá snapshot"]
    F2 -->|drift| X["Snapshot failed<br/>drift_detected"]
    F2 --> F3["F-03 Engine + ledger<br/>CPU/GPU"]
    F3 -.->|không bật pilot| F4["F-04 VLM chọn lọc"]
    F3 --> F5["F-05 Gộp issue · xếp hạng<br/>lát ngẫu nhiên"]
    F5 --> F6["F-06 Review · quyết định<br/>phân xử"]
    F6 --> F7["F-07 Sửa trên CVAT<br/>re-check · verify"]
    F7 -->|snapshot gia tăng| F3
    F7 --> F8["F-08 Run cuối is_final<br/>gate · báo cáo"]
    F6 --> F8
```

## SD-1 — Tạo snapshot (F-01, F-02)

```mermaid
sequenceDiagram
    actor QA as QA Lead
    participant API as LabelX API
    participant W as Worker (queue snapshot)
    participant CV as CVAT API
    participant OS as Object Storage
    participant DB as PostgreSQL
    QA->>API: POST /api/snapshots {scope}
    API->>DB: kiểm quyền, tạo snapshot (pending) + audit
    API-->>QA: 202 {id}
    API->>W: snapshots.build_snapshot(snapshot_id)
    loop mỗi job trong scope
        W->>CV: GET job, annotations, meta
        CV-->>W: JSON, updated_date
        W->>W: chuẩn hoá + SHA-256 job
        W->>CV: GET ảnh frame
        W->>OS: PUT ảnh (khoá = sha256)
    end
    W->>CV: GET job meta lần 2
    alt không drift
        W->>DB: lưu hash, assignee, frame, annotation, khoá (locked)
    else có drift
        W->>DB: failed, reason=drift_detected, danh sách job
    end
```

## SD-2 — QC Run (F-03, F-05)

```mermaid
sequenceDiagram
    actor QA as QA Lead
    participant ORC as qc (Orchestrator)
    participant CPU as CPU worker
    participant GPU as GPU worker
    participant DB as PostgreSQL
    QA->>ORC: POST /api/runs {snapshot_id, config_version_id}
    ORC->>DB: tạo run (queued), work_unit theo shard
    par mỗi shard
        ORC->>CPU: schema / geometry / duplicate
        CPU->>DB: candidate + evidence + ledger (1 txn)
    and
        ORC->>GPU: detect theo lô
        GPU->>DB: prediction (1 txn)
        GPU->>CPU: match shard (chain)
        CPU->>DB: candidate E1/E2 + evidence + ledger (1 txn)
    end
    opt shard lỗi
        ORC->>GPU: retry cùng idempotency_key
    end
    ORC->>CPU: aggregate_run
    CPU->>DB: upsert issue theo (run_id, dedup_key)
    ORC->>CPU: score_run(score_version)
    CPU->>DB: frame_risk, rank, lát ngẫu nhiên
    ORC-->>QA: run Completed / Partial
```

## SD-3 — Review (F-06)

```mermaid
sequenceDiagram
    actor RV as Reviewer
    participant UI as Workspace
    participant API as LabelX API
    participant DB as PostgreSQL
    RV->>UI: Bắt đầu review
    UI->>API: POST /api/queues/{name}/next
    API->>DB: SELECT … FOR UPDATE SKIP LOCKED, bỏ frame mà reviewer là assignee
    API-->>UI: frame + lease
    UI->>API: GET /api/frames/{id}/issues
    UI->>API: GET /api/guidelines/rules/{rule_id}?version=
    RV->>UI: Xác nhận / Bác bỏ + lý do
    UI->>API: POST /api/issues/{id}/decisions (Idempotency-Key)
    API->>DB: kiểm lease, self-review · decision + audit (1 txn)
    API-->>UI: 201 hoặc 403 / 409
    RV->>UI: Đã review xong
    UI->>API: POST /api/frames/{id}/complete
    API->>DB: kiểm FR-REV-13, trả lease, dừng effort
```

## SD-4 — Rework và run cuối (F-07, F-08)

```mermaid
sequenceDiagram
    actor RV as Reviewer
    participant API as LabelX API
    actor AN as Annotator
    participant CV as CVAT
    participant ORC as qc (Orchestrator)
    RV->>API: POST /api/rework
    API-->>AN: yêu cầu sửa + deep link
    AN->>CV: mở job/frame, sửa box
    AN->>API: POST /api/rework/{id}/submitted
    API->>ORC: snapshot gia tăng các job bị ảnh hưởng
    alt hash không đổi
        API-->>AN: 409 chưa có thay đổi
    else revision mới
        ORC->>ORC: re-check engine liên quan
    end
    RV->>API: POST /api/rework/{id}/verify
    API-->>RV: Đã đóng hoặc Mở lại
    opt mọi yêu cầu sửa của scope đã đóng
        API->>ORC: snapshot toàn scope + run is_final
        ORC->>ORC: liên kết verification trước đó
    end
    alt run cuối Partial/Failed hoặc có issue mới
        API-->>RV: issue mới vào hàng đợi, gate chưa đạt
    end
```
