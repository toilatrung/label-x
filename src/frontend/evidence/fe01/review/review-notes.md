# FE-01 Quality Control Home & Summary Review Notes

## 1. Scope & Implementation Overview
- **Issue**: Issue #147 — FE-01: Quality Control Home and Quality Summary (Relates to #147, does not close #147)
- **Branch**: `feat/feat/FE-01-home-quality-summary`
- **Base Branch**: `develop-fe` (pinned baseline `9a214fb8e0d3409d4c3e52e548fa3fdb7ea02e61`)
- **Canonical Design Sources**:
  - [`docs/design/screens/Main.dc.html`](../../../../../docs/design/screens/Main.dc.html) (Quality Control Home)
  - [`docs/design/screens/Dashboard.dc.html`](../../../../../docs/design/screens/Dashboard.dc.html) (Quality Summary)
  - [`docs/design/screens/TopBar.dc.html`](../../../../../docs/design/screens/TopBar.dc.html) (TopBar navigation)
  - [`docs/design/screens/ContextBarStates.dc.html`](../../../../../docs/design/screens/ContextBarStates.dc.html) (ContextBar pills & interactive pickers)

---

## 2. Supervisor Directives & Accepted Overrides

### A. Honest Data Representation vs. Illustrative Values
- **Human Directive**: The initial issue #147 description contained illustrative mock figures (e.g. `92.4%`, `12,500 frames`, fake IDs, sample badges). The human supervisor explicitly directed that **NO illustrative fixtures or fabricated sample badges** be rendered in production.
- **Resolution**:
  - Real API data is rendered where connected (Dataset pagination, CVAT project mapping, Run list, CVAT tasks for scope).
  - Unaggregated metrics (Frame counts, Engine coverage, Candidate issue breakdown) render clean em dashes (`—`).
  - Regions awaiting dedicated aggregation endpoints display truthful `NotConnectedNotice` (`"Chức năng vẫn chưa được kết nối với server"` + concise detail).
  - Zero mutation writes: Navigating and interacting with menus generates 0 unintended POST/PUT/PATCH/DELETE requests.

### B. Canonical Copy & Clean Regional Banners
- Restored canonical explanatory lead sentence in Quality Summary:
  > *"Tình trạng kiểm tra của [Dataset] · Quality Control Run: [Run]. Coverage thấp và lỗi nghiêm trọng luôn hiển thị riêng, không gộp vào một điểm chất lượng duy nhất."*
- Cleaned all regional notices of technical implementation jargon (removed `"trong FE-01"` and duplicate phrases).

### C. Authentic User Account & RBAC
- Tested with authentic mapped `qa_lead` account (`fe01_qalead`).
- The `fe01_qalead` account holds a verified genuine CVAT identity; the Review Center and Escalations tabs are displayed in accordance with authentic RBAC rules (`requiresIdentity = true`).
- Authentic RBAC rules are strictly preserved across all user roles and navigation views.
- Active dataset: Dataset 2 (BDD100K 100-frame validation subset, CVAT Project 2, Task 1, Job 1, 100 frames, 2006 annotations).

---

## 3. Visual & Geometric Fidelity

| Viewport | Container Geometry | Left / Right Margin | Match Status |
| :--- | :--- | :--- | :--- |
| **Desktop 1440px** | `max-width: 1440px; box-sizing: border-box` | Content spans `x = 24` to `x = 1416` (`padding: 24px`) | Matches canonical `Main.dc.html` 1:1 |
| **Mobile 390px** | `width: 100%; box-sizing: border-box` | Content spans `x = 16` to `x = 374` (`padding: 16px`) | Matches responsive Design System specifications |

*Note on Browser Evidence & Verification*:
Mobile geometry and touch flows are in progress and subject to verified browser collector output in `evidence-summary.json`. No claim of overall PASS or identical full screenshots is made, as live dynamic data and truthful missing-value notices intentionally differ from static fixture designs.

---

## 4. Interaction & Fault Flow Verifications

1. **ContextBar Pickers**:
   - Dataset picker: multi-page pagination, search filter, selection updates active dataset and resets dependent Run/Task state.
   - Run picker: displays runs scoped strictly to active Dataset; error on first 403 displays retry button without infinite loop.
   - Task Scope picker: displays `"Toàn dataset"` plus individual CVAT tasks scoped to Dataset.
   - Coordinated menu open behavior: opening a ContextBar picker closes TopBar menus and other pickers; clicking outside or pressing Escape closes the menu.
2. **Quality Control Home**:
   - Table rows support click, Enter, and Space selection.
   - Pagination preserves search query and recovers from repeated cursors.
3. **Quality Summary**:
   - Task table rows support click, Enter, Space to update scope.
   - Preserves state across authenticated user transitions in mounted tree.

---

## 5. Automated Verification Evidence (`make check`)

Full repository check executed with exit code `0` (clean pass):
- **Backend Test Suite**: **603 passed, 1 skipped** (Django core, API contracts, snapshots, runs, tasks, effort tracking).
- **Frontend Test Suite**: **355 passed across 34 test files** (`npm test`), including 33 unit/integration tests in [`HomeQualitySummary.test.tsx`](../../../../../src/frontend/src/__tests__/HomeQualitySummary.test.tsx).
- **Detector Worker**: **10 passed** (Ruff check & pytest).
- **Repository Framework Validator**: `FRAMEWORK_VALIDATION_PASS`.
- **Production Bundle**: Turbopack build successful (`BUILD_ID=FZ6rgrLJq52_4Vl4-MCJL`).

---

## 6. Remaining Acceptance Gates

- **Browser Evidence Collection**: Collector run completed (2026-10-11T22:47:08.420Z, duration 36s). Tested viewports: desktop 1440px and mobile 390px across accounts: fe01_qalead, fe01_no_dataset. Verified 47 actions and 649 network requests with 0 ERROR findings and 0 unintended writes.
- **Clean Final-Commit Production Reproduction**: Pending verification against final commit.
- **Human Interactive Demo**: Final acceptance gate requires human walkthrough and review.

---

## 7. Review Artifacts & Receipt Summary

- **Receipt**: [`evidence-receipt.json`](evidence-receipt.json) (compact public verification metadata).
- **Paired Screenshots**:
  - `ref-home-1440.png` vs `live-home-1440.png`
  - `ref-home-390.png` vs `live-home-390.png`
  - `ref-summary-1440.png` vs `live-summary-1440.png`
  - `ref-summary-390.png` vs `live-summary-390.png`
  - ContextBar picker proofs: `menu-proof-1440.png` & `menu-proof-390.png`
- **Privacy Audit**: Staged artifacts audited to confirm zero passwords, tokens, or session cookies are included.
