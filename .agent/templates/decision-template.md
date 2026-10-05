---
id: decision-template
title: Decision Template
type: governance
domain: governance
module: templates
tags: [decision, adr, template]
priority: 2
---
# Decision Template

## Usage Purpose

Use this template to record a consequential technical, product, process, or governance decision and its traceable rationale.

## Record Metadata

- **Decision ID**: `DEC-<number>`
- **Title**: `<required>`
- **Owner**: `<required-person-or-agent-id>`
- **Decision Makers**: `<required-person-or-role-ids>`
- **Status**: `proposed | under-review | accepted | rejected | superseded | deprecated`
- **Decision Type**: `architecture | product | process | governance | security | operations`
- **Created Date**: `YYYY-MM-DD`
- **Decision Date**: `YYYY-MM-DD | pending`

## Context

State the verified conditions, constraints, and problem requiring a decision.

## Decision Drivers

- `<measurable-driver-or-constraint>`

## Options Considered

| Option | Benefits | Costs and Risks | Constraint Fit |
|---|---|---|---|
| `<option-name>` | `<specific-benefits>` | `<specific-costs-and-risks>` | `meets | partially-meets | does-not-meet` |

## Decision Outcome

- **Selected Option**: `<required-when-accepted>`
- **Rationale**: `<required-when-accepted-or-rejected>`
- **Effective Date**: `YYYY-MM-DD | pending`

## Consequences

- **Positive**: `<specific-consequences>`
- **Negative**: `<specific-consequences>`
- **Follow-up Work**: `<task-ids-or-none>`

## Related Files

- **Affected Documents**: `<paths>`
- **Epics or Tasks**: `<ids-or-none>`
- **Change Requests**: `<paths-or-none>`
- **Risks**: `<paths-or-none>`
- **Supersedes**: `<decision-paths-or-none>`
- **Superseded By**: `<decision-path-or-none>`

## Completion Criteria

- [ ] Context, drivers, and viable options are documented.
- [ ] Decision makers and rationale are recorded.
- [ ] Follow-up work and affected documents are linked.
- [ ] Accepted decisions are mapped in `.agent/intelligence/git-nexus/decision-commit-map.md` when implemented.

## Forbidden Actions

- Do not record a decision as `accepted` without identified decision makers.
- Do not erase rejected options or consequences after acceptance.
- Do not silently modify an accepted decision; supersede it with a new record.
- Do not claim implementation without commit or report evidence.

## Output Requirements

- Save as `.agent/governance/decisions/DEC-<number>.md`.
- Preserve every heading and table column in this template.
- Use repository-relative links and exact enum values.
