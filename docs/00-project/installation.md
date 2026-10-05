---
id: agentic-sdlc-kit-installation
title: Installing Agentic SDLC Kit
type: reference
domain: project
module: installation
tags: [installation, overlay, upgrade]
priority: 1
---
# Installing Agentic SDLC Kit

## Purpose

Install the kit as a framework overlay without replacing the target project's identity, application code, tests, package configuration, or infrastructure.

## Prerequisites

- A cloned Agentic SDLC Kit repository
- An existing target project directory
- Bash for `install-kit.sh` or PowerShell 7/Windows PowerShell for `install-kit.ps1`
- Python 3.10 or later for post-install validation

## Install from a Cloned Kit

Clone or download the kit, then run an installer from the kit root.

### Bash

```bash
chmod +x scripts/install-kit.sh
./scripts/install-kit.sh /absolute/path/to/target-project
```

### PowerShell

```powershell
.\scripts\install-kit.ps1 -TargetProjectPath C:\absolute\path\to\target-project
```

The target must already exist and must not be the cloned kit directory.

To intentionally replace existing target runtime state, pass the explicit runtime reset flag:

```bash
./scripts/install-kit.sh /absolute/path/to/target-project --reset-runtime
```

```powershell
.\scripts\install-kit.ps1 -TargetProjectPath C:\absolute\path\to\target-project -ResetRuntime
```

## Install into an Existing Project

The installer performs a clean overlay operation:

1. Validate the source and target paths.
2. Back up every existing overlay destination before copying.
3. Copy reusable framework assets only: `AGENT.md`, `docs/`, `.agent/templates/`, `scripts/validate-framework.py`, the renamed distribution guide, and the kit license.
4. Initialize clean runtime state for the target project under `.agent/execution/`, `.agent/planning/`, and `.agent/intelligence/`.
5. Create `.keep` files for runtime report and governance directories without copying any runtime records from the kit repository.
6. Leave project-owned files and directories outside the overlay untouched.
7. Run `python scripts/validate-framework.py` when a Python command is available.
8. Print copied, backed-up, skipped, and validation results.

The validator automatically detects overlay mode through `AGENTIC-SDLC-KIT.md`. In overlay mode, it validates kit-owned Markdown only; unrelated project Markdown is not required to adopt kit frontmatter.

The installer does not copy runtime reports, runtime governance records, task-board state, current-context state, planning state, or intelligence state from the cloned kit repository. Those files are initialized fresh for the target project. If matching runtime files already exist in the target, the installer preserves them by default and records them as skipped. Use `--reset-runtime` for Bash or `-ResetRuntime` for PowerShell only when replacing target runtime state is intentional.

## Backup Behavior

Before replacing an existing destination, the installer creates a sibling backup using:

```text
<original-path>.backup-agentic-sdlc-kit
```

If that backup already exists, the installer appends `.1`, `.2`, and so on. Backups are copied snapshots; the target remains available while the overlay is applied.

Directory backups cover copied reusable directories such as `.agent/templates/` and `docs/`. File backups cover `AGENT.md`, `scripts/validate-framework.py`, `AGENTIC-SDLC-KIT.md`, `LICENSE.agentic-sdlc-kit`, and runtime files only when `--reset-runtime` or `-ResetRuntime` is used.

## Files Copied

| Kit source | Target destination |
|---|---|
| `AGENT.md` | `AGENT.md` |
| `.agent/templates/` | `.agent/templates/` |
| `docs/` | `docs/` |
| `scripts/validate-framework.py` | `scripts/validate-framework.py` |
| `LICENSE` | `LICENSE.agentic-sdlc-kit` |
| `README.md` | `AGENTIC-SDLC-KIT.md` |

## Runtime Initialized

The installer creates clean target-project runtime files when they do not already exist:

- `.agent/execution/current-context.md`
- `.agent/execution/sessions-history.md`
- `.agent/execution/task-board.md`
- `.agent/planning/roadmap.md`
- `.agent/planning/milestones.md`
- `.agent/planning/epics.md`
- `.agent/planning/dependency-graph.md`
- `.agent/intelligence/code-graph/modules.md`
- `.agent/intelligence/code-graph/dependencies.md`
- `.agent/intelligence/code-graph/api-routes.md`
- `.agent/intelligence/code-graph/database-usage.md`
- `.agent/intelligence/code-graph/function-map.md`
- `.agent/intelligence/git-nexus/commit-map.md`
- `.agent/intelligence/git-nexus/task-commit-map.md`
- `.agent/intelligence/git-nexus/decision-commit-map.md`
- `.agent/intelligence/git-nexus/regression-log.md`

The installer creates only `.keep` files in these runtime directories:

- `.agent/reports/implementation/.keep`
- `.agent/reports/review/.keep`
- `.agent/reports/qa/.keep`
- `.agent/reports/releases/.keep`
- `.agent/governance/issues/.keep`
- `.agent/governance/blockers/.keep`
- `.agent/governance/change-requests/.keep`
- `.agent/governance/decisions/.keep`
- `.agent/governance/risks/.keep`

## Files Never Copied

- `src/`
- `tests/`
- `infrastructure/`
- `CHANGELOG.md`
- `CONTRIBUTING.md`
- Root `README.md` as `README.md`
- Root `LICENSE` as `LICENSE`
- Package manifests, lock files, build configuration, and application-specific scripts
- `.agent/reports/**/*.md`
- `.agent/governance/**/*.md`
- `.agent/execution/current-context.md` from the kit repository
- `.agent/execution/task-board.md` from the kit repository
- `.agent/planning/*.md` from the kit repository

## Validation

When Python is available, the installer runs:

```bash
python scripts/validate-framework.py
```

Expected success output:

```text
FRAMEWORK_VALIDATION_PASS
```

If no Python command is available, installation completes with `VALIDATION_SKIPPED_PYTHON_NOT_AVAILABLE`. Run the validator manually after installing Python 3.10 or later.

## Uninstall Notes

There is intentionally no destructive automatic uninstaller.

1. Preserve any runtime records created after installation.
2. Compare active overlay files with the installer's copied-file output.
3. For destinations that had backups, move the active destination aside and restore the corresponding `.backup-agentic-sdlc-kit` snapshot.
4. For destinations without backups, remove only files listed as copied by the installer.
5. Remove `AGENTIC-SDLC-KIT.md` and `LICENSE.agentic-sdlc-kit` only if the target project did not adopt them.
6. Re-run project-native checks after restoration.

Do not recursively delete `.agent/`, `docs/`, or `scripts/` without reviewing project-owned and post-install content.

## Upgrade Notes

Run the newer kit's installer against the same target project. The installer creates a new backup before applying the upgraded overlay; existing backup names are never overwritten.

Before accepting an upgrade:

- review changes to `AGENT.md`, templates, prompts, and validator behavior;
- preserve runtime governance and report records created by the target project;
- use a governed change request for operating-policy or lifecycle changes;
- run framework validation after installation;
- run the target project's native build, test, and security checks.

An upgrade must not silently resolve governance records, rewrite final reports, or change project source and identity files.
