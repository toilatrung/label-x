---
id: design-component-data-table
title: DataTable
type: reference
domain: design
module: components
tags: [design, component, data-table]
priority: 2
---

# DataTable

The default way to list records (datasets, runs, issues, jobs).

- Provide: `.lx-card` > optional `.lx-toolbar` > `table.lx-table` > optional `.lx-table__foot`.
- Two-line cells: `.lx-cell__main` + `.lx-cell__sub` (caption). Numbers right-aligned with class `r` (tabular figures).
- Selected row: `aria-selected="true"`. No zebra stripes, no vertical rules, no per-column background colours.
- Row actions sit in the last column, right-aligned.
