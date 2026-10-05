---
id: agentic-sdlc-kit-readme
title: Agentic SDLC Kit
type: reference
domain: project
module: repository
tags: [readme, framework, release]
priority: 1
---
# Agentic SDLC Kit

Agentic SDLC Kit is a repository-native framework for governing agent-assisted software delivery. It provides durable planning truth, explicit lifecycle controls, reusable record templates, task-driven context retrieval, auditable execution, and source-to-decision traceability without prescribing application architecture or business logic.

Version: `v1.0.0`

## Core Concepts

- **Planning Truth**: roadmap, milestones, epics, and dependencies are maintained as authoritative registries.
- **Controlled Execution**: work progresses through explicit epic and task lifecycles defined in `AGENT.md`.
- **Runtime Governance**: issues, blockers, change requests, decisions, and risks are stored as auditable records.
- **Evidence-Based Reports**: implementation, review, QA, and release reports capture outcomes and verification evidence.
- **Reusable Templates**: stable templates enforce predictable metadata, headings, statuses, and completion criteria.
- **Task-Driven Retrieval**: agents retrieve only context justified by the active task, domain, module, dependencies, and governance links.
- **Derived Intelligence**: Code Graph and Git Nexus connect implementation structure and commit history to governed work.

## Folder Structure

```text
.
├── AGENT.md                 # Authoritative operating policy
├── .agent/
│   ├── planning/            # Roadmap, milestones, epics, dependencies
│   ├── execution/           # Current context, task board, session audit
│   ├── governance/          # Runtime governance records only
│   ├── reports/             # Runtime delivery reports only
│   ├── templates/           # Reusable record templates
│   └── intelligence/        # Code Graph and Git Nexus
├── docs/                    # Project and framework documentation
├── scripts/                 # Framework validation tooling
├── src/                     # Reserved for onboarded application source
├── tests/                   # Reserved for onboarded application tests
└── infrastructure/          # Reserved for onboarded deployment assets
```

## Agent Roles

| Role | Primary responsibility |
|---|---|
| `coordinator` | Select authorized work, assemble context, and synchronize execution state. |
| `planner` | Maintain roadmap, milestones, epics, and dependency integrity. |
| `implementer` | Execute authorized tasks and produce implementation evidence. |
| `reviewer` | Independently assess artifacts and record actionable findings. |
| `qa` | Execute quality checks and issue evidence-based release recommendations. |
| `governance` | Triage governance records and record authorized approvals. |
| `release-manager` | Validate readiness and record release execution. |

Detailed authority and separation-of-duty rules remain defined in [AGENT.md](AGENT.md).

## Workflow Overview

1. Bootstrap or validate the framework structure.
2. Onboard authoritative SRS, contract, and architecture inputs.
3. Create the planning hierarchy: Roadmap -> Milestone -> Epic.
4. Keep the roadmap in `ROADMAP_DRAFT` until explicit governance approval.
5. Expand tasks only while the parent epic is `EPIC_READY`.
6. Transition the epic to `EPIC_IN_PROGRESS` before task execution.
7. Execute authorized tasks and produce implementation evidence.
8. Complete independent review and QA as required.
9. Update governance records, reports, Code Graph, Git Nexus, and execution state.
10. Release only after the release manager validates required evidence.

## Context Retrieval Model

Context retrieval is task-driven; there is no fixed required reading order. An agent selects context from:

- the active task and parent epic;
- domain and module metadata;
- dependency edges;
- linked decisions, risks, blockers, and change requests;
- required outputs and verification rules.

Use `.agent/templates/context-package-template.md` when work needs an explicit bounded context bundle. Repository-wide scans are reserved for authorized audits, migrations, and validations.

## Planning Lifecycle

Planning proceeds only through `Roadmap -> Milestone -> Epic -> Task`.

- Roadmaps begin as `ROADMAP_DRAFT` and require explicit approval before activation.
- Milestones group measurable epic outcomes.
- Epics use `EPIC_PROPOSED | EPIC_READY | EPIC_IN_PROGRESS | EPIC_BLOCKED | EPIC_DONE | EPIC_CANCELLED`.
- Tasks use `pending | in-progress | blocked | review | done | cancelled`.
- Tasks are not generated during onboarding and may be expanded only from an `EPIC_READY` epic.

## Governance Model

Runtime records are stored under `.agent/governance/`:

- `issues/` for defects, gaps, and inconsistencies;
- `blockers/` for conditions preventing authorized progress;
- `change-requests/` for governed baseline or scope changes;
- `decisions/` for consequential choices and rationale;
- `risks/` for uncertain events and response plans.

Reusable templates remain in `.agent/templates/`. Baselined requirements, contracts, architecture, roadmap commitments, operating policy, and approved scope require an approved change request before modification.

## Quick Start

1. Clone the kit or follow [the overlay installation guide](docs/00-project/installation.md) for an existing project.
2. Run `python scripts/validate-framework.py`.
3. Read `AGENT.md` as the authoritative operating policy.
4. Use `docs/10-agents/project-bootstrap-prompt.md` to verify the framework installation.
5. Supply the authoritative SRS, contract, and architecture documents.
6. Use `docs/10-agents/project-onboarding-prompt.md` to build the initial Planning Truth.
7. Resolve all input blockers before requesting roadmap approval.
8. Use the remaining prompt pack for roadmap approval, epic expansion, execution, review, QA, and release.

Successful framework validation prints:

```text
FRAMEWORK_VALIDATION_PASS
```

## Project Onboarding Flow

1. Ingest the SRS, contract, and architecture documents without inventing missing content.
2. Add complete frontmatter to every Markdown document.
3. Validate scope, ownership, version, approval state, and cross-document consistency.
4. Create blockers for missing or contradictory inputs.
5. Define only Roadmap -> Milestone -> Epic; do not generate tasks.
6. Mark the roadmap `ROADMAP_DRAFT` unless explicit approval evidence exists.
7. Build dependency edges and link governance records.
8. Synchronize current context and append the onboarding session record.
9. Validate the repository before requesting roadmap approval.

## Validation

Run:

```bash
python scripts/validate-framework.py
```

The validator checks metadata, duplicate IDs, internal links, templates, lifecycle states, folder placement, prompt contracts, and governance/report separation.

## Installation

Install into an existing project without replacing its README, license, package files, source, tests, or infrastructure:

```bash
git clone https://github.com/toilatrung/agentic-sdlc-kit.git
cd agentic-sdlc-kit
./scripts/install-kit.sh /path/to/project
```

```powershell
.\scripts\install-kit.ps1 -TargetProjectPath C:\path\to\existing-project
```

The overlay guide is copied as `AGENTIC-SDLC-KIT.md`, and the kit license is copied as `LICENSE.agentic-sdlc-kit`. Existing overlay destinations are backed up before replacement.

## Contributing and License

The cloned distribution includes `CONTRIBUTING.md`, `CHANGELOG.md`, and the MIT `LICENSE`. Overlay installation deliberately omits the changelog and contribution guide, renames the kit license, and preserves the target project's own root files.
