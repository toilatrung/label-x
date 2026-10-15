# Engine recovery and activity indicators

Implementation branch: `plan/engine-resilience-loading`.

## Runtime behavior

Detector inference admission uses `orchestration.ResourceLease`, keyed by the normalized physical worker URL. Revisions and runs targeting the same URL share one inference slot. Admission holds a DB row lock only while acquiring or releasing ownership, never during HTTP. The GPU worker's own inference lock remains the final protection against callers outside this deployment.

GPU responses preserve allowlisted error codes. `worker_busy` waits without consuming the inference retry allowance; transient network/timeout/429/5xx errors use the existing configured retry limit. Auth, invalid batches and invalid response formats terminate the shard. An independent shard's failure no longer revokes successful siblings. A client timeout leaves the endpoint quarantined until its previous lease expiry, because a remote inference might still be running.

VLM retries are persisted on each `VlmUnit` and scheduled as future Celery tasks. They do not sleep in a worker process. The DB budget and attempt records survive redelivery. Endpoint admission is shared across runs, and transient provider failures apply increasing cooldown, capped at 120 seconds, with a single request admitted after cooldown. A successful request resets cooldown. Both numeric and HTTP-date Retry-After values are accepted and bounded.

VLM failure affects the candidate concerned. Other in-flight results can still commit while their leases remain valid. Auth/quota errors stop unsent automatic candidates; manual evaluation generations remain independent. Deadline expiry produces `skipped` with a reason, rather than inventing failed provider requests. Skipped work is recorded as Not checked (`provider_unavailable`) in the ledger and remains in the eligible denominator. Candidate evidence exposes `state=skipped`, the specific reason and a human-review requirement.

Runs with failed or skipped VLM work finish with incomplete results even when legacy fail-fast is disabled. Targeted retries include skipped candidates, preserve existing evidence and queues, and allocate a fresh retry deadline for failed detector shards.

## Configuration and deployment

New settings (seconds):

| Setting | Default | Purpose |
| --- | --- | --- |
| `ENGINE_WAIT_TIMEOUT_SECONDS` | 1800 | Bound detector shard waiting/recovery; starts at dispatch or first claim |
| `VLM_STAGE_TIMEOUT_SECONDS` | 1800 | Bound the initial VLM stage from preparation; manual generations get their own deadline at dispatch or claim |
| `VLM_DISPATCH_WINDOW` | 1 | Limit broker tasks per run; physical endpoint admission remains one across runs |

The detector resource lease lasts at least 1800 seconds, or HTTP timeout plus 60 seconds if longer. Ordinary completion releases it immediately. A process crash or uncertain timeout can therefore produce a deliberate wait; progress labels and deadlines make this visible. These limits do not prove that arbitrary remote code has stopped; the worker lock must stay enabled.

The initial VLM stage has a total time budget, not an unlimited allowance per candidate. Increase its setting deliberately when expected candidate count and latency need more than 30 minutes. Published per-candidate max attempts and per-run call budgets are preserved. No automatic provider/model switching is performed.

Required rollout order:

1. Drain existing engine tasks, then apply additive migrations `runs.0015` and `orchestration.0009`.
2. Deploy API and every Celery consumer from the same revision; mixed old/new workers bypass the new endpoint gate.
3. Keep Celery beat running for `orchestration.redispatch_pending`. It recovers lost retry publications and closes expired waiting work. With the existing default interval, expiry may take one sweeper cycle to appear.
4. Build/restart the frontend after generating contract types. Start with a small detector batch and one VLM candidate, then increase load with observed counters.

The GPU worker code change adds only safe exception-class logging for inference failures. Deploy that change separately if the remote GPU host needs the extra diagnostic output; no credentials or image URLs are logged.

No production migration, restart, GPU redeployment, replay of run 11 or paid model request is part of this implementation checkout. Keep the running test instance separate until rollout is requested. Do not clear leases or rewrite historical evidence to force progress. If rollback is needed, drain work first and retain the additive schema/data.

## Progress UI

Run detail responses add optional per-engine `progress`: phase, next retry, deadline, last actual activity, pending/failed/skipped counts, reserved provider calls and staleness. List responses retain their existing query budget; they do not compute operational details per run.

The common `ProgressBar` animates overall Analysis and engine progress. Determinate width comes from processed-unit counters, including incomplete terminal units, and does not estimate remaining time or quality. Unknown totals use indeterminate motion. Static benchmark coverage remains a measurement.

Motion stops for terminal states, errors fetching progress, backend deadline expiry, or a successful poll older than 30 seconds. Labels expose waiting/retry and last actual backend activity separately from the last confirmed API update. Reduced-motion disables animations while preserving labels and ARIA values.

## Verification

Automated recovery tests use fake model clients, a separate PostgreSQL test database and an in-memory Celery broker. They cover shared endpoint admission, timeout quarantine, ownership fencing, detector busy recovery, sibling commit after failure, durable VLM retry/budget, stage deadlines and distinct skipped counts. UI tests cover active, indeterminate, paused, stale and terminal states. Live provider availability remains a deployment smoke check.

Validation on 2026-10-15:

- Full backend suite: 1634 passed, 3 skipped; two contract checks identified a missing nested progress schema and enum ordering. Both were corrected without test exemptions.
- Final contract/interface/recovery/run API regression group after those corrections: 105 passed.
- Focused GPU/detector/recovery group: 59 passed, 1 skipped; final VLM stage/retry/recovery group: 53 passed.
- Frontend progress and Execution History: 45 passed. Detector HTTP adapter: 14 passed.
- Backend lint/format, frontend TypeScript/ESLint, migration drift checks and strict typing of changed backend modules passed.
- The full suite was not repeated after the two schema corrections; the affected contracts and dependent run APIs were checked by the final 105-test group.
