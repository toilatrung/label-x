---
id: design-component-dropdown-menu
title: DropdownMenu
type: reference
domain: design
module: components
tags: [design, component, dropdown-menu]
priority: 2
---

# DropdownMenu

The floating card that opens under a top-level tab with independent screens, under the user area, or under a context chip.

- Provide: `.lx-nav__group` (position: relative) holding `button.lx-navbtn[aria-haspopup=menu][aria-expanded]` and, when open, `.lx-menu[role=menu]` with `a.lx-menu__item[role=menuitem]` children.
- Look: white card, 6px radius, soft shadow, a small pointer toward the tab. Items are 15px, hairline separators, label on the left (`.lx-menu__t`) and a 16px line icon on the right (`.lx-menu__ico`). The description (`.lx-menu__d`) appears only as a tooltip on hover or focus.
- The current screen has `is-active` (light fill, darker text and icon). Close on selecting an item or clicking outside (`.lx-backdrop`).
- User menu: `.lx-menu--user`, attached flush under the user button, items with the icon on the left (`.lx-menu__ico--l`): Hồ sơ, Cài đặt, Đăng xuất.
- Text colour inside menus is `ink-muted` / `ink`, never inherited from the white tab text of the dark bar.
- Keep to 2–4 items; use `lx-menu--end` when the menu opens at the right edge so tooltips open to the left.
