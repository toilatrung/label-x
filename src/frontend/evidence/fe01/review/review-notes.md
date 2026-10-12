# FE-01 PR #181 repair evidence for read-only review

Issue #147; branch `feat/feat/FE-01-home-quality-summary`; base `develop-fe` at `e5116733292541e7e7fc52b82e91d8d7fab09301`. Final repair handoff for leader QA rerun. Leader QA acceptance remains pending.

## Behavior and scope

- Home preserves real scoped, paginated Dataset API reads, search, row selection, delayed-response protection and user switching. Dataset names/IDs/CVAT project mappings are real; unavailable Task/Job totals, frame totals, latest run, coverage, issues and Gate are labeled canonical illustration. Real Dataset version is not inferred from Guideline/Taxonomy.
- Summary preserves real Dataset selection and CVAT Task/Job identity. Metrics `12,500 / 92.4% / 384 / 126`, six engine rows, review `124 / 50 / 18 / 242`, Task quality columns, candidate categories and Gate are canonical illustration with badges and regional notices. The live Task row's displayed `600` frames and quality fields are illustration, not a measurement of the real 100-frame Task.
- API-unavailable preview renders all four canonical Home rows and all Summary regions, with explicit error/retry UI, `SampleDataBadge` and the notice prefix “Chức năng vẫn chưa được kết nối với server”. Fixture IDs do not authorize backend reads.
- FE-01 has zero inline styles in `page.tsx`, `QualityControlHome.tsx`, `QualitySummary.tsx`; 39 added CSS utility lines are identical in all three mirrors.
- `TopBar.tsx`, `ContextBar.tsx`, `AppShell.tsx` match `origin/develop-fe` exactly. Per [leader directive](https://github.com/toilatrung/label-x/pull/181#issuecomment-6117171982), FE10 PR #183 owns the Overview Quality Summary link. Direct `/?view=summary` and the Home row arrow work.
- Repeated sync retains one warning per Home region. Summary links use `/reports`, `/review`, `/reports/gate`, `/analysis/history`; preview Home links also use `/reports/releases` and `/analysis/snapshots`.
- [Aggregation blocker](../../../../../.agent/reports/implementation/blocker-fe01-missing-aggregation-endpoints.html) distinguishes proposed missing aggregation endpoints from existing `GET /api/runs/{id}/gate/` contract, whose Summary callout wiring is pending.

## Fresh Codex CLI browser evidence

Collector run: **exit 0**, `2026-10-12T03:56:46.937Z`, 23 seconds, production `BUILD_ID=GmKVNBuw8zXZSOEkYyyNB`, app port 3001, official Node 22.23.3. [Portable receipt](evidence-receipt.json) records 46 actions, **1152 request + response events** (not 1152 requests), screenshot SHA-256 values, assertions and Task response/UI proof. Full sanitized collector output is retained locally at `.cache/fe01-codex-capture.log`.

| Phase | Data boundary | Verified at 1440 and 390 |
| --- | --- | --- |
| Live QA Lead | Actual login and backend GETs; no API response mocks | Dataset GET 200; Dataset 2 / CVAT project #2 loaded; BDD search filtered to one matching row then cleared; repeated sync exactly one notice; row `aria-selected=true` stays on Home; arrow changes URL to Summary |
| Live Summary | Actual `/api/datasets/2/tasks/` GET 200 | Response contains Task ID 1; UI shows settled `Task #1` before capture; four canonical metrics, six engines, review/Task/candidate/Gate regions; Report, Gate and History clicked and URL asserted; Review Center link presence asserted |
| API 503 preview | Separate authenticated browser contexts; only Dataset GET paths intercepted with HTTP 503; auth remains real | Four canonical illustrative Home rows; full Summary preview including three illustrative Tasks; badges/notices; explicit failure UI retained |
| Write safety | Writes blocked before server except auth login/logout | Zero unintended writes; the only observed non-GET requests were four `POST /api/auth/login/` requests |
| Mobile layout | 390px viewport | No horizontal document overflow in live and preview Home/Summary; wide tables keep local scroll containers |

The collector's former native `querySelector` with Playwright `:has-text` was corrected in the ignored helper. Task settling is bounded to 30 seconds and a real HTTP 200 response plus Task ID 1 in both response and UI is mandatory. No application source was changed in this evidence finalization.

Network warnings: one expected unauthenticated `GET /api/auth/session/` 403 before login per context; three intentionally intercepted Dataset 503 responses per preview context. No additional HTTP error responses were recorded. No filled login screenshots, traces, HAR, credentials, headers, cookies or response bodies were persisted.

## Visual comparison with retained canonical references

All four references and all eight fresh captures were opened and inspected. References: [Home 1440](ref-home-1440.png), [Home 390](ref-home-390.png), [Summary 1440](ref-summary-1440.png), [Summary 390](ref-summary-390.png). Reference files are unchanged.

| Region | 1440 comparison | 390 comparison | Difference / limit |
| --- | --- | --- | --- |
| Shared shell | Graphite TopBar and context row present | Navigation and context chips wrap within viewport | Actual QA Lead name/role, real selected Dataset, unselected Run/Snapshot and baseline role chip differ from canonical Super Admin fixture; FE10 owns shell changes |
| Home header / search / footer | Same region order, actions, search and Dataset definition footer | Header/actions wrap; footer visible | Live lead wraps less than reference; real two-row list is shorter; preview error/retry adds vertical space |
| Home table | Eight columns in canonical order; preview four rows, versions, badges and row actions retained | Wide table remains locally scrollable | Real two-row names/IDs have no invented version; live column widths differ from fixture; rightmost columns are offscreen at 390 pending table scroll |
| Summary header / Gate / four metrics | Same region order and canonical values; action links present | Gate wraps and four metrics stack | Notices and API failure/retry panel add height; real Dataset and absent real Run differ from canonical lead |
| Six engine rows / review volume | Main/side card structure, status words, values and progress bars match canonical content | Cards stack; engine table scrolls locally | Added regional badges/notices shift vertical placement |
| Task / candidates | Canonical columns and five categories retained; preview three Tasks | Cards stack; Task table scrolls locally | Live Task identity/Job are real and one row replaces three fixtures; frame/quality figures remain labeled illustration; first preview Task selection highlight differs from reference |

This establishes inspected regions and canonical content, **not pixel 1:1 fidelity or final visual QA acceptance**. The 390 screenshots do not prove interaction with every offscreen table column.

## Earlier executor validation (not rerun by Codex)

The approved handoff reports these earlier successful runs. The native `task-547.log` was inspected read-only: lint/typecheck output, backend `603 passed, 1 skipped`, frontend `38 files / 370 tests`, detector `10 passed`, and `FRAMEWORK_VALIDATION_PASS` are present. That full repository run occurred before the final one-line TopBar restoration. Its exit 0 and Postgres environment are reported by the handoff, not independently rerun here.

- Earlier `make check`: exit 0; backend 603 + 1 skip, frontend 370/38, detector 10, framework pass. Backend lint/format clean (216 files), mypy 134 files; frontend typecheck and lint reported exit 0.
- After shell restoration: handoff reports focused FE-01 **22/22, exit 0**, with React `act(...)` stderr warnings, and production build **exit 0**, BUILD_ID above.
- Earlier static design verifier: handoff reports **24 screens / 18 tab states, exit 0**; this is not pixel comparison evidence.
- Earlier `refresh-demo.sh`: overall **exit 1** because unrelated port 3000 was absent; handoff reports FE-01 build and port 3001 app readiness exit 0. No claim that this helper passed.

No broad suite/build rerun was needed because product source was unchanged during finalization. Fresh scope, CSS, merge preservation, privacy and receipt checks are recorded in `.cache/fe01-codex-checks.log` and the executor result.

## Pending acceptance / unverified cases

- Leader QA rerun and final acceptance, new repair commit CI, clean release reproducibility, other roles/no-Dataset account, real pagination beyond the first page, delayed-response/user-switch browser scenarios, Task scope interaction, offscreen table scrolling, preview release/snapshot clicks and Review Center click are **NOT VERIFIED by this fresh collector**. Existing source/tests or previous evidence do not turn them into new browser proofs.
- Real aggregation data and existing Gate contract wiring remain blocked/pending as documented. FE10 Overview menu link remains pending.
- [QA recheck request](QA_RECHECK.md) requests leader QA rerun; it does not claim QA acceptance.
