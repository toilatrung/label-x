---
id: blocker-template
title: Blocker Template
type: governance
domain: governance
module: templates
tags: [blocker, template]
priority: 2
---
# Blocker Template

## Usage Purpose

Use this template when an epic or task cannot proceed because a specific dependency, approval, access, decision, or defect is unresolved.

## Record Metadata

- **Blocker ID**: `BLOCKER-<number>`
- **Title**: `<required>`
- **Owner**: `<required-person-or-agent-id>`
- **Reporter**: `<required-person-or-agent-id>`
- **Status**: `open | investigating | workaround-active | resolved | accepted | cancelled`
- **Blocker Type**: `dependency | approval | access | decision | defect | environment | external`
- **Priority**: `1 | 2 | 3 | 4 | 5`
- **Created Date**: `YYYY-MM-DD`
- **Target Resolution Date**: `YYYY-MM-DD`

## Blocking Condition

State the exact condition preventing progress and the evidence confirming it.

## Impact

- **Blocked Epics or Tasks**: `<ids>`
- **Blocked Deliverables**: `<outputs>`
- **Schedule or Quality Impact**: `<specific-impact>`

## Related Files

- **Affected Records**: `<paths>`
- **Issues**: `<paths-or-none>`
- **Decisions**: `<paths-or-none>`
- **Risks**: `<paths-or-none>`
- **Change Requests**: `<paths-or-none>`

## Resolution Plan

- **Required Action**: `<specific-action>`
- **Responsible Owner**: `<person-or-agent-id>`
- **Dependency or Approval**: `<identifier-or-none>`
- **Workaround**: `<bounded-workaround-or-none>`
- **Verification Method**: `<check>`

## Completion Criteria

- [ ] The blocking condition no longer prevents affected work.
- [ ] Resolution evidence is linked.
- [ ] Affected epic and task statuses are updated.
- [ ] Workaround removal is tracked when applicable.

## Forbidden Actions

- Do not mark status `resolved` based only on a proposed action.
- Do not continue blocked work through an unauthorized workaround.
- Do not omit affected epic or task links.
- Do not fabricate resolution evidence.

## Output Requirements

- Save as `.agent/governance/blockers/BLOCKER-<number>.md`.
- Preserve every heading in this template.
- Use repository-relative links and exact enum values.
