---
id: release-notes-v1-0-0
title: Agentic SDLC Kit v1.0.0 Release Notes
type: reference
domain: project
module: release
tags: [release-notes, v1.0.0, framework]
priority: 1
---
# Agentic SDLC Kit v1.0.0 Release Notes

## Release Summary

Version `v1.0.0` packages the repository-native Agentic SDLC Kit as a reusable framework for governed, agent-assisted software delivery.

## Architecture

The kit separates durable operating policy, planning truth, execution state, runtime governance, evidence reports, reusable templates, project documentation, and derived intelligence. Application source, tests, scripts, and infrastructure remain explicit project-owned areas.

## Governance

Issues, blockers, change requests, decisions, and risks use dedicated runtime directories and metadata-complete templates. Approved change requests protect baselined requirements, contracts, architecture, roadmap commitments, policy, and approved scope.

## Planning

Planning follows `Roadmap -> Milestone -> Epic -> Task`. Roadmaps begin in `ROADMAP_DRAFT`; tasks are expanded only from `EPIC_READY` epics and execute only under `EPIC_IN_PROGRESS`.

## Execution

Current context, the task board, and append-only session history provide synchronized state and audit evidence. Explicit owners, status transitions, blockers, acceptance criteria, review, and QA control task completion.

## Intelligence

Code Graph tracks modules, dependencies, API routes, database usage, and functions. Git Nexus maps commits to tasks and decisions and records regressions.

## Retrieval

Context retrieval is task-driven with no fixed required reading order. Metadata and context packages bound retrieval to the active domain, module, dependencies, governance constraints, and expected outputs.

## Onboarding

The onboarding workflow ingests authoritative SRS, contract, and architecture inputs, validates metadata and completeness, creates blockers instead of guessing, and builds only the initial Roadmap -> Milestone -> Epic hierarchy.

## Installation

Bash and PowerShell overlay installers copy only framework-owned assets into an existing project. Existing destinations are backed up with the `.backup-agentic-sdlc-kit` suffix, while project README, license, package files, source, tests, and infrastructure remain untouched.

## Validation

Run `python scripts/validate-framework.py`. A releasable framework emits `FRAMEWORK_VALIDATION_PASS`.

## Compatibility

This release requires Python 3.10 or later only for the validation script. The framework documentation and record model remain language- and platform-neutral.
