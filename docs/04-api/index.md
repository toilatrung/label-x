---
id: api-overview
title: API Documentation
type: reference
domain: api
module: repository
tags: [api, contracts, events]
priority: 3
---
# API Documentation

## Purpose

Mục lục hợp đồng giao diện có thẩm quyền của LabelX QC: endpoint, schema, mã lỗi và Celery task.

## Contents

- [contract.md](contract.md) — intake: nguồn, kết quả kiểm tra, các mục còn mở
- [rest-api.md](rest-api.md) — REST API (DRF): endpoint, quyền, request/response, mã lỗi, idempotency
- [event-contracts.md](event-contracts.md) — Celery task: tên, payload, khoá idempotent, retry; ghi chú về domain event
- `graphql.md` — **không dùng**. Hệ thống chỉ có REST (SRS §9.3; DEC-001)

Schema OpenAPI được sinh tự động tại `/api/schema/` (drf-spectacular). Frontend sinh type từ schema này (DEC-001).
