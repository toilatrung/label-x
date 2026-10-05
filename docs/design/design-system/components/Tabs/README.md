---
id: design-component-tabs
title: Tabs
type: reference
domain: design
module: components
tags: [design, component, tabs]
priority: 2
---

# Tabs

Underline tabs that switch views of the same list inside one screen (queues, report sections).

- Provide: `.lx-tabs[role=tablist]` with `button.lx-tab[role=tab]`; the selected one gets `is-active` and `aria-selected="true"`. Optional `.lx-count` shows a number.
- Use for 2–4 views of the same data. Different screens belong in the top navigation dropdown, not in tabs.
- Place at the top of a `.lx-card`, above the toolbar and table.
