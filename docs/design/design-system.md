---
id: design-system
title: LabelX Design System
type: reference
domain: design
module: design-system
tags: [design, design-system, tokens, components]
priority: 2
---

# LabelX Design System
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


# Components

# Button

Buttons trigger actions; `primary` is graphite and used once per view region.

- Provide: a `<button>` (or `<a>`) with class `lx-btn` plus one modifier: `lx-btn--primary`, `lx-btn--ghost`, `lx-btn--sm`.
- One primary per page header or per table row action column. Secondary actions use the default outlined button.
- Label is a verb, sentence case, Vietnamese: "Mở Dataset", "Tạo snapshot". A trailing `→` only when it navigates.
- Do not colour buttons by meaning (no red "Reject" button fill); destructive confirmation lives in a dialog.


# ContextChip

A key–value pill in the context bar that shows and switches the QC context; the bar always holds six chips in this order: Dataset → Quality Control Run → Snapshot → Phạm vi → Guideline → Taxonomy.

- Provide: `.lx-chip` with `.lx-chip__k` (muted key) and `.lx-chip__v` (value); a chevron SVG when it opens a switcher (Dataset, Quality Control Run, Phạm vi). Read-only facts (Snapshot, Guideline, Taxonomy) use `lx-chip--static`, no chevron.
- IDs inside the value use `lx-mono`.

## States

1. **Dataset read-only** — a released version: add `<span class="lx-tag lx-tag--ro">read-only</span>` after the value; write actions are hidden across the module.
2. **Quality Control Run status** — an 8px `.lx-dot` after the run ID: Checked `#1f8f5a`, Partial `#b7791f`, Running `#2f6fbf`, Failed `#c0362c` (each ≥3:1 on `surface`). The dot is the one exception to "state is always a word": give it `title` and `aria-label` with the status name, and show the word in the run menu.
3. **Snapshot locked** — snapshots are immutable: static chip with the ID, `rev <hash>` in `ink-muted` mono, and a lock icon.


# DataTable

The default way to list records (datasets, runs, issues, jobs).

- Provide: `.lx-card` > optional `.lx-toolbar` > `table.lx-table` > optional `.lx-table__foot`.
- Two-line cells: `.lx-cell__main` + `.lx-cell__sub` (caption). Numbers right-aligned with class `r` (tabular figures).
- Selected row: `aria-selected="true"`. No zebra stripes, no vertical rules, no per-column background colours.
- Row actions sit in the last column, right-aligned.


# DropdownMenu

The floating card that opens under a top-level tab with independent screens, under the user area, or under a context chip.

- Provide: `.lx-nav__group` (position: relative) holding `button.lx-navbtn[aria-haspopup=menu][aria-expanded]` and, when open, `.lx-menu[role=menu]` with `a.lx-menu__item[role=menuitem]` children.
- Look: white card, 6px radius, soft shadow, a small pointer toward the tab. Items are 15px, hairline separators, label on the left (`.lx-menu__t`) and a 16px line icon on the right (`.lx-menu__ico`). The description (`.lx-menu__d`) appears only as a tooltip on hover or focus.
- The current screen has `is-active` (light fill, darker text and icon). Close on selecting an item or clicking outside (`.lx-backdrop`).
- User menu: `.lx-menu--user`, attached flush under the user button, items with the icon on the left (`.lx-menu__ico--l`): Hồ sơ, Cài đặt, Đăng xuất.
- Text colour inside menus is `ink-muted` / `ink`, never inherited from the white tab text of the dark bar.
- Keep to 2–4 items; use `lx-menu--end` when the menu opens at the right edge so tooltips open to the left.


# FlowNav

A bar at the top of a page that merges sequential screens into one feature: flow name, back arrow, numbered steps, position ("Bước 2 / 3"), forward arrow.

- Provide: `nav.lx-flow` > `.lx-flow__k`, `a.lx-iconbtn.lx-flow__arrow` (back and forward, each with `data-tip` naming the neighbouring step; `is-off` at the first and last step), `ol.lx-flow__steps` > `li.lx-flow__step` (`is-active` for the current step) and `.lx-flow__pos`.
- Flows: Quy trình phân tích (Snapshot, Analysis Configuration, Execution History), Quy trình review (Review Queues, Review Workspace, Rework Tracking), Quy trình nghiệm thu (Quality Report, Quality Gate, Release History).
- Use it instead of a dropdown when screens always follow each other.


# IconButton

A borderless 32px icon button for actions inside table rows; a tooltip names the action on hover and keyboard focus.

- Provide: `<a class="lx-iconbtn" href data-tip="Mô tả hành động" aria-label="Mô tả hành động">` (or `<button>`) containing one 16px line SVG (`viewBox="0 0 16 16"`, stroke from `currentColor`).
- `data-tip` and `aria-label` carry the same verb phrase in Vietnamese ("Mở trong Review Workspace"). Never ship an icon button without both.
- Icons: arrow-right = open / continue, pencil = edit, clock = history, plus = create, download = export. One icon per meaning across the product.
- Place in the last column of a `DataTable`, right-aligned. Use `Button` instead for page-level actions and form submits.


# MetricTile

A bordered tile with one number, its label and a single line of context.

- Provide: `.lx-metric` > `.lx-metric__k` (label), `.lx-metric__v` (value), optional `.lx-progress`, `.lx-metric__n` (note). Lay tiles out with `.lx-grid.lx-grid--4`.
- Colour the value only when it breaches a threshold: `is-warn` (below target) or `is-bad` (blocking). Always state the threshold in the note.
- Four tiles per row at most. Never merge several measures into one score.


# SearchField

A full-width text filter above a table.

- Provide: `.lx-search` wrapping a magnifier SVG and an `<input>` with a placeholder naming what is searchable.
- Sits in a table's `.lx-toolbar`, followed by a result count in `caption` style ("4/4 dataset").


# StatusBadge

A small uppercase label for a machine state (gate, run, engine, issue).

- Provide: `<span class="lx-badge lx-badge--{success|warning|danger|info}">WORD</span>`; no modifier = neutral.
- Always a word, never a dot or colour alone. Mapping: RELEASED/CHECKED/OK → success; PARTIAL/READY · chờ approve → warning; BLOCKED/FAILED → danger; RUNNING/IN REVIEW → info; NOT CHECKED/— → neutral.
- `lx-tag` is the non-status version tag (v1.4, read-only).


# Tabs

Underline tabs that switch views of the same list inside one screen (queues, report sections).

- Provide: `.lx-tabs[role=tablist]` with `button.lx-tab[role=tab]`; the selected one gets `is-active` and `aria-selected="true"`. Optional `.lx-count` shows a number.
- Use for 2–4 views of the same data. Different screens belong in the top navigation dropdown, not in tabs.
- Place at the top of a `.lx-card`, above the toolbar and table.


# TopNav

The single global bar: logo, the seven Quality Control modules, current user. Graphite (`primary`) background, white text.

- Provide: `header.lx-topnav` > `a.lx-logo` (Label<b>X</b>), `nav.lx-nav` with one `.lx-nav__group` per module, `.lx-userwrap` (user menu).
- Module order is fixed: Overview, Quality Analysis, Review Center, Escalations, Calibration & Audit, Reports & Releases, Configuration. The module containing the current screen has `is-active` (white text + 3px white underline).
- Modules whose screens are sequential or belong together (Quality Analysis, Review Center, Escalations, Reports & Releases) are a single link (`a.lx-navbtn`) with no dropdown; their steps are shown by `FlowNav` or by tabs inside the page. Modules with independent screens (Overview, Calibration & Audit, Configuration) are a `button.lx-navbtn` that opens a `DropdownMenu`.
- The user area opens a user menu (Hồ sơ, Cài đặt, Đăng xuất) with the role label "Super Admin" beside the avatar.


# Tokens

See `design-system/tokens.json` (colour, type, spacing, radius, shadow, size) and `design-system/components/bundle.css` (all `lx-*` classes).
