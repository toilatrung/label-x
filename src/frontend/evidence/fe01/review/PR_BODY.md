## FE-01 Home and Quality Summary repairs

Relates to #147; PR #181, base `develop-fe`, branch `feat/feat/FE-01-home-quality-summary`. The repairs restore canonical, explicitly labeled illustration where quality aggregation APIs are absent while preserving scoped Dataset and Task reads. Shared shell files match `origin/develop-fe` (`e358c8b`) exactly; FE10 PR #183 owns the Overview Quality Summary menu link.

Final repair handoff for leader QA rerun. **Leader QA acceptance remains pending.**

| Finding | Repair |
| --- | --- |
| M1 | Complete Home preview and Summary regions: 12,500 frames, 92.4%/95%, 384 candidates, 126 confirmed, six engines, review 124/50/18/242, Task/candidate/Gate. Badges and notices distinguish illustration from real identity. Real Dataset names/IDs/CVAT projects and Task/Job identity remain scoped. |
| M2 | Zero inline styles in the three FE-01 UI files; 39 CSS utility additions identical in three mirrors. |
| M3 | Zero diff from base in TopBar, ContextBar and AppShell. Direct Summary URL and Home arrow work; Overview menu wiring requested from FE10. |
| F1 | Repeated sync retains one regional notice and issues no fake mutation. |
| F2 | Genuine route links to Reports, Review, Gate and History; preview release link retained; first Snapshot link corrected to `/analysis` per latest-base route map. |
| F3 | TODOs and `.agent/reports/implementation/blocker-fe01-missing-aggregation-endpoints-@tdt2112.html` identify missing aggregations separately from existing `/api/runs/{id}/gate/` contract pending Summary wiring. |
| F4 / F5 | Full “Quality Control Run”; no invented Dataset version from Guideline/Taxonomy. |
| F7 / F8 | Overview remains baseline per leader directive; clean local integration of develop-fe is preserved. Latest base `e358c8b` integrated; literal branch name unchanged. |

### Fresh browser evidence

Codex CLI collector **exit 0** at `2026-10-12T04:25:41.623Z`, 23 seconds, official Node 22.23.3, production `BUILD_ID=PwTBS3cAI9RPUzGOrXGDm`, port 3001. Receipt: `src/frontend/evidence/fe01/review/evidence-receipt.json`; **48 actions, 1160 request + response events, zero unintended writes**. The only writes observed were four auth login POSTs. Committed networkEvents contain only 96 relevant `/api/` events; the total count includes static asset request/response events.

- At 1440 and 390: real Dataset GET 200, authentic BDD Dataset 2 / CVAT project #2, one-row BDD search then clear, repeated-sync single notice, Home selection remains Home, arrow navigates to `/?view=summary`.
- Summary captures now wait for settled **Task #1**, confirmed in actual `/api/datasets/2/tasks/` HTTP 200 response and UI at both widths. Task/Job identity is real; displayed frame/quality fields remain labeled illustration.
- Report, Gate and History links were clicked with actual URL changes asserted at both widths. Review Center link presence was verified; its click was not tested.
- Four live PNGs and four separately named API503 preview PNGs are in `src/frontend/evidence/fe01/review/`. Preview uses isolated authenticated contexts with Dataset GET responses intercepted to 503; this is simulated failure evidence, not live aggregation data.
- First Snapshot link was clicked in isolated API503 preview at both widths; actual URL changed to `/analysis`. `/analysis/snapshots` remains Snapshot history. The plus icon is preserved and the Home preview test asserts the corrected href.
- No horizontal document overflow at 390. Filled login forms, traces, HAR, secrets, cookies, headers and response bodies were not persisted. The obsolete bespoke-shell menu proofs were removed; four canonical references are unchanged.

### Regions compared with canonical references

All references and fresh PNGs were inspected against `Main.dc.html` and `Dashboard.dc.html` at 1440/390. Full region table and limitations: `src/frontend/evidence/fe01/review/review-notes.md`.

| Region | Comparison | Known difference |
| --- | --- | --- |
| Shell | Graphite navigation, context row, responsive wrapping retained | Base shell and actual QA Lead context differ from canonical Super Admin fixture; FE10 owns shell. |
| Home | Header, sync, search, eight-column order, footer; full four-row preview | Real two-row list/IDs and no invented versions; notices and preview failure/retry add height; live lead/columns wrap differently. |
| Summary header/Gate/metrics | Same order and canonical values, mobile stacking | Real selected Dataset/absent Run, labels and error panel change text and height. |
| Engines/review | Six engine rows, statuses and review values/bars retained | Regional badges/notices shift vertical positions; mobile engine table scrolls locally. |
| Task/candidates | Canonical columns and five categories; three preview Tasks | Live settled Task #1 replaces three fixtures; quality columns remain illustration; wide mobile tables have offscreen columns. |

**No pixel 1:1 claim.** Reference comparison documents retained content and visible differences; final visual QA is pending.

### Latest-base checks and remaining limits

Latest `origin/develop-fe` `e358c8be661ed4eb6eb37fdf13626bac4172d0f2` is integrated locally. CSS conflicts keep all upstream additions plus 39 FE-01 utility lines identically in three mirrors. Upstream Snapshot, escalation, calibration and report changes are preserved; none appears as a FE-01 feature diff against the latest base. TopBar/ContextBar/AppShell have zero diff.

**New `make check`: exit 0** on existing PostgreSQL, official Node 22.23.3: backend 603 passed +1 skipped, frontend **378/39 files**, detector 10, framework pass; lint/typecheck passed. Log retains 8 timer-overflow warnings and a uv no-sync/no-project warning. The new Snapshot href assertion is included in the full suite.

**New production build: exit 0**, BUILD_ID `PwTBS3cAI9RPUzGOrXGDm`, app HTTP 200 / proxy CSRF 204 on owned port 3001. Reviewed refresh helper **overall exit 1** because foreign port 3000 is absent after successful build/readiness; no foreign service restarted. New design verifier **24 screens / 18 states, exit 0**; static verification only. Full logs remain locally in `.cache/fe01-latest-base-{make-check,build,refresh,design-verify,capture}.log`.

Fresh scope/CSS/shell/privacy/receipt checks accompany the repair. Leader QA, new-head CI, clean release reproducibility, other roles/no-Dataset browser flow, delayed responses/user switching, pagination beyond page one, Task scope interactions, offscreen table scrolling, preview release click and Review Center click are NOT VERIFIED by this collector. Backend aggregation and Gate callout wiring remain pending; FE10 Overview link remains pending. Please rerun QA; this PR does not close #147.

CI ownership repair (CR-100): the blocker report now uses the `-@tdt2112.html` filename and per-user metadata ID. Only report ownership metadata and public references changed; product source, eight captures and the receipt are unchanged. New-head CI is pending; leader QA and release acceptance remain pending.

<!-- issue-migration-2026-10-17:start -->

Historical issue references were archived on 2026-10-17; original text above is preserved.

| Old issue | Current follow-up / archive |
|---|---|
| #147 | [Mapping and scope](../../../../../docs/08-devops/github-issue-migration-2026-10-17.html#issue-147) |
<!-- issue-migration-2026-10-17:end -->
