---
id: qa-report-template
title: QA Report Template
type: report
domain: testing
module: templates
tags: [qa, testing, report, template]
priority: 3
---
# QA Report Template

## Usage Purpose

Use this template to record QA Agent checks, results, defects, and completion recommendation after independent review approval.

## Record Metadata

- **Report ID**: `TASK-ID`
- **Title**: `<required>`
- **Owner**: `<required-person-or-agent-id>`
- **Tester**: `<required-person-or-agent-id>`
- **Status**: `draft | passed | failed | blocked | superseded`
- **Task ID**: `TASK-ID`
- **Review Decision**: `APPROVED`
- **Test Date**: `YYYY-MM-DD`
- **Environment ID**: `<environment-name-or-id>`

## Test Scope

- **Features or Requirements**: `<ids-or-descriptions>`
- **Included Test Levels**: `unit | integration | contract | end-to-end | security | performance | manual`
- **Behavior Checks**: `<checks-or-none>`
- **Edge Cases**: `<checks-or-none>`
- **Regression Checklist**: `<path-or-inline-checklist>`
- **Excluded Checks**: `<checks-and-reasons-or-none>`

## Related Files

- **Test Plan or Strategy**: `<paths>`
- **Implementation Report**: `.agent/reports/implementation/TASK-ID.md`
- **Review Report**: `.agent/reports/review/TASK-ID.md`
- **Task Board**: `.agent/execution/task-board.md`
- **Current Context**: `.agent/execution/current-context.md`
- **Issues or Risks**: `<paths-or-none>`
- **Build or Commit**: `<identifier>`

## Command Evidence

| Command | Result | Evidence |
|---|---|---|
| `agent qa start TASK-ID` | `passed | failed | not-run` | `<output-or-path>` |
| `agent qa pass TASK-ID` | `passed | failed | not-run` | `<output-or-path>` |
| `agent qa fail TASK-ID` | `passed | failed | not-run` | `<output-or-path>` |

## Test Results

| Check ID | Test Level | Result | Evidence | Defect ID |
|---|---|---|---|---|
| `CHECK-<number>` | `<enum-value>` | `passed | failed | blocked | skipped` | `<path-or-output>` | `<issue-id-or-none>` |

## Result Summary

- **Total**: `<integer>`
- **Passed**: `<integer>`
- **Failed**: `<integer>`
- **Blocked**: `<integer>`
- **Skipped**: `<integer>`

## Defects and Risks

- **Open Defects**: `<issue-ids-or-none>`
- **Residual Risks**: `<risk-ids-or-none>`
- **Blocking Conditions**: `<blocker-ids-or-none>`

## Acceptance Criteria

- [ ] Review report records `APPROVED` before QA starts.
- [ ] Every required check has a result and evidence.
- [ ] Result totals reconcile with the results table.
- [ ] Failed checks map to issue records.
- [ ] Skipped checks include an explicit approved reason.
- [ ] Behavior, edge cases, regression checklist, and manual verification are recorded when applicable.

## Release Recommendation

- **Recommendation**: `go | conditional-go | no-go`
- **Conditions**: `<required-for-conditional-go-or-none>`
- **Rationale**: `<required>`
- **Authorized By**: `<person-or-role-id>`

## Completion Criteria

- [ ] Required tests are executed or formally waived.
- [ ] Defects, blockers, and residual risks are linked.
- [ ] Release recommendation matches recorded results.

## Forbidden Actions

- Do not start QA before independent review is `APPROVED`.
- Do not mark status `passed` with unresolved required failures.
- Do not omit, relabel, or discard failed results.
- Do not count unexecuted checks as passed.
- Do not replace independent review with QA.
- Do not change roadmap or acceptance criteria.
- Do not expose secrets or production personal data in evidence.

## Output Requirements

- Save as `.agent/reports/qa/TASK-ID.md`.
- Preserve every heading and table column in this template.
- Use exact enum values and non-negative integer totals.
