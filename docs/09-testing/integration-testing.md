---
id: labelx-integration-testing
title: Integration testing LabelX
type: reference
domain: testing
module: repository
tags: [integration, transactions, celery, cvat]
priority: 2
---

# Integration testing

PostgreSQL thật cho transaction/lease; Redis + worker thật cho retry/redelivery; Object Storage tạm cho upload-before-commit, checksum và orphan. Mỗi run dùng namespace riêng. Không dùng eager Celery/SQLite để kết luận distributed/concurrency đúng.

Ép lỗi ở ranh giới commit, replay cùng shard, hai reviewer claim đồng thời, snapshot drift R1/R2, identity/account mapping, stale If-Match/lease, rework unchanged revision và final run Partial. Mock CVAT bằng allowlist semantic read; không cho mutation annotation. Token và dữ liệu thật không vào PR jobs.

Live contract chỉ sau pin instance và quyền; request recorder giữ endpoint/method đã redacted. API response phải có scope/version/provenance; OpenAPI export và type frontend phải tương thích.

Nguồn: [test strategy](test-strategy.md), [DEC-001](../../.agent/governance/decisions/DEC-001.md), SRS NFR-05/06/07/15.
