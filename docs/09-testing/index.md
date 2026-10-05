---
id: testing-overview
title: Testing
type: reference
domain: testing
module: repository
tags: [testing, quality, strategy]
priority: 2
---
# Testing

Chiến lược và kế hoạch kiểm thử cho LabelX — module Quality Control (M13). Mục tiêu là chứng minh R-01…R-07 (nguồn R) và AC-01…AC-11 (SRS chương 7) bằng phép kiểm và dữ liệu.

## Nội dung

| Tài liệu | Nội dung |
|---|---|
| [test-strategy.md](test-strategy.md) | Tầng kiểm thử; ánh xạ AC-01…AC-11 và R-01…R-07 sang unit/integration/E2E/pilot; NFR |
| [unit-testing.md](unit-testing.md) | pytest/pytest-django; quy tắc phải test: matching, suy ra lỗi, dedup, idempotency, state transition, quyền, coverage, scoring, thống kê |
| [integration-testing.md](integration-testing.md) | PostgreSQL/Redis/SeaweedFS qua Docker Compose; Celery retry/idempotency; adapter CVAT giả lập; API DRF |
| [e2e-testing.md](e2e-testing.md) | Kịch bản UC-01 → UC-11 qua API; E2E UI là TBD vì frontend chưa có test runner (DEC-001) |
| [acceptance-pilot.md](acceptance-pilot.md) | Điều kiện tiên quyết, giai đoạn pilot, pre-registration, KPI-1, thí nghiệm effort EX-01…EX-10, gate |

## Lệnh thường dùng

| Lệnh | Tác dụng |
|---|---|
| `make infra-up` | Bật PostgreSQL 17, Redis 7, SeaweedFS (S3) |
| `make test` | `cd src/backend && uv run pytest -q` |
| `make check` | lint + typecheck + test + validate-kit (chạy trước khi báo xong) |
| `make validate-kit` | Kiểm cấu trúc docs/.agent |

Liên quan: [Domain Model](../03-domain/index.md), [AI và đánh giá](../12-ai/index.md).
