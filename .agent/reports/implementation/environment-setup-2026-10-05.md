---
id: labelx-environment-setup-implementation-2026-10-05
title: Bootstrap môi trường dev và hướng dẫn máy mới
type: report
domain: development
module: repository
tags: [implementation, onboarding, bootstrap, windows, ubuntu]
priority: 2
---
# Implementation Report Template

## Usage Purpose

Ghi bằng chứng cho yêu cầu trực tiếp đổi tên scripts/Makefile, kiểm và bổ sung bootstrap máy mới, tạo env-setup.md. Không phê duyệt QA độc lập.

## Record Metadata

- **Report ID**: `USER-ENV-2026-10-05`
- **Title**: `Khởi tạo môi trường phát triển`
- **Owner**: `project-owner`
- **Executor**: `Codex`
- **Status**: `draft`
- **Task ID**: `direct-user-request; no registered task`
- **Epic ID**: `none; no registered epic`
- **Report Date**: `2026-10-05`

## Scope

- **Implemented**: đổi tên Make adapter; bootstrap PowerShell/Ubuntu; opt-in công cụ máy; dependencies frozen; random secret và bảo toàn env; chặn endpoint ngoài local/mixed OS; kiểm dịch vụ/migrate/check/build; onboarding không yêu cầu Make; bootstrap tests trong CI.
- **Not Implemented**: cài thật công cụ máy, kiểm máy sạch/real Docker, tự bật virtualization/WSL/khởi động lại/cấp quyền Docker, CVAT/model/reference, runtime Celery Windows, triển khai production.

## Changes Made

| File or Artifact | Change Summary | Task ID |
|---|---|---|
| `scripts/init-develop-environment.mk`, `Makefile` | Rename; setup tuần tự qua Bash; quote đường dẫn; cleanup allowlist | direct-user-request |
| `scripts/init-develop-environment.ps1`, `.sh` | Setup/Check/Plan; cài global có lựa chọn; lỗi trả nonzero | direct-user-request |
| `scripts/development/` | Shared env/preflight, đọc kiểm PostgreSQL/Redis/S3, cleanup guard, 9 test | direct-user-request |
| `infrastructure/docker-compose.dev.yml` | Bucket init fail-fast, bootstrap dùng compose run để nhận exit code | direct-user-request |
| `env-setup.md`, `README.md`, docs development/devops/security | Hướng dẫn máy chưa có Make/Bash/Git; cập nhật đường dẫn và hành vi | direct-user-request |
| `.github/workflows/ci.yml` | Kiểm bootstrap trên Linux và PowerShell/Node trên Windows, không cài global trong test | direct-user-request |

## Related Files

- **Task Records**: none; yêu cầu trực tiếp của người dùng.
- **Context Packages**: `AGENT.md`, `.agent/governance/decisions/DEC-001.md`, cấu hình stack và docs liên quan.
- **Task Board**: `.agent/execution/task-board.md` (không đổi).
- **Current Context**: `.agent/execution/current-context.md` (không đổi).
- **Decisions**: DEC-001 giữ nguyên; tham chiếu tên scripts/Makefile trong quyết định đã accepted là lịch sử.
- **Change Requests**: not applicable; không đổi operating policy.
- **Risks or Blockers**: thiếu Docker và Python 3.12 native trên máy kiểm tra; tải công cụ Python/dependency bị chặn network.
- **Review Request**: pending independent review.
- **Commits**: none; workspace không có .git.

## Command Evidence

| Command | Result | Evidence |
|---|---|---|
| `agent task start TASK-ID` | not-run | Không có task/epic đăng ký, yêu cầu trực tiếp |
| `agent task verify TASK-ID` | not-run | Không có task ID |
| `agent task report TASK-ID --executor Codex` | not-run | Báo cáo scoped viết trực tiếp |
| `agent review request TASK-ID --reviewer ...` | not-run | Chưa có reviewer được chỉ định |

## Verification Evidence

| Check | Result | Evidence |
|---|---|---|
| `node --test scripts/development/tests/environment.test.cjs scripts/ci/tests/*.test.cjs` | passed | 29 test, 29 pass, 0 skip trên Windows |
| PowerShell Parser.ParseFile | passed | Không lỗi AST |
| Bash `-n` và `--plan` qua Git Bash | passed | Parse thành công; Plan không cài hoặc sửa file |
| PowerShell `-Mode Plan` | passed | Plan không cài; test thực thi |
| PowerShell `-Mode Check` | failed | Báo thiếu Docker, trả exit 1; không báo setup thành công |
| GNU Make `--dry-run setup` | passed | Chỉ gọi Bash bootstrap tuần tự, dùng mingw32-make có sẵn |
| `scripts/validate-framework.py` qua Python embedded có sẵn | passed | FRAMEWORK_VALIDATION_PASS; không kết nối MySQL |
| `make check`, `make validate-kit` theo uv/Python 3.12 chuẩn | not-run | Thiếu Docker và Python 3.12 native; dependency hiện tại thuộc Linux |
| Freshness HTML bằng `scripts/md2html.py --check` | not-run | Thiếu Markdown/pymdown-extensions; tải bị chặn. HTML các docs đã thay đổi đồng bộ theo nội dung, chưa có bằng chứng renderer chính thức |
| Cài global/local end-to-end trên máy sạch | not-run | Không cài công cụ toàn cục hoặc migrate database khi kiểm tra |

## Deviations

- **Plan Deviations**: thêm bootstrap .ps1/.sh vì Make không thể là prerequisite trên máy mới và recipes cũ chỉ phù hợp Bash. Dùng Python embedded đã có để kiểm framework stdlib; đây không phải runtime project.
- **Approved By**: yêu cầu người dùng trong phiên, không ghi thay quyết định stack.
- **Known Limitations**: hỗ trợ auto global Windows và Ubuntu 22.04/24.04/26.04; WSL Docker Desktop integration có bước thủ công. Check không build frontend. Script không tự gỡ Docker cũ, cấp Docker group hoặc tạo CVAT/reference. CI mới chưa được chạy trên GitHub. Cần kiểm máy sạch trước phát hành bootstrap cho toàn đội.

## Completion Criteria

- [x] Every reported change maps to an authorized task (direct request).
- [x] Acceptance criteria results and evidence are linked; kiểm máy sạch còn thiếu.
- [x] Deviations and limitations are explicit.
- [x] Build, lint, and test checks are recorded or explicitly marked not-run with rationale.
- [ ] Reviewer handoff identifies an independent Reviewer Agent.
- [ ] Git Nexus mappings are updated when commits exist (không có commit).

## Forbidden Actions

Không nhận QA độc lập/self-approval; không coi mock/Plan là cài thật; không ghi secret hoặc sửa accepted DEC-001.

## Output Requirements

Báo cáo runtime ở `.agent/reports/implementation/`, trạng thái draft, không đổi task thành done.
