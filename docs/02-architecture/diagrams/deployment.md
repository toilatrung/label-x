---
id: architecture-diagram-deployment
title: Sơ đồ triển khai LabelX QC
type: reference
domain: architecture
module: quality-control
tags: [architecture, diagram, deployment, mermaid]
priority: 2
---
# Sơ đồ triển khai

## Môi trường thật

Nguồn: SRS `fig:deployment`. Cấu hình phần cứng của app server và GPU server là **TBD-02**. RPO/RTO là **TBD-17**.

```mermaid
flowchart LR
    BR["Trình duyệt reviewer"]
    subgraph APP["App server (Linux)"]
        NX["Next.js frontend (DEC-001)<br/>vị trí host: TBD-02"]
        GU["Gunicorn + Django/DRF"]
        CW["Celery CPU workers<br/>queues: snapshot, cpu"]
        BEAT["Celery beat<br/>(django-celery-beat)"]
    end
    subgraph GPUS["GPU server"]
        GW["Celery GPU worker<br/>queue: gpu · Detector"]
    end
    subgraph DATA["Data"]
        PG[("PostgreSQL 17")]
        RD[("Redis 7")]
        OS[("Object Storage S3-compatible")]
    end
    CV["CVAT (hiện có)"]

    BR <-->|HTTPS| NX
    NX <-->|REST/JSON| GU
    BR -. deep link HTTPS .-> CV
    GU -->|HTTPS chỉ đọc| CV
    CW -->|HTTPS chỉ đọc| CV
    GU <--> PG
    GU <--> RD
    CW <--> PG
    CW <--> RD
    CW <--> OS
    GW <--> RD
    GW <--> PG
    GW <--> OS
    BEAT --> RD
```

Ràng buộc:

- Token CVAT chỉ nằm ở app server và worker, không bao giờ gửi xuống trình duyệt (FR-SNP-02; NFR-07).
- Ảnh chỉ nằm trong Object Storage nội bộ. Detector chạy trên GPU nội bộ (NFR-09).
- Frontend Next.js (DEC-001) không có trong sơ đồ triển khai của SRS. Việc chạy nó trên app server hay host riêng là **TBD-02**. Nếu trình duyệt gọi thẳng API thì cần cấu hình CORS và cookie session (`CORS_ALLOWED_ORIGINS`, `CORS_ALLOW_CREDENTIALS` trong settings).
- Không cần GPU worker thứ hai cho VLM, vì VLM không bật trong pilot (TBD-08).

## Dev local

Nguồn: [docker-compose.dev.yml](../../../infrastructure/docker-compose.dev.yml).

```mermaid
flowchart LR
    DEV["Máy dev<br/>Django runserver · Celery · Next.js dev"]
    subgraph Compose["docker compose: labelx-dev"]
        P[("postgres:17<br/>:5432 db labelx")]
        R[("redis:7-alpine<br/>:6379")]
        S[("seaweedfs S3<br/>:9000")]
        I["seaweedfs-init<br/>tạo bucket labelx-snapshots,<br/>labelx-evidence, labelx-reports"]
    end
    CV["CVAT instance thật<br/>(không trong compose)"]
    DEV --> P
    DEV --> R
    DEV --> S
    I --> S
    DEV -->|CVAT_BASE_URL| CV
```
