---
id: database-overview
title: Database
type: reference
domain: database
module: repository
tags: [database, schema, migrations]
priority: 3
---
# Database

Phần này mô tả schema PostgreSQL, quy tắc migration và các truy vấn quan trọng của LabelX QC. Nguồn: ERD trong SRS (`fig:erd`) và A §22. Stack: PostgreSQL 17 + Django ORM (DEC-001).

## Contents

- [schema.md](schema.md) — các bảng, cột chính, khoá, ràng buộc unique cho idempotency và dedup, audit append-only
- [migrations.md](migrations.md) — quy tắc Django migrations, RunSQL cho append-only
- [queries.md](queries.md) — cấp lease bằng `SELECT … FOR UPDATE SKIP LOCKED`, ranking, coverage ledger, ghi shard idempotent, gate

Liên quan: [system-design.md](../02-architecture/system-design.md), [rest-api.md](../04-api/rest-api.md), [object-storage.md](../11-integrations/object-storage.md).
