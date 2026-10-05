---
id: epic-expansion-prompt
title: Epic Expansion Prompt
type: reference
domain: agents
module: prompts
tags: [prompt, epic, tasks]
priority: 1
---
# Epic Expansion Prompt

## Role

Act as the `planner` and `coordinator` responsible for expanding one authorized epic into bounded executable tasks.

## Responsibilities

- Confirm the selected epic is `EPIC_READY`.
- Retrieve context from epic scope, domain, module, dependencies, governance links, and expected outputs.
- Create the minimum task set needed to satisfy epic acceptance criteria.
- Preserve traceability from each task to the epic and required evidence.

## Required Inputs

- One `EPIC_READY` epic with owner, scope, acceptance criteria, and dependencies
- Applicable context package, decisions, risks, blockers, and change requests
- `.agent/templates/task-template.md`

## Allowed Actions

- Add task records to `.agent/execution/task-board.md` while the epic remains `EPIC_READY`.
- Add task dependency edges to `.agent/planning/dependency-graph.md`.
- Create or update a bounded context package.
- Transition the epic to `EPIC_IN_PROGRESS` only after expanded tasks validate and before any task starts.
- Update current context and session history.

## Forbidden Actions

- Do not expand an epic in any status other than `EPIC_READY`.
- Do not add work outside epic scope or an approved change request.
- Do not start a task before the epic is `EPIC_IN_PROGRESS`.
- Do not implement application code during expansion.

## Required Outputs

- Bounded task records with owners, dependencies, acceptance criteria, verification, and output requirements
- Updated dependency graph
- Epic transition evidence when moved to `EPIC_IN_PROGRESS`
- Updated current context and session record

## Validation Rules

- Task statuses use `pending | in-progress | blocked | review | done | cancelled`.
- Every task references the selected epic and has one accountable owner before execution.
- Every epic acceptance criterion maps to at least one task output or verification rule.
- No task begins in `in-progress` during expansion.
- Framework validation passes after expansion.
