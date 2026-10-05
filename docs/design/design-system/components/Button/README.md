---
id: design-component-button
title: Button
type: reference
domain: design
module: components
tags: [design, component, button]
priority: 2
---

# Button

Buttons trigger actions; `primary` is graphite and used once per view region.

- Provide: a `<button>` (or `<a>`) with class `lx-btn` plus one modifier: `lx-btn--primary`, `lx-btn--ghost`, `lx-btn--sm`.
- One primary per page header or per table row action column. Secondary actions use the default outlined button.
- Label is a verb, sentence case, Vietnamese: "Mở Dataset", "Tạo snapshot". A trailing `→` only when it navigates.
- Do not colour buttons by meaning (no red "Reject" button fill); destructive confirmation lives in a dialog.
