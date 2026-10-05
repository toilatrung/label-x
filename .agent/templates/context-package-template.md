---
id: context-package-template
title: Context Package Template
type: execution
domain: agents
module: templates
tags: [context, retrieval, template]
priority: 1
---
# Context Package Template

## Usage Purpose

Use this template to provide the minimum authoritative context required to execute one epic or task without repository-wide retrieval.

## Record Metadata

- **Context Package ID**: `CTX-<number>`
- **Title**: `<required>`
- **Owner**: `<required-person-or-agent-id>`
- **Status**: `draft | ready | stale | archived`
- **Target Type**: `epic | task`
- **Target ID**: `<E-number-or-T-number>`
- **Domain**: `<required-domain>`
- **Module**: `<required-module>`
- **Prepared Date**: `YYYY-MM-DD`
- **Validated Date**: `YYYY-MM-DD`

## Required Context

| Path | Purpose | Authority | Required |
|---|---|---|---|
| `<repository-relative-path>` | `<specific-use>` | `source | contract | governance | report | reference` | `yes | no` |

## Related Files

- **Current Context**: `.agent/execution/current-context.md`
- **Epic or Task Record**: `<path-and-anchor>`
- **Decisions**: `<paths-or-none>`
- **Risks**: `<paths-or-none>`
- **Blockers**: `<paths-or-none>`
- **Change Requests**: `<paths-or-none>`

## Governing Constraints

- **Required Approvals**: `<approval-record-paths-or-none>`
- **Security Constraints**: `<specific-constraints-or-none>`
- **Data Constraints**: `<specific-constraints-or-none>`
- **Forbidden Operations**: `<specific-operations-or-none>`

## Current State

- **Implemented State**: `<verified-summary>`
- **Known Gaps**: `<specific-gaps-or-none>`
- **Active Dependencies**: `<ids-or-none>`
- **Active Blockers**: `<ids-or-none>`

## Expected Outputs

| Output | Required Path | Verification |
|---|---|---|
| `<artifact-name>` | `<repository-relative-path>` | `<check-or-evidence>` |

## Completion Criteria

- [ ] Every required path exists and is readable.
- [ ] Content authority and purpose are recorded for every path.
- [ ] Constraints and current state were validated on the recorded date.
- [ ] Expected outputs map to explicit verification evidence.

## Forbidden Actions

- Do not include secrets, credentials, personal data, or unrelated repository content.
- Do not mark status `ready` with missing required context.
- Do not use a `stale` or `archived` package for execution.
- Do not substitute summaries for mandatory contracts or governance records.

## Output Requirements

- Store the completed package at the task- or epic-approved path under `.agent/execution/`.
- Use repository-relative paths only.
- Preserve every heading and table column in this template.
