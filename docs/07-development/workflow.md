---
id: development-workflow
title: Quy trình phát triển LabelX
type: reference
domain: development
module: repository
tags: [development, workflow, agentic-sdlc-kit, review, git]
priority: 2
---
# Quy trình phát triển LabelX

## Mục đích

Mô tả quy trình làm việc trong repo theo **agentic-sdlc-kit**. Quy tắc gốc nằm ở `AGENT.md` (chính sách có hiệu lực) và [../10-agents/index.md](../10-agents/index.md) (luồng agent, prompt pack). Tài liệu này chỉ tóm tắt và chỉ ghi những gì có căn cứ trong repo. Khi có mâu thuẫn, `AGENT.md` thắng.

## 1. Nguyên tắc

- Chỉ làm việc khi có **task được duyệt**, có owner và đủ ngữ cảnh (`AGENT.md`, Forbidden Actions; `CLAUDE.md`).
- Ghi decision, blocker, issue, change request, risk vào `.agent/governance/` đúng thư mục; ghi report vào `.agent/reports/` (`AGENT.md`, Governance Rules, Report Rules).
- Muốn đổi requirement, hợp đồng, kiến trúc, roadmap hay stack đã chốt thì phải có **change request `approved`** trong `.agent/governance/change-requests/` (`AGENT.md`, Change Request Rule). Stack hiện chốt ở `.agent/governance/decisions/DEC-001.md`.
- Không bịa trạng thái, kết quả test, bằng chứng review hay link commit (`AGENT.md`, Forbidden Actions).

## 2. Epic và task

Nguồn: `AGENT.md` (Epic Expansion Rule, Task Lifecycle); `.agent/planning/epics.md`; `.agent/execution/task-board.md`.

- **Epic**: `EPIC_PROPOSED → EPIC_READY → EPIC_IN_PROGRESS → EPIC_DONE` (hoặc `EPIC_BLOCKED`, `EPIC_CANCELLED`). Chỉ tạo task khi epic ở `EPIC_READY`. `EPIC_READY` cần owner, scope có giới hạn, tiêu chí nghiệm thu, phụ thuộc và link governance.
- **Task**: `pending → in-progress → review → done` (thêm `blocked`, `cancelled`). Task chỉ vào `in-progress` khi epic cha ở `EPIC_IN_PROGRESS`. Vào `blocked` phải có blocker record. Vào `review` phải có bằng chứng triển khai.
- Hiện trạng: task board **chưa có task nào** ("No task records are registered").
- Mẫu dùng lại nằm ở `.agent/templates/` (epic, task, context package, issue, blocker, change request, decision, risk và bốn loại report).

## 3. Luồng executor → reviewer → QA

Nguồn: [../10-agents/index.md](../10-agents/index.md), `docs/10-agents/executor-prompt.md`, `docs/10-agents/reviewer-prompt.md`, `docs/10-agents/qa-prompt.md`.

```text
Orchestrator -> Executor Agent -> Implementation Report -> Reviewer Agent -> QA Agent -> DONE
```

| Vai trò | Adapter theo `docs/10-agents` | Đầu ra |
|---|---|---|
| Executor | Codex Extension, Claude Code | Mã trong scope task + `.agent/reports/implementation/TASK-ID.md` |
| Reviewer (độc lập, **khác** executor) | **Codex CLI**, Claude CLI | `.agent/reports/review/TASK-ID.md`; kết luận đúng một trong `APPROVED`, `CHANGES_REQUESTED`, `BLOCKED` |
| QA | QA agent | `.agent/reports/qa/TASK-ID.md` |

- Executor không tự review và không tự duyệt (`AGENT.md`, Agent Roles; [../10-agents/index.md](../10-agents/index.md): `Executor Agent != Reviewer Agent`).
- Reviewer kiểm: truy vết tới task/epic/decision, diff, tiêu chí nghiệm thu, tuân thủ kiến trúc, ảnh hưởng bảo mật/hiệu năng, rủi ro regression, bằng chứng build/lint/test (`reviewer-prompt.md`).
- Với LabelX, reviewer kiểm thêm các ranh giới cứng trong [coding-standards.md](coding-standards.md) mục 4 (adapter chỉ đọc, task idempotent, quyền ở API, UI theo Design System).
- Đồng bộ trạng thái ở `.agent/execution/task-board.md` và `.agent/execution/current-context.md`.
- Report cuối là bằng chứng bất biến; muốn sửa thì tạo report mới thay thế, có link tới report cũ (`AGENT.md`, Report Rules).

### Khác biệt cần biết

- `docs/10-agents/index.md` dùng bộ trạng thái `BACKLOG → READY → IN_PROGRESS → IMPLEMENTED → REVIEWING → APPROVED → DONE` (thêm `CHANGES_REQUESTED`, `BLOCKED`). `AGENT.md` và `task-board.md` dùng `pending | in-progress | blocked | review | done | cancelled`. Task board chỉ nhận bộ của `AGENT.md`; coi bộ của `docs/10-agents` là các bước luồng làm việc, không phải giá trị trạng thái. Việc thống nhất hai bộ **chưa có** decision.
- "Command Contract" trong `docs/10-agents/index.md` (`agent task start`, `agent review request`…) mô tả hợp đồng lệnh. Repo **chưa có** CLI `agent` hiện thực các lệnh này. Hiện chỉ cập nhật file trong `.agent/` thủ công.

## 4. Kiểm tra trước khi báo xong

- Chạy `make check` (lint + typecheck + test + validate-kit); cần `make infra-up` trước vì pytest dùng PostgreSQL (`CLAUDE.md`, `scripts/init-develop-environment.mk`).
- Sửa `.agent/` hoặc `docs/` thì chạy `make validate-kit` (`CLAUDE.md`).
- Đổi API backend thì chạy `make gen-api` để sinh lại type frontend (cần `make dev-backend`).
- Ghi kết quả các lệnh này làm bằng chứng trong implementation report. Không ghi "đã pass" nếu chưa chạy.

## 5. Git, branch và PR

Căn cứ hiện có trong repo:

- `scripts/init-develop-environment.mk` mô tả `make check` là "toàn bộ kiểm tra trước khi tạo PR", tức là đã dự kiến quy trình PR.
- `.gitignore` loại `.env`, `.env.*` (trừ `.env.example`), `.venv/`, `node_modules/`, `.next/`, file build LaTeX và backup của installer kit.
- `.agent/intelligence/git-nexus/` có các file ánh xạ commit ↔ task/decision (`task-commit-map.md`, `decision-commit-map.md`, `commit-map.md`, `regression-log.md`). DEC-001 còn tiêu chí chưa xong: "Accepted decisions are mapped in `decision-commit-map.md` when implemented".
- `src/frontend/AGENTS.md`: khối quy tắc Next.js do `next dev` tự sinh; commit nó cùng thay đổi để giữ working tree sạch.

**Chưa có căn cứ** (chưa được quyết định trong repo; cần decision trước khi áp dụng):

- Quy ước đặt tên branch, chiến lược merge (merge/squash/rebase), branch được bảo vệ.
- Mẫu PR, số người duyệt PR bắt buộc, quy ước commit message.
- Repo remote và nền tảng host (GitHub/GitLab…). Bản làm việc hiện tại không có thư mục `.git`.

Đề xuất (cần decision): mỗi branch/PR gắn một `TASK-ID`, mô tả PR link tới implementation report và review report trong `.agent/reports/`, và chỉ merge khi review report là `APPROVED` và `make check` pass.

## Liên quan

- [tooling.md](tooling.md)
- [coding-standards.md](coding-standards.md)
- [../08-devops/ci-cd.md](../08-devops/ci-cd.md)
