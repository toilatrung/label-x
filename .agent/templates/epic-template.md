---
id: epic-template
title: Epic Template
type: planning
domain: governance
module: templates
tags: [epic, planning, template]
priority: 2
---
# Epic Template

## Usage Purpose

Use this template to define one outcome-oriented epic before task expansion begins.

## Record Metadata

- **Epic ID**: `E-<number>`
- **Title**: `<required>`
- **Owner**: `<required-person-or-agent-id>`
- **Status**: `EPIC_PROPOSED | EPIC_READY | EPIC_IN_PROGRESS | EPIC_BLOCKED | EPIC_DONE | EPIC_CANCELLED`
- **Milestone ID**: `M-<number>`
- **Created Date**: `YYYY-MM-DD`
- **Target Date**: `YYYY-MM-DD`
- **Priority**: `1 | 2 | 3 | 4 | 5`

## Objective

State one measurable outcome and the reason it is required.

## Scope

### Included

- `<required-scope-item>`

### Excluded

- `<required-exclusion-or-none>`

## Dependencies

- **Depends On**: `<epic-or-milestone-ids-or-none>`
- **Blocked By**: `<blocker-ids-or-none>`

## Related Files

- **Roadmap**: `.agent/planning/roadmap.md`
- **Milestones**: `.agent/planning/milestones.md`
- **Dependency Graph**: `.agent/planning/dependency-graph.md`
- **Decisions**: `<paths-or-none>`
- **Risks**: `<paths-or-none>`
- **Change Requests**: `<paths-or-none>`

## Acceptance Criteria

- [ ] Each criterion is observable and testable.
- [ ] Scope boundaries are explicit.
- [ ] Dependencies and governance links are current.
- [ ] Required reports and verification evidence are defined.

## Task Expansion Rules

- Create tasks only when status is `EPIC_READY`.
- Start task execution only when status is `EPIC_IN_PROGRESS`.
- Every task must reference this epic ID.

## Completion Criteria

- [ ] All linked tasks are `done` or formally cancelled.
- [ ] Acceptance criteria are verified with linked evidence.
- [ ] Required implementation, review, and QA reports exist.
- [ ] Open blockers and risks have an explicit disposition.

## Forbidden Actions

- Do not expand tasks while status is `EPIC_PROPOSED`.
- Do not mark the epic `EPIC_DONE` with unmet acceptance criteria.
- Do not change baselined scope without an approved change request.
- Do not record fabricated links, evidence, or completion state.

## Output Requirements

- Save the completed record in `.agent/planning/epics.md` or the project-approved epic registry.
- Preserve every heading in this template.
- Replace every `<required...>` placeholder; use `none` only where explicitly allowed.
