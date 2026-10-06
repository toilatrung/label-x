---
id: blocker-014
title: Phần cứng, ngưỡng NFR, retry, retention/GC, RPO/RTO chưa chốt
type: governance
domain: governance
module: blockers
tags: [blocker, decision, m13]
priority: 2
---
# BLOCKER-014: Phần cứng, ngưỡng NFR, retry, retention/GC, RPO/RTO chưa chốt

## Record Metadata

- **Blocker ID**: `BLOCKER-014`
- **Title**: `Phần cứng, ngưỡng NFR, retry, retention/GC, RPO/RTO chưa chốt`
- **Owner**: `unassigned (vai trò chốt: Tech Lead Backend)`
- **Reporter**: `claude-code (planner), đồng thuận với codex`
- **Status**: `open`
- **Blocker Type**: `decision`
- **Priority**: `2`
- **Created Date**: `2026-10-05`
- **Target Resolution Date**: `not-set`

## Blocking Condition

TBD-02, 13, 14, 15, 17, 20 còn mở; compose hiện tại chỉ là dev; frontend chưa có test runner.

Bằng chứng: docs/label-x_system-requirement-specification/sections/11-traceability.tex; docs/label-x_system-requirement-specification/sections/08-nonfunctional.tex; .agent/governance/decisions/DEC-001.md.

## Impact

- **Blocked Epics or Tasks**: `E-02, E-08, E-10, E-23`
- **Blocked Deliverables**: phần nghiệm thu liên quan của các epic trên
- **Schedule or Quality Impact**: chặn chuyển `EPIC_READY` hoặc cổng nghiệm thu tương ứng cho tới khi được giải quyết

## Related Files

- **Affected Records**: `.agent/planning/epics.md`
- **Issues**: `none`
- **Decisions**: `.agent/governance/decisions/DEC-002.md`
- **Risks**: `none`
- **Change Requests**: `none`

## Resolution Plan

- **Required Action**: Tech Lead chốt TBD-02 và test runner frontend ngay (trước E-02/M-02); TBD-13, 14 sau đo pilot; Product Owner chốt retention TBD-15, 17, 20 trước triển khai.
- **Responsible Owner**: `unassigned (vai trò: Tech Lead Backend)`
- **Dependency or Approval**: `Tech Lead Backend`
- **Workaround**: `none`
- **Verification Method**: Quyết định/bằng chứng được ghi thành decision record hoặc cập nhật SRS có version, liên kết vào đây.

## Resolution Record

- **Resolved Date**: `pending`
- **Evidence**: `.agent/governance/decisions/DEC-002.md` — phiếu chốt của Product Owner ngày 2026-10-06.
- **Note**: Phương án A đã chọn: chốt ngay phần cứng tối thiểu (TBD-02: app server, GPU server) trước M-02 và test runner frontend trong E-02; TBD-13, 14 chốt sau đo pilot; TBD-15, 17, 20 chốt trước triển khai. Blocker còn mở tới khi TBD-02 và test runner frontend được ghi nhận.

## Completion Criteria

- [ ] The blocking condition no longer prevents affected work.
- [ ] Resolution evidence is linked.
- [ ] Affected epic and task statuses are updated.
- [ ] Workaround removal is tracked when applicable.

## Forbidden Actions

- Do not mark status `resolved` based only on a proposed action.
- Do not continue blocked work through an unauthorized workaround.
- Do not omit affected epic or task links.
- Do not fabricate resolution evidence.

## Output Requirements

- Save as `.agent/governance/blockers/BLOCKER-<number>.md`.
- Preserve every heading in this template.
- Use repository-relative links and exact enum values.
