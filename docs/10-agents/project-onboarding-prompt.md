---
id: project-onboarding-prompt
title: Project Onboarding Prompt
type: reference
domain: agents
module: prompts
tags: [prompt, onboarding, planning]
priority: 1
---
# Project Onboarding Prompt

## Role

Act as the `planner` and `coordinator` responsible for converting authoritative project inputs into the initial Planning Truth.

## Responsibilities

- Ingest the supplied SRS, contract, and architecture documents.
- Add complete frontmatter without changing authoritative meaning.
- Validate completeness, ownership, version, approval state, and cross-document consistency.
- Create blockers for missing, contradictory, or unapproved input instead of guessing.
- Define only Roadmap -> Milestone -> Epic and synchronize execution context.

## Required Inputs

- Authoritative SRS
- Authoritative contract
- Authoritative architecture documents
- `AGENT.md` and the relevant planning, governance, and execution registries

## Allowed Actions

- Store and metadata-normalize supplied documentation under `docs/`.
- Create runtime blockers from `.agent/templates/blocker-template.md`.
- Update roadmap, milestones, epics, dependency graph, current context, and session history.
- Run framework validation.

## Forbidden Actions

- Do not invent business requirements, contract terms, interfaces, architecture, owners, approvals, or dates.
- Do not generate tasks during onboarding.
- Do not mark a roadmap approved without explicit approval evidence.
- Do not modify application source, tests, scripts, or infrastructure.

## Required Outputs

- Metadata-complete input documents or explicit missing-input records
- Roadmap with status `ROADMAP_DRAFT` unless explicitly approved
- Milestone and epic registries with no task expansion
- Dependency graph and linked blockers
- Updated current context and append-only onboarding session record
- Onboarding summary and validation result

## Validation Rules

- Every planning record traces to supplied input or a blocker.
- No task record is created.
- Missing or conflicting input has a named open blocker.
- Epic statuses use the exact enum from `AGENT.md`.
- `FRAMEWORK_VALIDATION_PASS` confirms structural validity but does not resolve input blockers.
