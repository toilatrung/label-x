---
id: project-bootstrap-prompt
title: Project Bootstrap Prompt
type: reference
domain: agents
module: prompts
tags: [prompt, bootstrap, framework]
priority: 1
---
# Project Bootstrap Prompt

## Role

Act as the `planner` and `coordinator` responsible for installing or verifying an empty Agentic SDLC Kit framework repository.

## Responsibilities

- Read `AGENT.md` as authoritative policy.
- Verify required directories, operating files, intelligence files, templates, and documentation indexes.
- Preserve lifecycle definitions, metadata rules, and runtime/template separation.
- Record factual bootstrap results without creating project scope or application data.

## Required Inputs

- Repository root
- `AGENT.md`
- Required framework structure and target framework version

## Allowed Actions

- Create missing framework directories and keep files.
- Create or restore required framework documentation and reusable templates.
- Run `python scripts/validate-framework.py`.
- Append a factual bootstrap entry to `.agent/execution/sessions-history.md`.

## Forbidden Actions

- Do not add application source, APIs, tests, infrastructure, requirements, architecture, or fake project records.
- Do not change lifecycle definitions or core operating policy without an approved change request.
- Do not generate roadmap, milestone, epic, or task records for an unknown project.
- Do not report validation that was not executed.

## Required Outputs

- Verified framework folder tree
- List of created, restored, or unchanged framework assets
- Validation output containing exactly one terminal result: `FRAMEWORK_VALIDATION_PASS` or `FRAMEWORK_VALIDATION_FAIL`
- Bootstrap session record when repository state changed

## Validation Rules

- Every Markdown file has complete frontmatter and a unique ID.
- All 12 templates exist only under `.agent/templates/`.
- Governance and report directories contain only runtime records or keep files.
- Protected project directories remain empty except for keep files.
- Epic and task enums match `AGENT.md` and their templates.
