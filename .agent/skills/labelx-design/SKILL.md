---
name: labelx-design
description: Design and build screens, components and copy for LabelX, the Quality Control module around CVAT. Use for any new or changed LabelX screen, mockup, Design System component or UI text so it stays neutral, table-first and consistent.
---

# LabelX design skill

LabelX is an enterprise Quality Control module that runs around CVAT. Users are Quality Control Leads, Reviewers, Quality Assurance staff and Annotators working long sessions on dense data. The interface is quiet, neutral and table-first. It must not look "AI-generated": no gradients, no glow, no decorative illustration, no emoji.

## Sources of truth

- Design System document: `docs/design/design-system.md` (principles, content rules, layout, states, every component).
- Design System "LabelX" in `docs/design/design-system/` (tokens in `tokens.json`, classes `lx-*` in `components/bundle.css`, one README per component). The frontend copy lives in `src/frontend/src/styles/tokens.css` and `labelx.css`.
- Design canvas "LabelX Quality Control Screens" in `docs/design/screens/` (one `.dc.html` per screen, shared `TopBar` and `FlowNav` components, `canvas.json` for the board layout).
- Always reuse tokens and `lx-*` classes. Never hard-code a colour, radius or spacing that a token already covers.

## Principles

1. Neutral first. Surface on canvas; text `ink`, `ink-muted`, `ink-subtle`. The only action colour is graphite `primary` (#1f2933).
2. Red is for the logo X (`brand`) and blocking states (`danger`) only.
3. State is always a word: use `StatusBadge` with text. The one exception is the Quality Control Run dot, which carries a tooltip and aria-label.
4. Context is always visible: every screen sits under the context bar (Dataset, Quality Control Run, Snapshot, Phạm vi, Guideline, Taxonomy). Dataset, Run and Phạm vi open selection menus and update the other chips.
5. Square by default: cards, tables, panels, buttons, inputs are square. Only small elements are rounded: badges and tags (4px), context chips (pill), switches, avatar, status dots, floating dropdown cards (6px).
6. Borders, not shadows: 1px `border`; shadow only on dropdown cards.
7. Row actions are borderless icon buttons (`lx-iconbtn`) with `data-tip` and `aria-label` carrying the same Vietnamese verb phrase. Page-level actions use boxed `lx-btn`; one primary per region.
8. Rebalance content: each screen is neither crowded nor empty. Related lists become tabs inside one page; a history or log opens from a button on its own page.

## Navigation model

Top bar: graphite background, white text, logo "Label" white and X red, 7 modules, user menu at the right (role label "Super Admin").

| Module | Behaviour |
| --- | --- |
| Overview | Dropdown: Quality Control Home, Quality Summary |
| Quality Analysis | Direct link. Flow of 3 steps: Snapshot, Analysis Configuration, Execution History. Snapshot history is a separate page opened by a button |
| Review Center | Direct link. Flow of 3 steps: Review Queues, Review Workspace, Rework Tracking |
| Escalations | Direct link. One page with tabs: Guideline Gaps, Decision Cases, Adjudication (gaps and cases first) |
| Calibration & Audit | Dropdown: Performance Evaluation, Ground Truth Benchmark, Audit Sampling, Calibration |
| Reports & Releases | Direct link. Flow of 3 steps: Quality Report, Quality Gate, Release History |
| Configuration | Dropdown: Rules & Thresholds, Models & Guidelines, Workflow & Permissions |

Rules:
- Screens that always follow each other are merged into one feature with `FlowNav` (back and forward arrow buttons with tooltips naming the neighbouring step). Do not list them as separate dropdown items.
- Only independent screens live in a dropdown. A dropdown is a white floating card with a small pointer, label left, 16px line icon right, hairline separators, 15px text; the active item has a light fill; descriptions only as hover tooltips. Text colour inside menus is `ink-muted`/`ink`, never the white text of the dark bar.
- User menu: attached under the user button, icon on the left, items Hồ sơ, Cài đặt, Đăng xuất.
- Do not add a second navigation row.

## Layout and type

- App frame: top bar (56px) then context bar (44px) then content on canvas with 24px gutter; content max width 1440.
- Page header: `lx-h1` 22/28 plus one `lx-lead` sentence or two; primary action at the right.
- Lists: `lx-card` containing optional tabs and toolbar, then `lx-table`. Numbers right-aligned in tabular figures; two-line cells with `lx-cell__main` and `lx-cell__sub`.
- Spacing steps 4, 8, 12, 16, 24, 32 only.
- Inter for text, JetBrains Mono for identifiers only. Weight 600 for emphasis, never above 700 except the logo.
- Icons: 16px, 1.5px stroke, `currentColor`, one icon per meaning (arrow = open, pencil = edit, clock = history, plus = create, download = export).

## Content rules

- UI language is Vietnamese; domain terms stay in English: Dataset, Quality Control Run, Snapshot, Coverage, Gate, Issue, Rework, Release.
- Write names in full. Never "QC", "IoU", "GT": write Quality Control, Intersection over Union, Ground Truth. Allowed: product and format names (CVAT, PDF, CSV, JSON) and identifiers (`#QC-091`, `SNP-014`, `rev a91f3c`).
- Sentence case for titles and buttons; UPPERCASE only in table headers and badges.
- Numbers with thousands separators (12,500), empty value is an em dash. No exclamation marks, no marketing tone.
- Keep data consistent across screens: 12,500 frames; coverage 92.4% (threshold 95%); 384 candidates; 126 confirmed errors; 86 rework requests (74 closed = 86.0%, 12 open); random audit 4/100 = 4.0%; reviewer agreement 94.1%.
- Domain rules to respect: Dataset = CVAT project + version; a Quality Control Run is bound to an immutable Snapshot; decisions are Xác nhận lỗi, Bác bỏ, Chưa chắc chắn, Yêu cầu sửa, Chuyển cấp trên; assistant models only provide evidence, the reviewer decides; engines that did not run are "Not checked", never "passed"; random audit estimates quality, risk sampling only finds errors.

## States

Pass or done = success; partial or needs attention = warning; blocking = danger; in progress = info; inert = neutral. Every text colour holds at least 4.5:1 on its soft ground. Focus ring 2px `focus` with 2px offset on every interactive element.

## Working checklist for a new screen

1. Pick the module and decide: independent screen (dropdown item) or a step (add to a flow) or a tab inside an existing page.
2. Build with `TopBar` (active, active-item) and, if a step, `FlowNav` (flow, step).
3. Use only DS tokens and `lx-*` classes; add a new class to the Design System first if one is missing.
4. Check: square corners, state as words, row actions as icon buttons with tooltips, no abbreviations, numbers consistent with the data above, all states of the context bar still correct.
5. Reply to review comments in the thread and resolve them when done.
