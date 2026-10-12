# FE-01 PR #181 final repair handoff

Issue #147; branch `feat/feat/FE-01-home-quality-summary`; base `develop-fe` at `e358c8be661ed4eb6eb37fdf13626bac4172d0f2`. Final repair handoff for leader QA rerun. Leader QA acceptance remains pending.

## Behavior and scope

- Home preserves real scoped, paginated Dataset API reads, search, row selection, delayed-response protection and user switching. Dataset names/IDs/CVAT project mappings are real; unavailable Task/Job totals, frame totals, latest run, coverage, issues and Gate are labeled canonical illustration. Real Dataset version is not inferred from Guideline/Taxonomy.
- Summary preserves real Dataset selection and CVAT Task/Job identity. Metrics `12,500 / 92.4% / 384 / 126`, six engine rows, review `124 / 50 / 18 / 242`, Task quality columns, candidate categories and Gate are canonical illustration with badges and regional notices. The live Task row's displayed `600` frames and quality fields are illustration, not a measurement of the real 100-frame Task.
- API-unavailable preview renders all four canonical Home rows and all Summary regions, with explicit error/retry UI, `SampleDataBadge` and the notice prefix “Chức năng vẫn chưa được kết nối với server”. Fixture IDs do not authorize backend reads.
- FE-01 has zero inline styles in `page.tsx`, `QualityControlHome.tsx`, `QualitySummary.tsx`; 39 added CSS utility lines are identical in all three mirrors.
- `TopBar.tsx`, `ContextBar.tsx`, `AppShell.tsx` match `origin/develop-fe` exactly. Per [leader directive](https://github.com/toilatrung/label-x/pull/181#issuecomment-6117171982), FE10 PR #183 owns the Overview Quality Summary link. Direct `/?view=summary` and the Home row arrow work.
- Repeated sync retains one warning per Home region. Summary links use `/reports`, `/review`, `/reports/gate`, `/analysis/history`; preview Home links use `/reports/releases` and `/analysis` (Snapshot creation); `/analysis/snapshots` is Snapshot history per latest upstream skill.
- [Aggregation blocker](../../../../../.agent/reports/implementation/blocker-fe01-missing-aggregation-endpoints-@tdt2112.html) distinguishes proposed missing aggregation endpoints from existing `GET /api/runs/{id}/gate/` contract, whose Summary callout wiring is pending.

## Fresh Codex CLI browser evidence

Collector run: **exit 0**, `2026-10-12T04:25:41.623Z`, 23 seconds, production `BUILD_ID=PwTBS3cAI9RPUzGOrXGDm`, app port 3001, official Node 22.23.3. [Portable receipt](evidence-receipt.json) records 48 actions, **1160 request + response events** (not 1160 requests), screenshot SHA-256 values, assertions and Task response/UI proof. Committed network audit is trimmed to 96 `/api/` events, explicitly distinct from the total event count; complete sanitized raw receipt stays in ignored `.cache/fe01-pr181-receipt.e358c8b.json`. Full collector output is `.cache/fe01-latest-base-capture.log`.

| Phase | Data boundary | Verified at 1440 and 390 |
| --- | --- | --- |
| Live QA Lead | Actual login and backend GETs; no API response mocks | Dataset GET 200; Dataset 2 / CVAT project #2 loaded; BDD search filtered to one matching row then cleared; repeated sync exactly one notice; row `aria-selected=true` stays on Home; arrow changes URL to Summary |
| Live Summary | Actual `/api/datasets/2/tasks/` GET 200 | Response contains Task ID 1; UI shows settled `Task #1` before capture; four canonical metrics, six engines, review/Task/candidate/Gate regions; Report, Gate and History clicked and URL asserted; Review Center link presence asserted |
| API 503 preview | Separate authenticated browser contexts; only Dataset GET paths intercepted with HTTP 503; auth remains real | Four canonical illustrative Home rows; full Summary preview including three illustrative Tasks; badges/notices; explicit failure UI retained; first Snapshot link clicked and actual URL `/analysis` asserted |
| Write safety | Writes blocked before server except auth login/logout | Zero unintended writes; the only observed non-GET requests were four `POST /api/auth/login/` requests |
| Mobile layout | 390px viewport | No horizontal document overflow in live and preview Home/Summary; wide tables keep local scroll containers |

The collector's former native `querySelector` with Playwright `:has-text` was corrected in the ignored helper. Task settling is bounded to 30 seconds and a real HTTP 200 response plus Task ID 1 in both response and UI is mandatory. Latest-base route correction changes only the existing first Snapshot href to `/analysis`, preserves its plus icon and adds one assertion to the existing Home preview test.

Network warnings: one expected unauthenticated `GET /api/auth/session/` 403 before login per context; four intentionally intercepted Dataset 503 responses per preview context. No additional HTTP error responses were recorded. No filled login screenshots, traces, HAR, credentials, headers, cookies or response bodies were persisted.

## Visual comparison with retained canonical references

The four unchanged canonical references were reused from the previous visual review; all eight latest-build captures were reopened and compared against them. References: [Home 1440](ref-home-1440.png), [Home 390](ref-home-390.png), [Summary 1440](ref-summary-1440.png), [Summary 390](ref-summary-390.png). Reference files are unchanged.

| Region | 1440 comparison | 390 comparison | Difference / limit |
| --- | --- | --- | --- |
| Shared shell | Graphite TopBar and context row present | Navigation and context chips wrap within viewport | Actual QA Lead name/role, real selected Dataset, unselected Run/Snapshot and baseline role chip differ from canonical Super Admin fixture; FE10 owns shell changes |
| Home header / search / footer | Same region order, actions, search and Dataset definition footer | Header/actions wrap; footer visible | Live lead wraps less than reference; real two-row list is shorter; preview error/retry adds vertical space |
| Home table | Eight columns in canonical order; preview four rows, versions, badges and row actions retained | Wide table remains locally scrollable | Real two-row names/IDs have no invented version; live column widths differ from fixture; rightmost columns are offscreen at 390 pending table scroll |
| Summary header / Gate / four metrics | Same region order and canonical values; action links present | Gate wraps and four metrics stack | Notices and API failure/retry panel add height; real Dataset and absent real Run differ from canonical lead |
| Six engine rows / review volume | Main/side card structure, status words, values and progress bars match canonical content | Cards stack; engine table scrolls locally | Added regional badges/notices shift vertical placement |
| Task / candidates | Canonical columns and five categories retained; preview three Tasks | Cards stack; Task table scrolls locally | Live Task identity/Job are real and one row replaces three fixtures; frame/quality figures remain labeled illustration; first preview Task selection highlight differs from reference |

This establishes inspected regions and canonical content, **not pixel 1:1 fidelity or final visual QA acceptance**. The 390 screenshots do not prove interaction with every offscreen table column.

## Latest-base integration and actual checks

The old e511673 merge and approved repairs were committed as `f2ea0c7`, then latest `origin/develop-fe` was merged as `9045c5e`. Three CSS conflicts were resolved by retaining the complete latest-base content plus the 39 FE-01 utility lines, identical in all mirrors. Already merged upstream Snapshot, escalation, calibration and report work is preserved. Upstream skill route-map changes are not a new FE-01 change.

- **New full `make check`: exit 0**, official Node 22.23.3, existing PostgreSQL connection verified (`DB_VENDOR=postgresql`, `DB_CONNECTION=OK`). Backend **603 passed, 1 skipped**; frontend **378 passed / 39 files**; detector **10 passed**; `FRAMEWORK_VALIDATION_PASS`. Ruff/format, mypy 134 files, ESLint and TypeScript completed successfully. The existing Home preview test includes the new `/analysis` href assertion.
- Full log: `.cache/fe01-latest-base-make-check.log`. Eight `TimeoutOverflowWarning` entries and the uv no-sync/no-project warning are retained; no clean-stderr claim. Earlier 22/22 focused run with act warnings is historical evidence, superseded here by the new full suite.
- **New production build: exit 0**, BUILD_ID `PwTBS3cAI9RPUzGOrXGDm`; complete build log `.cache/fe01-latest-base-build.log`. Owned FE01 listener restarted as PID chain `1918153 -> 1918184 -> 1918185`; app HTTP **200**, backend proxy CSRF **204**.
- Reviewed `refresh-demo.sh` overall **exit 1** after successful build/readiness/ownership because foreign port 3000 is absent. `.cache/fe01-latest-base-refresh.log` preserves that result. No foreign service restart or overall helper-pass claim.
- **New static design verifier: exit 0**, 24 screens / 18 tab states (`.cache/fe01-latest-base-design-verify.log`); static verification is not pixel proof.
- Fresh whitespace, CSS identity, shared-shell zero diff, upstream preservation, privacy, receipt/screenshot hashes and exact commit-scope checks: `.cache/fe01-latest-base-final-checks.log`.

## Pending acceptance / unverified cases

- Leader QA rerun and final acceptance, new repair commit CI, clean release reproducibility, other roles/no-Dataset account, real pagination beyond the first page, delayed-response/user-switch browser scenarios, Task scope interaction, offscreen table scrolling, preview release click and Review Center click are **NOT VERIFIED by this fresh collector**. Existing source/tests or previous evidence do not turn them into new browser proofs.
- Real aggregation data and existing Gate contract wiring remain blocked/pending as documented. FE10 Overview menu link remains pending.
- [QA recheck request](QA_RECHECK.md) requests leader QA rerun; it does not claim QA acceptance.

## CI ownership metadata repair

The framework job failed CR-100 ownership validation for the unsuffixed blocker report. The report now uses `blocker-fe01-missing-aggregation-endpoints-@tdt2112.html` and metadata ID `blocker-fe01-missing-aggregation-endpoints-tdt2112`; its substantive findings and status are unchanged. The three public references are updated. Product source, all eight captures and the receipt are unchanged. Ownership validation uses actor `tdt2112` against current `origin/develop-fe` (`78c6146e11f43381f63d31cc7e90033793c012d8`); the existing integrated ancestor `e358c8b` is preserved. New-head CI and leader QA remain pending.
