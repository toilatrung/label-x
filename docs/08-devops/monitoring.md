---
id: devops-monitoring
title: Monitoring LabelX
type: reference
domain: devops
module: repository
tags: [devops, monitoring, alerting, observability]
priority: 4
---
# Monitoring LabelX

Nội dung giám sát và cảnh báo nằm ở mục **13-observability**. Tài liệu này chỉ là điểm vào cho người vận hành.

- [../13-observability/index.md](../13-observability/index.md) — tổng quan, hiện trạng.
- [../13-observability/logging.md](../13-observability/logging.md) — log có cấu trúc kèm `run_id`, `snapshot_id`, `request_id` (NFR-12).
- [../13-observability/metrics.md](../13-observability/metrics.md) — metric hàng đợi Celery, thời gian shard, tỉ lệ lỗi, lease, effort.
- [../13-observability/alerts-and-slo.md](../13-observability/alerts-and-slo.md) — SLO đề xuất theo NFR (TBD-13) và cảnh báo.

Hiện trạng: repo **chưa có** công cụ giám sát (Prometheus, Grafana, Sentry…) hay cấu hình `LOGGING` riêng trong Django. Hạ tầng dev có healthcheck cho PostgreSQL, Redis, SeaweedFS trong `infrastructure/docker-compose.dev.yml`, và `make infra-logs` để xem log hạ tầng.
