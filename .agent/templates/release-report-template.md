---
id: release-report-template
title: Release Report Template
type: report
domain: releases
module: templates
tags: [release, report, template]
priority: 2
---
# Release Report Template

## Usage Purpose

Use this template to authorize, trace, and record one release and its deployment outcome.

## Record Metadata

- **Report ID**: `REL-<number>`
- **Release Version**: `<semantic-version-or-project-version>`
- **Title**: `<required>`
- **Owner**: `<required-person-or-agent-id>`
- **Release Manager**: `<required-person-or-agent-id>`
- **Status**: `planned | ready | approved | deploying | deployed | failed | rolled-back | cancelled | superseded`
- **Target Environment**: `<environment-name-or-id>`
- **Planned Date**: `YYYY-MM-DD`
- **Actual Date**: `YYYY-MM-DD | pending`

## Release Scope

- **Included Epics or Tasks**: `<ids>`
- **Included Commits**: `<hashes-or-range>`
- **Included Artifacts**: `<artifact-identifiers>`
- **Excluded or Deferred Items**: `<items-or-none>`

## Related Files

- **Implementation Reports**: `<paths>`
- **Review Reports**: `<paths>`
- **QA Reports**: `<paths>`
- **Change Requests**: `<paths-or-none>`
- **Decisions**: `<paths-or-none>`
- **Risks and Known Issues**: `<paths-or-none>`

## Readiness Checks

- [ ] Required implementation reports are complete.
- [ ] Required reviews are approved.
- [ ] QA recommendation is `go` or authorized `conditional-go`.
- [ ] Deployment and rollback procedures are verified.
- [ ] Required approvals are recorded.

## Deployment Plan

- **Procedure Path**: `<path>`
- **Responsible Owner**: `<person-or-agent-id>`
- **Start Criteria**: `<observable-criteria>`
- **Success Criteria**: `<observable-criteria>`
- **Monitoring Window**: `<duration>`

## Rollback Plan

- **Trigger Criteria**: `<observable-thresholds>`
- **Procedure Path**: `<path>`
- **Responsible Owner**: `<person-or-agent-id>`
- **Recovery Verification**: `<checks>`

## Deployment Outcome

- **Outcome**: `pending | succeeded | failed | rolled-back`
- **Evidence**: `<deployment-logs-dashboards-or-artifacts>`
- **Incidents or Regressions**: `<ids-or-none>`
- **Post-Release Verification**: `<checks-and-results>`

## Completion Criteria

- [ ] Deployment outcome and evidence are recorded.
- [ ] Post-release verification meets success criteria or rollback completed successfully.
- [ ] Regressions are recorded in `.agent/intelligence/git-nexus/regression-log.md`.
- [ ] Release status matches the deployment outcome.

## Forbidden Actions

- Do not deploy without required approvals and readiness evidence.
- Do not alter release scope after approval without governed authorization.
- Do not mark status `deployed` before post-release verification.
- Do not suppress failed deployment, rollback, incident, or regression evidence.

## Output Requirements

- Save as `.agent/reports/releases/REL-<number>.md`.
- Preserve every heading in this template.
- Use repository-relative links and exact enum values.
