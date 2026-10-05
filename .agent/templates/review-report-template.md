---
id: review-report-template
title: Review Report Template
type: report
domain: quality
module: templates
tags: [review, report, template]
priority: 3
---
# Review Report Template

## Usage Purpose

Use this template to record an independent Reviewer Agent assessment of an Executor Agent implementation.

## Record Metadata

- **Report ID**: `TASK-ID`
- **Title**: `<required>`
- **Owner**: `<required-person-or-agent-id>`
- **Reviewer**: `<required-person-or-agent-id>`
- **Executor**: `<executor-id>`
- **Status**: `draft | changes-requested | approved | blocked | superseded`
- **Decision**: `APPROVED | CHANGES_REQUESTED | BLOCKED`
- **Review Type**: `code | architecture | documentation | security | performance | governance | release`
- **Task ID**: `TASK-ID`
- **Report Date**: `YYYY-MM-DD`

## Review Scope

- **Included Artifacts**: `<paths-or-commit-range>`
- **Code Diff**: `<path-or-commit-range>`
- **Excluded Artifacts**: `<paths-or-none>`
- **Review Standard**: `<criteria-checklist-or-policy-path>`

## Related Files

- **Implementation Report**: `.agent/reports/implementation/TASK-ID.md`
- **Task or Epic Records**: `<paths-and-anchors>`
- **Task Board**: `.agent/execution/task-board.md`
- **Current Context**: `.agent/execution/current-context.md`
- **Decisions**: `<paths-or-none>`
- **Risks or Issues**: `<paths-or-none>`
- **Verification Evidence**: `<paths-or-none>`

## Command Evidence

| Command | Result | Evidence |
|---|---|---|
| `agent review start TASK-ID` | `passed | failed | not-run` | `<output-or-path>` |
| `agent review approve TASK-ID` | `passed | failed | not-run` | `<output-or-path>` |
| `agent review request-changes TASK-ID` | `passed | failed | not-run` | `<output-or-path>` |
| `agent review block TASK-ID` | `passed | failed | not-run` | `<output-or-path>` |

## Required Review Checks

| Check | Result | Evidence |
|---|---|---|
| Code diff | `passed | failed | blocked | not-run` | `<evidence>` |
| Acceptance criteria | `passed | failed | blocked | not-run` | `<evidence>` |
| Architecture compliance | `passed | failed | blocked | not-run` | `<evidence>` |
| Security | `passed | failed | blocked | not-run` | `<evidence>` |
| Performance | `passed | failed | blocked | not-run` | `<evidence>` |
| Regression risk | `passed | failed | blocked | not-run` | `<evidence>` |
| Test/lint/build evidence | `passed | failed | blocked | not-run` | `<evidence>` |

## Findings

| Finding ID | Severity | Artifact | Finding | Required Action | Owner |
|---|---|---|---|---|---|
| `F-<number>` | `critical | major | minor | observation` | `<path>` | `<specific-finding>` | `<action-or-none>` | `<person-or-agent-id>` |

## Acceptance Criteria

- [ ] Review scope and standard are explicit.
- [ ] Each finding identifies evidence, severity, action, and owner.
- [ ] Critical and major findings are resolved or formally accepted.
- [ ] Approval outcome matches unresolved findings.
- [ ] Code diff, acceptance criteria, architecture, security, performance, regression risk, and test/lint/build evidence are checked.
- [ ] Reviewer identity is independent from Executor identity.

## Approval Outcome

- **Decision**: `APPROVED | CHANGES_REQUESTED | BLOCKED`
- **Rationale**: `<required>`
- **Approved By**: `<reviewer-or-authorized-role>`
- **Decision Date**: `YYYY-MM-DD`
- **Follow-up Tasks**: `<task-ids-or-none>`

## Completion Criteria

- [ ] All required actions are linked to tasks or verified as resolved.
- [ ] Approval outcome and rationale are recorded.
- [ ] Related issue, risk, and report records are updated.

## Forbidden Actions

- Do not approve artifacts with unresolved critical findings.
- Do not remove findings after remediation; record their resolution.
- Do not assign ambiguous severity or ownership.
- Do not claim review coverage outside the declared scope.
- Do not act as the Executor Agent for the same task.
- Do not move a task to `DONE`; QA must run after `APPROVED`.
- Do not change roadmap or acceptance criteria.

## Output Requirements

- Save as `.agent/reports/review/TASK-ID.md`.
- Preserve every heading and table column in this template.
- Use repository-relative links and exact enum values.
