---
id: design-system-readme
title: LabelX Design System — tổng quan
type: reference
domain: design
module: design-system
tags: [design, design-system]
priority: 2
---

LabelX is the Quality Control module that runs around CVAT. Users are Quality Control Leads, Reviewers, Quality Assurance staff and Annotators working long sessions on dense data, so the interface is quiet, neutral and table-first: structure comes from borders and spacing, colour is reserved for meaning.

## Principles

- **Neutral first.** Surfaces are `surface` on `canvas`; text is `ink`, `ink-muted`, `ink-subtle`. The only action colour is graphite `primary`.
- **Red belongs to the logo and to blocking states.** `brand` is used for the X in the wordmark and nowhere else. `danger` is for BLOCKED / FAILED / critical only.
- **State is always a word.** Every status uses a `StatusBadge` with text; never a coloured dot or tinted row alone (the one exception is the Quality Control Run dot in `ContextChip`, which carries a tooltip and label).
- **Context is always visible.** Every screen shows the context bar (Dataset · Quality Control Run · Snapshot · Phạm vi · Guideline · Taxonomy) under the top nav.
- **Sub-features live in dropdowns.** Only tabs with independent screens (Overview, Calibration & Audit, Configuration) open a dropdown menu listing its screens as a floating white card (soft shadow, small pointer toward the tab): label on the left, line icon on the right, hairline separators; descriptions appear only as a tooltip on hover; the active screen is highlighted. Do not add a second navigation row.
- **Sequential screens are one feature, without a dropdown.** Tabs whose screens always follow each other (Quality Analysis, Review Center, Reports & Releases) are a single nav button. Inside, a flow bar (`lx-flow`) shows the steps with back and forward arrow buttons, each with a tooltip naming the neighbouring step. A history or log that is not a step (Snapshot history) opens from a button on the page. Related lists that belong together (Escalations) are tabs inside one page.
- **Row actions are icon buttons.** Actions inside table rows use `IconButton` (no box, tooltip on hover and focus, `aria-label` always set). Boxed `Button`s are for page-level actions and forms.
- **Square by default.** Cards, tables, panels, buttons, inputs and the workspace have square corners. Only small elements are rounded: badges and tags (`radius-sm`), context chips (pill), switches, avatar, status dots, and floating dropdown cards (6px).
- **Borders, not shadows.** Cards and tables use a 1px `border`; `shadow-menu` only for dropdowns.

## Content

- UI language is Vietnamese; domain terms stay in English as the team uses them: Dataset, Quality Control Run, Snapshot, Coverage, Gate, Issue, Rework, Release.
- Sentence case for titles and buttons ("Mở Dataset", "Tạo snapshot"); UPPERCASE only in table headers and badges (`label` style).
- IDs are written exactly and set in `code`: `#QC-091`, `SNP-014`, `rev a91f3c`.
- Numbers use thousands separators and tabular figures (`12,500`, `92.4%`). Empty values are an em dash `—`.
- Write names in full: "Quality Control", "Quality Assurance", "Intersection over Union", "Ground Truth". No abbreviations, except product and file-format names (CVAT, PDF, CSV, JSON) and identifiers such as `#QC-091`.
- No emoji, no exclamation marks, no marketing tone. Descriptions are one or two plain sentences in `ink-muted`.

## Layout

- App frame: `TopNav` (`topnav-height`, graphite `primary` bar with white text; the open tab lightens slightly while its dropdown card floats below) → context bar (`contextbar-height`, on `canvas`) → content on `canvas` with a `space-6` gutter.
- Content max width 1440px. Page header: `page-title` + one `body` description in `ink-muted`, primary action at the right.
- Lists are `DataTable` inside a `.lx-card`, with a toolbar holding `SearchField` and a count.
- Spacing steps: `space-1` 4, `space-2` 8, `space-3` 12, `space-4` 16, `space-6` 24, `space-8` 32. Nothing in between.
- Radii: `radius-md` and `radius-lg` are 0 (square); `radius-sm` 4px for badges and tags; `radius-full` for context chips and round controls only.

## Type

- Inter (Google Fonts) for everything; JetBrains Mono for IDs only.
- `page-title` 22/28 · `section-title` 15/22 · `body` 14/20 · `table` 13/20 · `caption` 12/16 · `label` 11/16 uppercase.
- Weight 600 for emphasis; never 700+ outside the logo.

## Colour and states

| State | Badge | Example |
| --- | --- | --- |
| Pass / done | `success` on `success-soft` | CHECKED, RELEASED, OK |
| Partial / needs attention | `warning` on `warning-soft` | PARTIAL, READY · chờ approve |
| Blocking | `danger` on `danger-soft` | BLOCKED, FAILED |
| In progress | `info` on `info-soft` | RUNNING, IN REVIEW |
| Inert | `neutral` on `neutral-soft` | NOT CHECKED, — |

Every text colour above holds ≥4.5:1 on its soft ground. Focus ring: 2px solid `focus` with 2px offset on every interactive element.

## Iconography

Line icons, 16px, 1.5px stroke, `currentColor` (Lucide style). Icons support a label, never replace it — except the search magnifier and dropdown chevron. No icons in the top nav tabs; dropdown items carry a right-aligned icon and the user menu a left-aligned icon.

## Logo

No logo file was provided: the wordmark is set in type — "Label" in white on the graphite bar (`ink` on light surfaces), "X" in `brand`, Inter 600/800, 20px.
