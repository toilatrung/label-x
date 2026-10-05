---
id: design-component-context-chip
title: ContextChip
type: reference
domain: design
module: components
tags: [design, component, context-chip]
priority: 2
---

# ContextChip

A key–value pill in the context bar that shows and switches the QC context; the bar always holds six chips in this order: Dataset → Quality Control Run → Snapshot → Phạm vi → Guideline → Taxonomy.

- Provide: `.lx-chip` with `.lx-chip__k` (muted key) and `.lx-chip__v` (value); a chevron SVG when it opens a switcher (Dataset, Quality Control Run, Phạm vi). Read-only facts (Snapshot, Guideline, Taxonomy) use `lx-chip--static`, no chevron.
- IDs inside the value use `lx-mono`.

## States

1. **Dataset read-only** — a released version: add `<span class="lx-tag lx-tag--ro">read-only</span>` after the value; write actions are hidden across the module.
2. **Quality Control Run status** — an 8px `.lx-dot` after the run ID: Checked `#1f8f5a`, Partial `#b7791f`, Running `#2f6fbf`, Failed `#c0362c` (each ≥3:1 on `surface`). The dot is the one exception to "state is always a word": give it `title` and `aria-label` with the status name, and show the word in the run menu.
3. **Snapshot locked** — snapshots are immutable: static chip with the ID, `rev <hash>` in `ink-muted` mono, and a lock icon.
