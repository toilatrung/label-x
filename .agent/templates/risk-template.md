---
id: risk-template
title: Risk Template
type: governance
domain: governance
module: templates
tags: [risk, template]
priority: 2
---
# Risk Template

## Usage Purpose

Use this template to track an uncertain event or condition that could affect delivery, quality, security, compliance, cost, or operations.

## Record Metadata

- **Risk ID**: `RISK-<number>`
- **Title**: `<required>`
- **Owner**: `<required-person-or-agent-id>`
- **Status**: `identified | analyzing | mitigating | monitoring | accepted | realized | closed`
- **Category**: `technical | delivery | security | compliance | financial | operational | external`
- **Probability**: `low | medium | high`
- **Impact**: `low | medium | high | critical`
- **Priority**: `1 | 2 | 3 | 4 | 5`
- **Created Date**: `YYYY-MM-DD`
- **Review Date**: `YYYY-MM-DD`

## Risk Statement

Use the form: `If <cause>, then <event> may occur, resulting in <measurable impact>.`

## Exposure Assessment

- **Affected Scope**: `<modules-documents-epics-or-tasks>`
- **Impact Description**: `<specific-impact>`
- **Detection Signals**: `<observable-signals>`
- **Assumptions**: `<assumptions-or-none>`

## Related Files

- **Epics or Tasks**: `<ids-or-none>`
- **Decisions**: `<paths-or-none>`
- **Issues or Blockers**: `<paths-or-none>`
- **Change Requests**: `<paths-or-none>`
- **Evidence**: `<paths-or-none>`

## Response Plan

- **Strategy**: `avoid | mitigate | transfer | accept`
- **Mitigation Actions**: `<task-ids-or-specific-actions>`
- **Contingency Actions**: `<actions-if-realized>`
- **Trigger Threshold**: `<observable-threshold>`
- **Responsible Owner**: `<person-or-agent-id>`

## Review Record

- **Last Reviewed Date**: `YYYY-MM-DD`
- **Reviewed By**: `<person-or-agent-id>`
- **Probability Change**: `increased | unchanged | decreased`
- **Impact Change**: `increased | unchanged | decreased`
- **Review Evidence**: `<paths>`

## Completion Criteria

- [ ] The risk is eliminated, accepted by an authorized owner, transferred, or converted to an issue after realization.
- [ ] Final status and supporting evidence are recorded.
- [ ] Related tasks, blockers, issues, and decisions are updated.

## Forbidden Actions

- Do not close a risk solely because its review date passed.
- Do not accept a high or critical risk without an identified authorized owner.
- Do not use vague triggers or unowned mitigation actions.
- Do not delete prior assessments when exposure changes.

## Output Requirements

- Save as `.agent/governance/risks/RISK-<number>.md`.
- Preserve every heading in this template.
- Use repository-relative links and exact enum values.
