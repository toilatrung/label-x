---
id: agents-overview
title: Agents
type: reference
domain: agents
module: repository
tags: [agents, coordination, tools]
priority: 2
---
# Agents

## Purpose

Index reusable role prompts and agent coordination documentation for the framework lifecycle.

## Standard Agent Workflow

The standard task workflow is:

`Orchestrator -> Executor Agent -> Implementation Report -> Reviewer Agent -> QA Agent -> DONE`

The Executor Agent and Reviewer Agent are separate roles:

- `Executor Agent != Reviewer Agent`
- Codex Extension and Claude Code are executor adapters.
- Codex CLI and Claude CLI are reviewer adapters.

The required handoff files are:

- Implementation report: `.agent/reports/implementation/TASK-ID.md`
- Review report: `.agent/reports/review/TASK-ID.md`
- QA report: `.agent/reports/qa/TASK-ID.md`
- Task board: `.agent/execution/task-board.md`
- Current context: `.agent/execution/current-context.md`

The task lifecycle for this workflow is:

`BACKLOG -> READY -> IN_PROGRESS -> IMPLEMENTED -> REVIEWING -> APPROVED -> DONE`

If the reviewer requires fixes, the task transitions `CHANGES_REQUESTED -> IN_PROGRESS`. If work cannot continue, the task transitions to `BLOCKED`.

## Command Contract

Executor flow:

```bash
agent task start TASK-ID
agent task verify TASK-ID
agent task report TASK-ID --executor <executor-id>
agent review request TASK-ID --reviewer <reviewer-id>
```

Reviewer flow:

```bash
agent review start TASK-ID
agent review approve TASK-ID
agent review request-changes TASK-ID
agent review block TASK-ID
```

QA flow:

```bash
agent qa start TASK-ID
agent qa pass TASK-ID
agent qa fail TASK-ID
```

## Prompt Pack

- `project-bootstrap-prompt.md` - Verify or restore the framework structure
- `project-onboarding-prompt.md` - Ingest authoritative inputs and create initial Planning Truth
- `roadmap-lock-prompt.md` - Govern draft-roadmap approval
- `epic-expansion-prompt.md` - Expand one `EPIC_READY` epic into tasks
- `executor-prompt.md` - Execute one authorized task
- `reviewer-prompt.md` - Perform independent review
- `qa-prompt.md` - Execute QA and issue a release recommendation
- `release-manager-prompt.md` - Validate and record release execution

## Related Documentation

- `AGENT.md` - Authoritative agent roles, permissions, and lifecycle rules
- `.agent/templates/` - Reusable governance, execution, and report templates
