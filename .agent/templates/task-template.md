---
id: task-template
title: Task Template
type: execution
domain: governance
module: templates
tags: [task, execution, template]
priority: 2
---
# Task Template

## Usage Purpose

Use this template to define one bounded, independently verifiable unit of authorized epic work.

## Record Metadata

- **Task ID**: `T-<number>`
- **Epic ID**: `E-<number>`
- **Title**: `<required>`
- **Owner**: `<required-person-or-agent-id>`
- **Status**: `pending | in-progress | blocked | review | done | cancelled`
- **Created Date**: `YYYY-MM-DD`
- **Target Date**: `YYYY-MM-DD`
- **Priority**: `1 | 2 | 3 | 4 | 5`

## Objective

State the single deliverable or state change this task must produce.

## Scope

### Included

- `<required-work-item>`

### Excluded

- `<required-exclusion-or-none>`

## Preconditions

- [ ] Parent epic status is `EPIC_IN_PROGRESS`.
- [ ] Required context package is available.
- [ ] Dependencies, approvals, and access are available.

## Related Files

- **Context Package**: `<path>`
- **Parent Epic**: `.agent/planning/epics.md#<epic-anchor>`
- **Decisions**: `<paths-or-none>`
- **Risks**: `<paths-or-none>`
- **Blockers**: `<paths-or-none>`
- **Change Requests**: `<paths-or-none>`

## Acceptance Criteria

- [ ] `<required-observable-condition>`
- [ ] Verification method is specified for each condition.

## Verification Requirements

- **Automated Checks**: `<commands-or-none-with-reason>`
- **Manual Checks**: `<steps-or-none-with-reason>`
- **Expected Evidence**: `<report-paths-logs-or-artifacts>`

## Completion Criteria

- [ ] Every acceptance criterion passes.
- [ ] Required reports are stored in `.agent/reports/`.
- [ ] Implementing commits are recorded in `.agent/intelligence/git-nexus/task-commit-map.md`.
- [ ] Current context and task board reflect the final status.

## Forbidden Actions

- Do not perform work outside the stated scope.
- Do not execute without an authorized parent epic.
- Do not mark status `done` before verification completes.
- Do not fabricate test, review, report, or commit evidence.

## Output Requirements

- Register the task in `.agent/execution/task-board.md`.
- Preserve every heading in this template.
- Replace every `<required...>` placeholder; use `none` only where explicitly allowed.
