---
id: design-component-flow-nav
title: FlowNav
type: reference
domain: design
module: components
tags: [design, component, flow-nav]
priority: 2
---

# FlowNav

A bar at the top of a page that merges sequential screens into one feature: flow name, back arrow, numbered steps, position ("Bước 2 / 3"), forward arrow.

- Provide: `nav.lx-flow` > `.lx-flow__k`, `a.lx-iconbtn.lx-flow__arrow` (back and forward, each with `data-tip` naming the neighbouring step; `is-off` at the first and last step), `ol.lx-flow__steps` > `li.lx-flow__step` (`is-active` for the current step) and `.lx-flow__pos`.
- Flows: Quy trình phân tích (Snapshot, Analysis Configuration, Execution History), Quy trình review (Review Queues, Review Workspace, Rework Tracking), Quy trình nghiệm thu (Quality Report, Quality Gate, Release History).
- Use it instead of a dropdown when screens always follow each other.
