---
id: change-request-template
title: Change Request Template
type: governance
domain: governance
module: templates
tags: [change-request, template]
priority: 2
---
# Change Request Template

## Usage Purpose

Use this template to propose, assess, approve, and trace a change to a baselined requirement, contract, architecture, roadmap, or governed scope.

## Record Metadata

- **Change Request ID**: `CR-<number>`
- **Title**: `<required>`
- **Owner**: `<required-person-or-agent-id>`
- **Proposer**: `<required-person-or-agent-id>`
- **Status**: `draft | proposed | under-review | approved | rejected | implementing | implemented | withdrawn | superseded`
- **Change Type**: `scope | requirement | contract | architecture | roadmap | process`
- **Priority**: `1 | 2 | 3 | 4 | 5`
- **Created Date**: `YYYY-MM-DD`
- **Decision Due Date**: `YYYY-MM-DD`

## Proposed Change

Describe the exact before-state and requested after-state.

## Justification

State the evidence-based reason the change is required.

## Impact Assessment

- **Affected Baselines**: `<paths>`
- **Affected Epics or Tasks**: `<ids-or-none>`
- **Schedule Impact**: `<specific-impact-or-none>`
- **Cost or Resource Impact**: `<specific-impact-or-none>`
- **Security or Compliance Impact**: `<specific-impact-or-none>`
- **Compatibility or Migration Impact**: `<specific-impact-or-none>`

## Related Files

- **Affected Documents**: `<paths>`
- **Decisions**: `<paths-or-none>`
- **Risks**: `<paths-or-none>`
- **Issues or Blockers**: `<paths-or-none>`

## Approval

- **Decision**: `pending | approved | rejected`
- **Approver**: `<required-for-approved-or-rejected>`
- **Decision Date**: `YYYY-MM-DD`
- **Conditions**: `<conditions-or-none>`
- **Rationale**: `<required-for-approved-or-rejected>`

## Implementation Plan

- **Responsible Owner**: `<person-or-agent-id>`
- **Tasks**: `<task-ids>`
- **Validation Method**: `<checks>`
- **Rollback Method**: `<steps-or-not-applicable-with-reason>`

## Completion Criteria

- [ ] Approval is recorded before baseline modification.
- [ ] Approved changes are implemented and verified.
- [ ] All affected baselines and traceability links are updated.
- [ ] Status is `implemented`, `rejected`, `withdrawn`, or `superseded`.

## Forbidden Actions

- Do not modify a baseline while decision is `pending` or `rejected`.
- Do not self-approve unless the governance model explicitly authorizes it.
- Do not alter the approved scope without a new or superseding change request.
- Do not omit impact assessment or approval rationale.

## Output Requirements

- Save as `.agent/governance/change-requests/CR-<number>.md`.
- Preserve every heading in this template.
- Use repository-relative links and exact enum values.
