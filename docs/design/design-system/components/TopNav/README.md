---
id: design-component-top-nav
title: TopNav
type: reference
domain: design
module: components
tags: [design, component, top-nav]
priority: 2
---

# TopNav

The single global bar: logo, the seven Quality Control modules, current user. Graphite (`primary`) background, white text.

- Provide: `header.lx-topnav` > `a.lx-logo` (Label<b>X</b>), `nav.lx-nav` with one `.lx-nav__group` per module, `.lx-userwrap` (user menu).
- Module order is fixed: Overview, Quality Analysis, Review Center, Escalations, Calibration & Audit, Reports & Releases, Configuration. The module containing the current screen has `is-active` (white text + 3px white underline).
- Modules whose screens are sequential or belong together (Quality Analysis, Review Center, Escalations, Reports & Releases) are a single link (`a.lx-navbtn`) with no dropdown; their steps are shown by `FlowNav` or by tabs inside the page. Modules with independent screens (Overview, Calibration & Audit, Configuration) are a `button.lx-navbtn` that opens a `DropdownMenu`.
- The user area opens a user menu (Hồ sơ, Cài đặt, Đăng xuất) with the role label "Super Admin" beside the avatar.
