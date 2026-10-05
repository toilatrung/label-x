---
id: design-component-status-badge
title: StatusBadge
type: reference
domain: design
module: components
tags: [design, component, status-badge]
priority: 2
---

# StatusBadge

A small uppercase label for a machine state (gate, run, engine, issue).

- Provide: `<span class="lx-badge lx-badge--{success|warning|danger|info}">WORD</span>`; no modifier = neutral.
- Always a word, never a dot or colour alone. Mapping: RELEASED/CHECKED/OK → success; PARTIAL/READY · chờ approve → warning; BLOCKED/FAILED → danger; RUNNING/IN REVIEW → info; NOT CHECKED/— → neutral.
- `lx-tag` is the non-status version tag (v1.4, read-only).
