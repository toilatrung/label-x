---
id: devops-overview
title: DevOps
type: reference
domain: devops
module: repository
tags: [devops, delivery, deployment]
priority: 3
---
# DevOps

CI/CD, triển khai và giám sát LabelX. Repo hiện chỉ có môi trường dev local (Docker Compose cho hạ tầng + `make`). CI/CD và production **chưa có**; topology production chờ **TBD-02**.

## Nội dung

- [ci-cd.md](ci-cd.md) — hiện trạng (chưa có CI) và pipeline **đề xuất** chạy `make check`.
- [deployment.md](deployment.md) — topology tham chiếu (SRS chương 10, DEC-001), dev local bằng compose, các mục production còn TBD.
- [monitoring.md](monitoring.md) — điểm vào sang [13-observability](../13-observability/index.md).
