---
id: design-component-metric-tile
title: MetricTile
type: reference
domain: design
module: components
tags: [design, component, metric-tile]
priority: 2
---

# MetricTile

A bordered tile with one number, its label and a single line of context.

- Provide: `.lx-metric` > `.lx-metric__k` (label), `.lx-metric__v` (value), optional `.lx-progress`, `.lx-metric__n` (note). Lay tiles out with `.lx-grid.lx-grid--4`.
- Colour the value only when it breaches a threshold: `is-warn` (below target) or `is-bad` (blocking). Always state the threshold in the note.
- Four tiles per row at most. Never merge several measures into one score.
