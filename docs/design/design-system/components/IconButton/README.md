---
id: design-component-icon-button
title: IconButton
type: reference
domain: design
module: components
tags: [design, component, icon-button]
priority: 2
---

# IconButton

A borderless 32px icon button for actions inside table rows; a tooltip names the action on hover and keyboard focus.

- Provide: `<a class="lx-iconbtn" href data-tip="Mô tả hành động" aria-label="Mô tả hành động">` (or `<button>`) containing one 16px line SVG (`viewBox="0 0 16 16"`, stroke from `currentColor`).
- `data-tip` and `aria-label` carry the same verb phrase in Vietnamese ("Mở trong Review Workspace"). Never ship an icon button without both.
- Icons: arrow-right = open / continue, pencil = edit, clock = history, plus = create, download = export. One icon per meaning across the product.
- Place in the last column of a `DataTable`, right-aligned. Use `Button` instead for page-level actions and form submits.
