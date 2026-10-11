# T-037 Handoff: ReviewWorkspace UI & In-Memory Queue Integration

> **Status**: Partial Implementation Draft PR (Revision 2 Approved, Consuming T-035 Interfaces)
> **Task ID**: `T-037` (Issue #104)
> **Epic Reference**: Epic E-14 (Issue #97, Package P06)
> **Baseline SHA**: `7effc8ed4ef1dbe644b177a21051e855405f8c95` (from `origin/integration/m03`, including T-032 #99/PR111, T-034 #101/PR129, T-035 #102/PR130, T-044 #123/PR132, T-036 #103/PR133)
> **Dependency Status**:
> - **T-032** (#99 / PR111): DELIVERED (Auth, session, roles, identity mapping)
> - **T-034** (#101 / PR129): DELIVERED (ReviewQueues, dataset/run selection, risk/random queues, claim/resume/renew)
> - **T-033**: DELIVERED (Queue/lease backend API)
> - **T-035** (#102 / PR130): **MERGED** (Merge SHA `7326af39f5c531a72144eb08c070b5cf3877a084`, source HEAD `2afb6a16709bd15ffc2d760dbd4897aebd06a09b`)
> - **T-036** (#103 / PR133): **MERGED** (Merge SHA `7effc8ed4ef1dbe644b177a21051e855405f8c95`, source HEAD `d914a767283eef61868eed7cff419cb5c96a38e0`). Lifecycle adapter integrated in `useEffortCollector.ts`; idle threshold policy awaiting PO approval (TBD-09)
> - **T-040**: Rework runtime owner (Atomic `POST /api/rework/`)
> - **T-046** (#125): E2E Live Integration & Cross-Role Delivery Owner
> **Configuration Key**: `NEXT_PUBLIC_API_BASE_URL` (Required environment configuration; default URLs are configuration requirements, not evidence of running services)
> **Requested Reviewer**: `DucHa180104`
> **Overall Acceptance / Integration Status**: **BLOCKED** (Pending live backend API stack, live T-040 rework runtime, live CVAT/T-046 stack, and interactive reviewer evaluation)

---

## 1. Overview & Architectural Boundary

Under user authorization and Revision 2 partial draft PR boundaries:
- Delivered baseline components from **T-032** (auth & session) and **T-034** (ReviewQueues, dataset/run selector, risk/random queues, claim/resume/renew) are preserved intact.
- An in-memory handoff connects `ReviewQueues` to `ReviewWorkspace` inside the AppShell upon a valid server `LeaseGrant` without URL credentials or second claim calls.
- **T-035 PR130** (MERGED, merge SHA `7326af39f5c531a72144eb08c070b5cf3877a084`, final HEAD `2afb6a16709bd15ffc2d760dbd4897aebd06a09b`) interfaces are consumed in frontend components without copying/cherry-picking backend models, migrations, or schemas into T-037.
- **PO Decision Compliance**: Per Product Owner decision on Issue #102 (comment 6106568257), `request_fix` belongs to atomic `POST /api/rework/` in T-040, NOT `POST /api/issues/{id}/decisions/`. The 5th action `request_fix` is rendered disabled with clear T-040 explanation and is never dispatched to POST decisions.
- **Governance Gap**: Owner acceptance comment is currently not present in Issue #104. Implementation and publication preparation proceed under user's explicit directive without impersonating the owner.
- **No PASS/done, owner acceptance, QA sign-off, or merge is claimed**. Full integration (A1–A12) remains blocked pending live stack verification and T-046.

---

## 2. Consumed T-035 PR130 Interfaces & Payload Mapping

### Usable Interface Mappings (Verified T-035 PR130 MERGED)
1. **`GET /api/frames/{id}/issues/`**:
   - Mapped into `ReviewCanvas`: image media (`frame.image_url`), frame dimensions (`frame.width`, `frame.height`), and CVAT deep link (`frame.cvat_deep_link`).
   - Mapped into `ReviewEvidenceTable`: engine statuses (`engines`), prediction classes, confidence scores, IoU, expected vs actual values.
   - Pinned `guideline_version` forwarded to `ReviewGuidelineLookup`.
   - **Validation**: Frame response `id` and `run_id` are strictly validated against the active queue grant; mismatched or stale payloads are rejected and never render an editable workspace.
2. **`GET /api/issues/{id}/`**:
   - Authoritative issue details and historical `review_decisions` are reconciled upon saving decisions.
3. **`POST /api/issues/{id}/decisions/` & State Machine (Follow-Up 18)**:
   - **Strict state enforcement**: Only `issue.state === 'in_review'` allows submitting new direct decisions.
   - Non-in_review states (`confirmed`, `rejected`, `escalated`, `resolved`, `pending_review`, `fix_pending`) display an informational notice, lock form controls, and strictly forbid dispatching `POST /api/issues/{id}/decisions/`.
   - Authoritative saved decision history (`issue.review_decisions`) is retained and displayed in DOM across all states.
   - Dispatches the **4 direct actions**: `confirm`, `reject`, `uncertain`, `escalate`.
   - Requires exact snapshot SHA revision.
   - `confirm` action validates that the chosen family strictly equals `issue.family`.
   - Super Admin role always requires a non-empty `override_reason`.
   - Generates and preserves canonical RFC 4122 v4 UUID in `Idempotency-Key` headers across retries.
   - Preserves successful server saves even if subsequent GET refresh encounters network issues.
   - **Save & Next Navigation**: "Lưu và chuyển issue tiếp ›" advances via `onNextIssue` ONLY after successful authoritative save and reconciliation. Failed saves (409, 400, 422, network errors) never advance.
4. **`POST /api/issues/` (Manual Issue Creation)**:
   - Supports `manual_object` (strictly requiring `namespace: 'cvat_shape'`) and `manual_region` (with server-allocated `reviewer_region` UUID).
   - Validates pixel bounding box coordinates are finite and bounded within frame width/height.
   - Enforces description limit of max 2000 characters.
   - Uses canonical RFC 4122 v4 UUID in `Idempotency-Key` header.
   - Unmount/context guards verify `isMountedRef` and matching `targetFrameId`/`targetLeaseId` before state mutations.
5. **`POST /api/frames/{id}/complete/`**:
   - Passes `lease_id`.
   - Handles 422 `BUSINESS_RULE_UNMET` by extracting `details.undecided_issue_ids` and rendering direct jump buttons.

### Design System & Mock Alignment (`docs/design/screens/ReviewWorkspace.dc.html`)
- **Header (`lx-head`)**: Displays `h1` "Review Workspace", lead paragraph, real context IDs (`Task`, `Job`, `Reviewer`, `Run`), and "Về hàng đợi" action.
- **Workflow Navigation (`lx-flow`)**: 3-step indicator (`Hàng đợi` &rarr; `Kiểm tra ảnh` [active] &rarr; `Theo dõi sửa`).
- **Desktop & Responsive Layout (`lx-ws lx-ws--reference`)**: 2-column desktop layout (`minmax(0, 1fr) 420px`), collapses to 1-column on &le;900px, with stage view left and aside panel right.
- **Stage Bottom Bar**: Includes disabled frame navigation with tooltip explaining unavailable frame-list/lease behavior (`Chuyển frame chỉ thực hiện qua hàng đợi ReviewQueues...`), plus in-frame issue navigation (`‹ Issue trước` / `Issue sau ›`).
- **Aside Panel Details**: Dynamic issue title matching findings, annotation class (with honest T-035 gap notice), revision hash, and similar cases / lineage links details.

### Error Code Classification & Concurrency Handling
- **409 Conflict codes are differentiated**:
  - `LEASE_CONFLICT`: Calls `onLeaseConflict()`, invalidates local lease, and locks mutations.
  - `INVALID_TRANSITION`: Displays specific transition/revision mismatch error; **does NOT invalidate lease** or destroy saved decisions.
  - `IDEMPOTENCY_KEY_REUSED`: Displays reused key error; **does NOT invalidate lease**.
  - `ISSUE_EXISTS`: Displays duplicate issue error in manual modal; **does NOT invalidate lease**.
- **400 / 403 / 422**: Handled with dedicated code-level parsing without mislabeling errors as lease expiry.

---

## 3. Remaining Interface Gaps & Contract Proposal

### Identified Gaps
1. **Plain Reviewer Snapshot Revision Gap**:
   - `POST /api/issues/{id}/decisions/` requires `revision` (snapshot SHA).
   - `GET /api/runs/{id}/` provides `snapshot_id`, but `GET /api/snapshots/{id}/` (which provides `revision_hash`) is RBAC-restricted to `qa_lead`, `qc_admin`, `super_admin`.
   - Plain `reviewer` role cannot call `GET /api/snapshots/{id}/`.
   - *Current Implementation*: For eligible roles (`qa_lead`, `super_admin`), the workspace automatically retrieves and validates the locked snapshot revision. For plain Reviewers, the UI disables decision submission and displays an informative notice without bypassing RBAC.
2. **Full Annotation Shapes Unavailable**:
   - `GET /api/frames/{id}/issues/` serializes issue anchor bboxes, but does not expose full annotation shapes from CVAT. Full annotations remain unavailable.
3. **Zero-Issue Frame Manual Policy Gap**:
   - Without an existing issue on the frame or a context policy prop, `anchorPolicyVersion` cannot be inferred, so manual issue creation remains locked.
4. **T-036 Effort Collector**:
   - Module upstream merged; lifecycle adapter integrated via `useEffortCollector.ts`. Idle threshold cutoff policy awaiting PO approval / deployment configuration (TBD-09; `idleAfterMs: null`).
5. **T-040 Atomic Rework**:
   - Direct `request_fix` input is excluded from POST decisions per PO decision and awaits T-040.

### Actionable Contract Proposal for API Owner
> **Proposal**: Include `snapshot_revision: string` directly in the `FrameSummary` schema (returned by `GET /api/frames/{id}/issues/` and `LeaseGrant.frame`).
> **Rationale**: This enables plain Reviewers to obtain the authoritative snapshot SHA bound to their claimed frame without needing elevated RBAC permissions to read the entire snapshot resource via `GET /api/snapshots/{id}/`.

---

## 4. Supported Routes & In-Memory Queue Handoff

1. `/review` ([src/app/review/page.tsx](file:///home/ductho/Build%20phase%20gpt/label-x/.agy-mcp/worktrees/job_1791702264_bbf193e2e4af/src/frontend/src/app/review/page.tsx)):
   - Renders `ReviewQueues` with dataset and run ID selection.
   - Displays active lease context upon claim or resume.
   - Provides **"Vào kiểm tra frame (Workspace)"** when active grant is valid.
   - Renders `ReviewWorkspace` inline inside AppShell with **"← Quay lại danh sách hàng đợi"** action.
   - Passes `activeGrant.frame.id`, `activeGrant.lease`, `effectiveRunId`, and `datasetId` directly in memory.
2. `/review/workspace?frame_id=<id>` ([src/app/review/workspace/page.tsx](file:///home/ductho/Build%20phase%20gpt/label-x/.agy-mcp/worktrees/job_1791702264_bbf193e2e4af/src/frontend/src/app/review/workspace/page.tsx)):
   - Standalone inspection entry point in safe **read-only mode** (`initialLease = null`).

---

## 5. Stable A1–A12 Requirements Matrix

| ID | Exact Requirement | Real Integration Status | Local Unit / Integration Evidence & Blockers |
|----|-------------------|-------------------------|----------------------------------------------|
| **A1** | Real auth queue lease binding | **BLOCKED** | Tested locally in `ReviewQueueWorkspaceIntegration.test.tsx`; live backend unverified. |
| **A2** | Modes / layers / zoom / pan | **BLOCKED** | Tested locally in `ReviewCanvas.test.tsx`; live frame media pending T-035. |
| **A3** | Evidence / engine / pinned guideline / Case | **BLOCKED** | Tested locally in `ReviewWorkspaceT035Integration.test.tsx` & `ReviewGuidelineLookup.test.tsx`; Case unavailable on contract. |
| **A4** | Five decisions validation persisted | **BLOCKED** | Tested locally in `ReviewWorkspaceT035Integration.test.tsx` (4 direct actions + request_fix T-040 rework indicator); live `/api/issues/{id}/decisions/` unverified. |
| **A5** | Manual object / region | **BLOCKED** | Tested locally in `ReviewManualIssueModal` (cvat_shape validation, canonical UUID, 2000 char limit); pending live T-035 anchor-v1. |
| **A6** | Complete / undecided | **BLOCKED** | Tested locally in `ReviewWorkspace.test.tsx` (422 handling with undecided IDs); live complete endpoint unverified. |
| **A7** | Lease races saved decisions retained | **BLOCKED** | Tested locally in `ReviewWorkspaceT035Integration.test.tsx` (409 LEASE_CONFLICT vs INVALID_TRANSITION/IDEMPOTENCY_KEY_REUSED); live multi-user concurrency unverified. |
| **A8** | Role / scope / identity / self-review | **BLOCKED** | Tested locally in `ReviewWorkspace.test.tsx` (403 error parsing) & role snapshot resolution; live server audit unverified. |
| **A9** | Actual CVAT job / frame | **BLOCKED** | Component renders genuine `cvat_deep_link` attribute; live CVAT stack pending T-046. |
| **A10** | Collector lifecycle | **BLOCKED** | Lifecycle adapter integrated in `useEffortCollector.ts` using upstream T-036 module; tested locally in `ReviewEffortIntegration.test.tsx`; live API ingest & PO idle threshold policy unverified. |
| **A11** | Error / loading / empty / stale / retry | **BLOCKED** | Tested locally in `ReviewWorkspaceT035Integration.test.tsx` (UUID retry reuse, stale response discard); live network unverified. |
| **A12** | Final clean production reproduction / user interactive confirmation | **BLOCKED** | Production build verified; live user demonstration and interactive sign-off pending. |

---

## 6. Reproduction Commands

To reproduce local verification:
```bash
cd src/frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```
