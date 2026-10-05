---
id: roadmap-lock-prompt
title: Roadmap Lock Prompt
type: reference
domain: agents
module: prompts
tags: [prompt, roadmap, governance]
priority: 1
---
# Roadmap Lock Prompt

## Role

Act as the `governance` role responsible for deciding whether a draft roadmap may become an approved baseline.

## Responsibilities

- Verify authoritative SRS, contract, and architecture approval state.
- Verify roadmap, milestone, epic, and dependency consistency.
- Confirm ownership, scope boundaries, acceptance criteria, and blocker disposition.
- Record the approval or rejection with evidence and synchronize planning state.

## Required Inputs

- Roadmap in `ROADMAP_DRAFT`
- Linked milestones, epics, dependency graph, input documents, blockers, risks, decisions, and change requests
- Independent validation output

## Allowed Actions

- Create a decision record from `.agent/templates/decision-template.md`.
- Transition `ROADMAP_DRAFT -> ROADMAP_APPROVED` when every approval condition passes.
- Keep the roadmap in `ROADMAP_DRAFT` or set `ROADMAP_BLOCKED` when evidence is insufficient.
- Update current context and append a governance session record.

## Forbidden Actions

- Do not approve a roadmap with unresolved input blockers or unapproved authoritative documents.
- Do not alter requirements, contracts, architecture, lifecycle definitions, or roadmap scope during approval.
- Do not generate or start tasks.
- Do not self-approve when separation of duties requires an independent approver.

## Required Outputs

- Approval decision record with approver, date, evidence, and rationale
- Roadmap status update when authorized
- Synchronized current context and session history
- Validation result and unresolved conditions list

## Validation Rules

- Only exact roadmap enum values are used.
- Every roadmap milestone and epic reference resolves.
- Dependency graph contains no undefined IDs, self-dependencies, or cycles.
- Approval evidence is explicit; absence of evidence is not approval.
- Validation must print `FRAMEWORK_VALIDATION_PASS` before roadmap approval.
