---
id: architecture-overview
title: Architecture
type: reference
domain: architecture
module: repository
tags: [architecture, design, decisions]
priority: 2
---
# Architecture

## Purpose

Mục lục tài liệu kiến trúc có thẩm quyền của LabelX Quality Control: quyết định, thiết kế hệ thống, sơ đồ, ràng buộc và ranh giới kỹ thuật.

## Contents

- [architecture.md](architecture.md) — intake: trạng thái tiếp nhận, nguồn, kết quả kiểm tra
- [system-design.md](system-design.md) — bối cảnh, thành phần, module backend, worker/queue, luồng F-01…F-08, idempotency, snapshot/revision, coverage ledger, triển khai
- [decisions.md](decisions.md) — bảng quyết định B-01…B-21, DEC-001, cấu hình MVP, R-01…R-07, các nội dung đã loại hoặc hoãn
- `diagrams/`
  - [component.md](diagrams/component.md) — sơ đồ thành phần
  - [deployment.md](diagrams/deployment.md) — sơ đồ triển khai (môi trường thật và dev local)
  - [data-flow.md](diagrams/data-flow.md) — luồng F-01…F-08 và sequence SD-1…SD-4

Tài liệu liên quan: [API](../04-api/index.md), [Database](../05-database/index.md), [Integrations](../11-integrations/index.md).
