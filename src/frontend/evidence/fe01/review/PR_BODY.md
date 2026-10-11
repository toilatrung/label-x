## Summary of Changes

Addresses frontend scope for Issue #147 (Draft PR, does not close #147).

### 1. Concrete Problem & Delivered Behavior

- **Problem**: LabelX required the foundational Quality Control Home (`/`) and Quality Summary overview (`/?view=summary`) with live dataset listing, responsive layout, context filtering, keyboard accessibility, and honest metric presentation without fictitious hardcoded stats or mock badges.
- **Delivered Behavior**:
  - **Quality Control Home (`/`)**: Connects to the real paginated dataset API (`getDatasets`, `cursorFrom`), supporting search filtering, keyboard row selection (Enter/Space), CVAT sync indicators, and unaggregated field notices.
  - **Quality Summary (`/?view=summary`)**: Displays dataset and run quality overview with canonical explanatory lead copy (*"Coverage thấp và lỗi nghiêm trọng luôn hiển thị riêng, không gộp vào một điểm chất lượng duy nhất."*), 4 KPI cards, and 4 region cards bound to real scoped datasets and CVAT tasks.
  - **Interactive ContextBar (`ContextBar.tsx`)**: Renders 6 canonical context pills (Dataset, Run, Snapshot, Scope, Guideline, Taxonomy) with interactive pickers for Dataset, Run, and Task Scope bound to scoped APIs. Includes loaded owner guards preventing self-cancellation loops and binds notices to current user + dataset identity (`noticeOwnerKey`).
  - **Responsive Geometry**: Matches canonical specifications at desktop 1440px (`max-width: 1440px; box-sizing: border-box`, content between `x = 24` and `x = 1416`) and mobile 390px (`x = 16` to `x = 374`).
  - **Zero Unintended Mutations**: All navigation and menu interactions produce 0 unintended POST/PUT/PATCH/DELETE write requests.

---

### 2. Supervisor Directives & Accepted Overrides

- **Honest Data Representation**: Overriding initial illustrative mock numbers (e.g. `92.4%`, `12,500 frames`), unaggregated fields display clean em dashes (`—`) accompanied by truthful `NotConnectedNotice` banners (`"Chức năng vẫn chưa được kết nối với server"`). No fake identifiers or illustrative sample badges are rendered.
- **Authentic Account & RBAC**: Tested with verified `qa_lead` account (`fe01_qalead`), which holds a genuine mapped CVAT identity; Review Center and Escalations tabs are displayed in accordance with authentic RBAC rules (`requiresIdentity = true`). Genuine RBAC checks are strictly preserved across all views.
- **Active Dataset Context**: Scoped to Dataset 2 (BDD100K 100-frame validation subset, CVAT Project 2, Task 1, Job 1, 100 frames, 2006 annotations).

---

### 3. Verification Status & Acceptance Gates

#### Completed Automated Checks
- **Frontend Test Suite**: **355/355 passed across 34 test files** (`npm test`), including 33 unit/integration tests in [`HomeQualitySummary.test.tsx`](src/frontend/src/__tests__/HomeQualitySummary.test.tsx).
- **Typecheck & Lint**: `npm run typecheck` and `npm run lint` exited `0` with 0 errors.
- **Production Bundle**: Turbopack build compiled successfully (`BUILD_ID=FZ6rgrLJq52_4Vl4-MCJL`).
- **Repository-Wide Checks (`make check`)**: Exited `0` cleanly (`FRAMEWORK_VALIDATION_PASS`):
  - Backend tests: 603 passed, 1 skipped.
  - Frontend tests: 355 passed.
  - Detector worker tests: 10 passed.

#### Remaining Acceptance Gates (In Progress / Pending)
- **Browser Evidence Collection**: Collector run completed (2026-10-11T22:47:08.420Z, duration 36s). Tested viewports: desktop 1440px and mobile 390px across accounts: fe01_qalead, fe01_no_dataset. Verified 47 actions and 649 network requests with 0 ERROR findings and 0 unintended writes. (No claim of overall PASS or identical full screenshots is made, as live dynamic data and truthful missing-value notices intentionally differ from static fixture designs).
- **Clean Final-Commit Production Reproduction**: Pending execution and verification against the final commit.
- **Human Interactive Demo**: Final acceptance gate requires human walkthrough and review.

---

### 4. Review Artifacts & Receipt

Visual screenshots and interaction proofs are documented in `src/frontend/evidence/fe01/review/`:
- `ref-home-1440.png` & `live-home-1440.png` (Desktop 1440px Home comparison)
- `ref-home-390.png` & `live-home-390.png` (Mobile 390px Home comparison)
- `ref-summary-1440.png` & `live-summary-1440.png` (Desktop 1440px Summary comparison)
- `ref-summary-390.png` & `live-summary-390.png` (Mobile 390px Summary comparison)
- `menu-proof-1440.png` & `menu-proof-390.png` (ContextBar picker dropdown proof)
- [`evidence-receipt.json`](src/frontend/evidence/fe01/review/evidence-receipt.json) (Sanitized machine-readable verification receipt)
- [`review-notes.md`](src/frontend/evidence/fe01/review/review-notes.md) (Detailed geometric fidelity & interaction notes)
