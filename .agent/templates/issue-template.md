---
id: issue-template
title: Issue Template
type: governance
domain: governance
module: templates
tags: [issue, template]
priority: 3
---
# Issue Template

## Usage Purpose

Use this template to record a defect, gap, inconsistency, or actionable concern requiring tracked resolution.

## Record Metadata

- **Issue ID**: `ISSUE-<number>`
- **Title**: `<required>`
- **Owner**: `<required-person-or-agent-id>`
- **Reporter**: `<required-person-or-agent-id>`
- **Status**: `open | triaged | in-progress | blocked | resolved | closed | rejected`
- **Issue Type**: `defect | gap | inconsistency | improvement | process`
- **Priority**: `1 | 2 | 3 | 4 | 5`
- **Created Date**: `YYYY-MM-DD`
- **Target Date**: `YYYY-MM-DD | none`

## Description

State the observed condition in factual, reproducible terms.

## Impact

- **Affected Scope**: `<modules-documents-or-processes>`
- **Severity**: `critical | high | medium | low`
- **User or Delivery Impact**: `<specific-impact>`

## Reproduction Evidence

- **Preconditions**: `<conditions-or-not-applicable>`
- **Steps**: `<ordered-steps-or-not-applicable>`
- **Observed Result**: `<result>`
- **Expected Result**: `<result>`
- **Evidence Paths**: `<paths-or-none>`

## Related Files

- **Affected Files**: `<paths>`
- **Tasks or Epics**: `<ids-or-none>`
- **Decisions**: `<paths-or-none>`
- **Risks**: `<paths-or-none>`
- **Blockers**: `<paths-or-none>`

## Acceptance Criteria

- [ ] Root cause or disposition is documented.
- [ ] Corrective outcome is defined in observable terms.
- [ ] Regression verification is defined when applicable.

## Resolution

- **Resolution Type**: `fixed | duplicate | rejected | accepted-risk | superseded | not-applicable`
- **Resolution Summary**: `<required-before-resolved>`
- **Verification Evidence**: `<paths-required-before-closed>`
- **Resolved By**: `<person-or-agent-id>`
- **Resolved Date**: `YYYY-MM-DD`

## Completion Criteria

- [ ] Acceptance criteria pass or an approved disposition exists.
- [ ] Resolution evidence is linked.
- [ ] Related task, risk, blocker, and regression records are updated.

## Forbidden Actions

- Do not close an issue without resolution evidence or an approved disposition.
- Do not delete history when status or ownership changes.
- Do not combine unrelated concerns in one issue record.
- Do not fabricate reproduction or verification evidence.

## Output Requirements

- Save as `.agent/governance/issues/ISSUE-<number>.md`.
- Preserve every heading in this template.
- Use repository-relative links and exact enum values.
