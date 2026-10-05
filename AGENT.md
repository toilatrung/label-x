---
id: agent-driven-sdlc-framework
title: Agent-Driven SDLC Framework
type: reference
domain: agents
module: repository
tags: [agents, governance, sdlc]
priority: 1
---
# Agent-Driven SDLC Framework

## Purpose

Define the authoritative operating policy for task-driven agent work, lifecycle control, governance, reporting, and traceability in this repository.

## Ownership and Access

- **Owner**: repository maintainers
- **Allowed Writers**: repository maintainers and governance agents explicitly authorized to change operating policy
- **Allowed Readers**: all authorized repository users and agents
- **Write Requirement**: policy changes require an approved change request in `.agent/governance/change-requests/`

## Agent Roles

| Role | Responsibility | Authorized Operating Writes |
|---|---|---|
| `coordinator` | Select authorized work, assemble context, and synchronize execution state | `.agent/execution/current-context.md`, `.agent/execution/task-board.md`, `.agent/execution/sessions-history.md` |
| `planner` | Maintain roadmap, milestones, epics, and dependency integrity | `.agent/planning/` |
| `implementer` | Execute authorized tasks and produce implementation evidence | task-scoped files and `.agent/reports/implementation/` |
| `reviewer` | Independently assess artifacts and record findings | `.agent/reports/review/`, issue records when findings require tracking |
| `qa` | Execute quality checks and record release recommendations | `.agent/reports/qa/`, issue and blocker records created from evidence |
| `governance` | Triage governance records and record authorized approvals | `.agent/governance/` |
| `release-manager` | Authorize and record release execution | `.agent/reports/releases/` and release-related execution records |

One agent may hold multiple roles only when repository policy permits it. Approval and independent-review duties must not be self-approved unless an explicit governance record authorizes the exception.

## Context Retrieval Policy

- Context retrieval is task-driven. Select context from the active task's domain, module, parent epic, dependencies, governance links, and required outputs.
- There is no fixed required reading order.
- Treat `AGENT.md` as governing policy, not as the first item in an ordered context bundle.
- Read `.agent/execution/current-context.md` only when shared execution state is relevant to the task.
- Prefer frontmatter lookup by `id`, `title`, `type`, `domain`, `module`, `tags`, and `priority` before broader content search.
- Use the context package template for work requiring an explicit bounded context set.
- Repository-wide scans are allowed only for an explicitly authorized audit, migration, or validation task.

## Metadata Standard

Every Markdown file must begin with YAML frontmatter containing these non-empty fields:

```yaml
---
id: unique-stable-id
title: Human-Readable Title
type: governance | planning | execution | report | intelligence | reference
domain: project-domain
module: owning-module-or-repository
tags: [searchable, labels]
priority: 1
---
```

- `id` must be unique and stable for the life of the document.
- `priority` must be `1 | 2 | 3 | 4 | 5`, where `1` is highest.
- `module` must be a stable module identifier or `repository` when no narrower module applies.
- Headings defined by an operating file or template must be preserved exactly for machine parsing.

## Execution Lifecycle

1. Select an authorized epic or task.
2. Retrieve task-driven context and validate dependencies, governance constraints, and ownership.
3. Set the task to `in-progress` and synchronize current context.
4. Execute only the authorized scope.
5. Produce implementation evidence and required reports.
6. Complete independent review and QA when required.
7. Update governance records, intelligence mappings, and execution state.
8. Set the task to a terminal status only after its completion criteria are satisfied.

## Task Lifecycle

- **Valid Statuses**: `pending | in-progress | blocked | review | done | cancelled`
- `pending -> in-progress` requires an `EPIC_IN_PROGRESS` parent, an owner, and sufficient context.
- `in-progress -> blocked` requires a linked blocker record.
- `in-progress -> review` requires implementation evidence.
- `review -> done` requires acceptance criteria and required review or QA evidence to pass.
- `blocked -> in-progress` requires verified blocker resolution.
- `cancelled` requires an owner-recorded rationale; `done` and `cancelled` are terminal.

## Epic Expansion Rule

- **Valid Statuses**: `EPIC_PROPOSED | EPIC_READY | EPIC_IN_PROGRESS | EPIC_BLOCKED | EPIC_DONE | EPIC_CANCELLED`
- Tasks may be created only when the parent epic is `EPIC_READY`.
- Tasks may enter `in-progress` only when the parent epic is `EPIC_IN_PROGRESS`.
- `EPIC_READY` requires an owner, bounded scope, acceptance criteria, dependencies, and governance links.
- `EPIC_DONE` requires all child tasks to be `done` or formally `cancelled` and all epic completion criteria to pass.

## Governance Rules

- Runtime issues, blockers, change requests, decisions, and risks belong only in their matching `.agent/governance/` directories.
- Reusable governance templates belong only in `.agent/templates/`.
- Governance records must identify owner, status, related work, evidence, and resolution or disposition.
- Approval records are append-only evidence after acceptance; corrections require a superseding record or governed amendment.
- Governance agents resolve conflicting records using approved decisions and change requests, not file timestamps alone.

## Report Rules

- Runtime implementation, review, QA, and release reports belong only in their matching `.agent/reports/` directories.
- Reusable report templates belong only in `.agent/templates/`.
- Reports must identify owner, author or reviewer, scope, status, evidence, findings, and completion outcome.
- Final reports are immutable evidence; corrections require a superseding report that links the prior report.
- A report must not claim evidence outside its declared scope.

## Intelligence Rules

- Code Graph files describe modules, dependencies, API routes, database usage, and functions using repository evidence.
- Git Nexus files map commits to tasks and decisions and record regressions.
- Intelligence artifacts are derived and must link authoritative sources, tasks, governance records, reports, or commits.
- When intelligence conflicts with source or approved governance evidence, the authoritative evidence wins and intelligence must be regenerated or corrected.

## Change Request Rule

- An approved change request is required before changing baselined requirements, contracts, architecture, roadmap commitments, operating policy, or approved scope.
- Only `approved` change requests authorize implementation; `draft`, `proposed`, `under-review`, and `rejected` records do not.
- Implementation must remain within the approved change and must link the change request from affected tasks, reports, and decisions.
- A material deviation requires a new or superseding change request before work continues.

## Update Triggers

Update this file only when an approved policy change modifies roles, lifecycle rules, metadata, governance, reporting, intelligence, context retrieval, or forbidden actions.

## Relationships

- Planning state: `.agent/planning/`
- Execution state: `.agent/execution/`
- Runtime governance: `.agent/governance/`
- Runtime reports: `.agent/reports/`
- Reusable templates: `.agent/templates/`
- Derived intelligence: `.agent/intelligence/`
- Domain documentation: `docs/`

## Conflict Handling

1. Stop the affected state transition or write.
2. Preserve both conflicting sources and record the conflict in an issue or blocker.
3. Apply precedence: approved governance record, authoritative contract or policy, current authorized task, derived report, derived intelligence.
4. Assign a governance owner and resolve through a decision or change request when precedence is insufficient.
5. Update dependent files only after the resolution is recorded.

## Forbidden Actions

- Do not execute work without an authorized task, owner, and sufficient task-driven context.
- Do not use or introduce a fixed required reading order.
- Do not expand an epic or transition a task contrary to the defined lifecycle.
- Do not bypass approvals, self-approve restricted actions, or silently alter governance history.
- Do not store reusable templates in runtime governance or report directories.
- Do not fabricate status, test results, review evidence, report evidence, or commit links.
- Do not expose secrets, credentials, personal data, or restricted information.
- Do not perform destructive or irreversible actions without explicit authorization.
- Do not modify protected source directories during framework-only maintenance.
