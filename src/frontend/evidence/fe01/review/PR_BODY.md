## FE-01 Home and Quality Summary repairs

Relates to #147; PR #181, base `develop-fe`, branch `feat/feat/FE-01-home-quality-summary`. The repairs restore canonical, explicitly labeled illustration where quality aggregation APIs are absent while preserving scoped Dataset and Task reads. Shared shell files match `origin/develop-fe` (`e511673`) exactly; FE10 PR #183 owns the Overview Quality Summary menu link.

Final repair handoff for leader QA rerun. **Leader QA acceptance remains pending.**

| Finding | Repair |
| --- | --- |
| M1 | Complete Home preview and Summary regions: 12,500 frames, 92.4%/95%, 384 candidates, 126 confirmed, six engines, review 124/50/18/242, Task/candidate/Gate. Badges and notices distinguish illustration from real identity. Real Dataset names/IDs/CVAT projects and Task/Job identity remain scoped. |
| M2 | Zero inline styles in the three FE-01 UI files; 39 CSS utility additions identical in three mirrors. |
| M3 | Zero diff from base in TopBar, ContextBar and AppShell. Direct Summary URL and Home arrow work; Overview menu wiring requested from FE10. |
| F1 | Repeated sync retains one regional notice and issues no fake mutation. |
| F2 | Genuine route links to Reports, Review, Gate and History; preview release/snapshot links retained. |
| F3 | TODOs and `.agent/reports/implementation/blocker-fe01-missing-aggregation-endpoints.html` identify missing aggregations separately from existing `/api/runs/{id}/gate/` contract pending Summary wiring. |
| F4 / F5 | Full “Quality Control Run”; no invented Dataset version from Guideline/Taxonomy. |
| F7 / F8 | Overview remains baseline per leader directive; clean local integration of develop-fe is preserved. Literal branch name unchanged. |

### Fresh browser evidence

Codex CLI collector **exit 0** at `2026-10-12T03:56:46.937Z`, 23 seconds, official Node 22.23.3, production `BUILD_ID=GmKVNBuw8zXZSOEkYyyNB`, port 3001. Receipt: `src/frontend/evidence/fe01/review/evidence-receipt.json`; **46 actions, 1152 request + response events, zero unintended writes**. The only writes observed were four auth login POSTs.

- At 1440 and 390: real Dataset GET 200, authentic BDD Dataset 2 / CVAT project #2, one-row BDD search then clear, repeated-sync single notice, Home selection remains Home, arrow navigates to `/?view=summary`.
- Summary captures now wait for settled **Task #1**, confirmed in actual `/api/datasets/2/tasks/` HTTP 200 response and UI at both widths. Task/Job identity is real; displayed frame/quality fields remain labeled illustration.
- Report, Gate and History links were clicked with actual URL changes asserted at both widths. Review Center link presence was verified; its click was not tested.
- Four live PNGs and four separately named API503 preview PNGs are in `src/frontend/evidence/fe01/review/`. Preview uses isolated authenticated contexts with Dataset GET responses intercepted to 503; this is simulated failure evidence, not live aggregation data.
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

### Prior checks and remaining limits

Prior executor evidence (not rerun by Codex): `make check` exit 0 before final TopBar restoration, backend 603 + 1 skipped, frontend 370/38 files, detector 10, framework pass; lint/typecheck exit 0. After restoration, handoff reports focused FE-01 22/22 exit 0 (React act warnings), production build exit 0. Prior design verifier: 24 screens / 18 states; static verification only. `refresh-demo.sh` overall exit 1 due to unrelated port 3000 absence; FE-01 build/readiness succeeded per handoff.

Fresh narrow checks cover diff whitespace, source/reference preservation, CSS identity, zero shared-shell diff, merge/index preservation, receipt/screenshot integrity and privacy. No application source changed during evidence finalization.

Leader QA, new repair commit CI, clean release reproducibility, other roles/no-Dataset browser flow, delayed responses/user switching, pagination beyond page one, Task scope interactions, offscreen table scrolling, preview release/snapshot clicks and Review Center click are NOT VERIFIED by this fresh collector. Backend aggregation and Gate callout wiring remain pending. Please rerun QA after the reviewed repair is published; this PR does not close #147.
