---
id: implementation-report-template
title: Implementation Report Template
type: report
domain: development
module: templates
tags: [implementation, report, template]
priority: 3
---
# Implementation Report Template

## Usage Purpose

Use this template to provide auditable evidence of work performed by an Executor Agent for one authorized task.

## Record Metadata

- **Report ID**: `TASK-ID`
- **Title**: `<required>`
- **Owner**: `<required-person-or-agent-id>`
- **Executor**: `<executor-id>`
- **Status**: `draft | complete | blocked | superseded`
- **Task ID**: `TASK-ID`
- **Epic ID**: `E-<number>`
- **Report Date**: `YYYY-MM-DD`

## Scope

- **Implemented**: `<specific-deliverables>`
- **Not Implemented**: `<excluded-or-deferred-items-or-none>`

## Changes Made

| File or Artifact | Change Summary | Task ID |
|---|---|---|
| `<repository-relative-path>` | `<specific-change>` | `T-<number>` |

## Related Files

- **Task Records**: `<paths-and-anchors>`
- **Context Packages**: `<paths>`
- **Task Board**: `.agent/execution/task-board.md`
- **Current Context**: `.agent/execution/current-context.md`
- **Decisions**: `<paths-or-none>`
- **Change Requests**: `<paths-or-none>`
- **Risks or Blockers**: `<paths-or-none>`
- **Review Request**: `<reviewer-id-or-pending>`
- **Commits**: `<hashes-or-none-with-reason>`

## Command Evidence

| Command | Result | Evidence |
|---|---|---|
| `agent task start TASK-ID` | `passed | failed | not-run` | `<output-or-path>` |
| `agent task verify TASK-ID` | `passed | failed | not-run` | `<output-or-path>` |
| `agent task report TASK-ID --executor <executor-id>` | `passed | failed | not-run` | `<output-or-path>` |
| `agent review request TASK-ID --reviewer <reviewer-id>` | `passed | failed | not-run` | `<output-or-path>` |

## Verification Evidence

| Check | Result | Evidence |
|---|---|---|
| `<command-or-review>` | `passed | failed | not-run` | `<output-or-path>` |

## Deviations

- **Plan Deviations**: `<deviations-or-none>`
- **Approved By**: `<approval-path-or-not-applicable>`
- **Known Limitations**: `<limitations-or-none>`

## Completion Criteria

- [ ] Every reported change maps to an authorized task.
- [ ] Acceptance criteria results and evidence are linked.
- [ ] Deviations and limitations are explicit.
- [ ] Build, lint, and test checks are recorded or explicitly marked not-run with rationale.
- [ ] Reviewer handoff identifies an independent Reviewer Agent.
- [ ] Git Nexus mappings are updated when commits exist.

## Forbidden Actions

- Do not report unperformed work as implemented.
- Do not omit failed or unexecuted required checks.
- Do not claim completion with unmet task acceptance criteria.
- Do not claim review approval or move the task to `DONE`.
- Do not change roadmap or acceptance criteria.
- Do not use this report as a substitute for independent review.
- Do not include secrets or sensitive command output.

## Output Requirements

- Save as `.agent/reports/implementation/TASK-ID.md`.
- Preserve every heading and table column in this template.
- Set status `complete` only after completion criteria pass.
