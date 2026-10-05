---
id: design-index
title: LabelX Design
type: reference
domain: design
module: index
tags: [design, design-system, screens]
priority: 2
---
# LabelX Design

## Purpose

Nguồn thiết kế chuẩn của LabelX (nguồn **H** trong tài liệu): Design System và 25 màn hình Quality Control. Skill thiết kế cho agent nằm ở [.agent/skills/labelx-design/SKILL.md](../../.agent/skills/labelx-design/SKILL.md).

## Nội dung

- [design-system.md](design-system.md) — tài liệu Design System (nguyên tắc, quy tắc nội dung, layout, trạng thái, mọi component).
- [design-system/](design-system/README.md) — `tokens.json`, `design-system.json`, `components/bundle.css` (toàn bộ style `lx-*`) và README + `preview.html` cho từng component.
- [screens/](screens/Main.dc.html) — 25 màn hình dạng `.dc.html`, kèm `canvas.json` (bố cục board), component dùng chung `TopBar.dc.html`, `FlowNav.dc.html` và `ds/labelx/` (bản sao tokens và style mà màn hình link tới).

Màn hình dùng canvas runtime của artifact đã publish (`support.js`), nên mở trong canvas đã publish; file ở đây dùng để sửa và bàn giao. Frontend chép tokens/style vào `src/frontend/src/styles/tokens.css` và `labelx.css`.
