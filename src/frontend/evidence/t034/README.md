# T-034 ReviewQueues Evidence & Reproduction Guide

## 1. Overview
- **Task**: T-034 / issue #101 — ReviewQueues trên API thật
- **Snapshot**: `label-x-101-T034-r1`
- **Execution Base**: `origin/integration/m03` (`0e0204ee5ab992b9b54835056dae19c0c26baacd`)
- **Branch**: `codex/T-034-review-queues`

## 2. Dependency Status
- **T-033 Status**: NOT MERGED on `origin/integration/m03`.
- **Runtime module `review`**: Not yet present in backend codebase at integration base.
- **Real API Acceptance (AC A3, A6)**: **BLOCKED** pending merge of backend T-033.

## 3. Implemented Components
1. `src/frontend/src/lib/review/types.ts`: Domain types strictly aligned with OpenAPI schemas (`QueueName`, `RankedFrame`, `LeaseGrant`, etc.).
2. `src/frontend/src/lib/review/api.ts`: Typed API client handling `runs_ranking`, `queues_next`, `leases_renew`, and graceful 204 No Content handling without JSON parse errors.
3. `src/frontend/src/components/review/ReviewDatasetPicker.tsx`: Reviewer-scoped dataset selector using `canAccessReview`.
4. `src/frontend/src/components/review/ReviewQueues.tsx`: Two independent queue tabs (risk & random), server filters, cursor-based pagination, composite frame keys (`Task #${cvat_task_id} • Frame #${frame_number}`), claim action, resumed badge, active lease context, and comprehensive error states (204, 403, 409 LEASE_CONFLICT, 5xx).
5. `src/frontend/src/app/review/page.tsx`: Production route integrating `ReviewQueues` protected by `AuthGuard` (`canAccessReview`, `requiresIdentity`).
6. `src/frontend/src/__tests__/ReviewQueues.test.tsx`: Test suite covering AC A1–A4 scenarios.
7. `src/frontend/evidence/t034/harness.html`: Test harness document for manual verification by T-046.

<!-- issue-migration-2026-10-17:start -->

Historical issue references were archived on 2026-10-17; original text above is preserved.

| Old issue | Current follow-up / archive |
|---|---|
| #101 | [Mapping and scope](../../../../docs/08-devops/github-issue-migration-2026-10-17.html#issue-101) |
<!-- issue-migration-2026-10-17:end -->
