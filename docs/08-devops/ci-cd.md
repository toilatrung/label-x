---
id: labelx-ci-cd
title: CI/CD và cổng kiểm thử LabelX
type: reference
domain: devops
module: repository
tags: [ci, cd, github-actions, quality-gates]
priority: 2
---

# CI/CD LabelX

## Trạng thái và giới hạn

GitHub Actions là phương án mặc định trong lần viết này; chưa có Git remote trong workspace, không có run GitHub hay deployment đã thực hiện. Không đổi stack DEC-001. Chưa có deployment target/Dockerfile/migration nghiệp vụ/reference; CD chỉ là khung có preflight chặn thiếu dữ liệu và hook.

## Workflow

| Workflow | Trigger | Nội dung | Điều kiện |
|---|---|---|---|
| [ci.yml](../../.github/workflows/ci.yml) | PR, push main, manual | Validate kit/plan; test cổng CI; Ruff/mypy/Django check/migrations/smoke PostgreSQL; Next lint/typecheck/build; artifact | Chỉ chứng minh scaffold và kiểm code hiện có |
| [phase-testing.yml](../../.github/workflows/phase-testing.yml) | Manual main | Một phase hoặc toàn nhóm MVP; bind pytest; receipt/JUnit | Missing test/dependency/reference/policy → BLOCKED; runner/evaluation environment nội bộ |
| [cd.yml](../../.github/workflows/cd.yml) | Manual main | Xác minh CI/phase run cùng SHA, quality receipts, hook đích, staging/production environment | Mặc định chưa cấu hình; không deploy khi thiếu hook/evidence/approval |

## Kiểm tra trên mỗi pull request

Mọi PR (kể cả từ fork) chạy `ci.yml` với quyền `contents: read`, không có secret. Ba status check phải đạt trước khi merge vào `main`:

| Status check | Bước chính |
|---|---|
| `framework` | `validate-framework.py`; ma trận test (`quality-gate.cjs validate-plan`, `render-plan.cjs --check`); `node --test scripts/ci/tests`; HTML sinh từ Markdown khớp (`scripts/md2html.py --check docs .agent`); SRS sinh lại từ LaTeX không đổi (`srs_tex2html.py`, `srs_tex2md.py` + `git diff --exit-code`) |
| `backend` | PostgreSQL 17 + Redis 7 service; `uv sync --frozen`; Ruff lint/format; mypy; `manage.py check`; `makemigrations --check`; `migrate`; OpenAPI `spectacular --validate`; **toàn bộ `pytest`** (mọi test trong `src/backend/tests`); ca đã đăng ký phase `scaffold`; artifact |
| `frontend` | `npm ci`; ESLint; `tsc`; `next build`; artifact |

Bước `pytest` toàn bộ bảo đảm test mới của collaborator luôn chạy, kể cả khi chưa được đăng ký trong `test-matrix.json`; `quality-gate` vẫn chạy riêng để tạo bằng chứng truy vết theo phase.

File hỗ trợ: [pull_request_template.md](../../.github/pull_request_template.md) (checklist truy vết và ràng buộc B-10/B-12/B-18), [CODEOWNERS](../../.github/CODEOWNERS) (mọi thay đổi cần review của `@toilatrung`), [dependabot.yml](../../.github/dependabot.yml) (github-actions, uv, npm, hằng tuần).

Cấu hình bảo vệ `main` trên GitHub (làm ở Settings/Rulesets, không nằm trong YAML): bắt buộc PR, bắt buộc 3 status check `framework`, `backend`, `frontend`, nhánh phải cập nhật với `main`, ít nhất 1 review và review của Code Owner, chặn force-push và xoá nhánh. Repo private cần gói GitHub Pro/Team để bật branch protection/rulesets.

## Dòng đi CI/CD

PR → quality checks → build artifacts cùng commit → phase tests + reference/evaluation khi đã có → review QA độc lập → staging smoke/migration rehearsal → approval environment → production hook → smoke → rollback hook khi deploy/smoke lỗi.

Không rebuild artifact giữa staging/production; promotion dùng cùng CI run/SHA. CI application gate 95% không phải test coverage code 95%, không phải GitHub branch protection. Application release Dataset khác triển khai phần mềm; full Dataset release sau M13 cần scope được duyệt.

Production phải cung cấp staging_run_id đã success và staging-verification.json có cùng source SHA, ci_run_id, test_run_id. Workflow kiểm actual environment API: required reviewers, prevent_self_review và branch policy, không chỉ dựa vào tên environment. Không có protection hoặc API đọc được cấu hình thì không deploy.

Ma trận MVP có nhóm Ranking/Evaluation truy từ SRS dự thảo; đây là profile kiểm thử đề xuất, không sửa scope/roadmap đã baselined. Owner phải review profile và các TBD trước khi bật CD. Artifact là gói source backend và Next build theo SHA, chưa phải container image; hook target phải cài runtime/dependency đúng lockfile và thực hiện healthcheck thật.

## Bootstrap trên GitHub

1. Đẩy thư mục vào repository Git; giữ main là branch chính hoặc sửa workflow theo branch thực.
2. Bật required checks: framework, backend, frontend; bảo vệ main và yêu cầu reviewer độc lập.
3. Tạo environment labelx-evaluation, staging, production, cấu hình required reviewers và prevent self-review. Các setting này phải làm ở GitHub; viết YAML không tự tạo approval. Khả năng protection phụ thuộc plan/repo.
4. Runner self-hosted Linux labels self-hosted/linux/labelx-evaluation chỉ chạy workflow main tin cậy; phải có Node 22, uv, Python 3.12, Docker, model/data nội bộ. Không cho PR code chạy trên runner có held-out/secrets.
5. Bind từng ca implemented trong test-matrix.json vào pytest node ID đã tồn tại; viết browser suite theo runner được chốt riêng. Không đánh dấu planned thành implemented chỉ để mở gate.
6. Cấp policy/reference/model/score manifest đã được duyệt cho evaluation; example policy là draft và không dùng nghiệm thu.
7. Tạo scripts/deploy/staging.sh, production.sh và rollback.sh theo target thực; không để echo TODO trả 0. Hook phải dùng artifact path được truyền, backup/migration plan, healthcheck và rollback. Set environment variable LABELX_CD_ENABLED=true chỉ sau đủ cấu hình/phê duyệt.

Environment evaluation cần TEST_DATABASE_URL, TEST_CELERY_BROKER_URL/RESULT_BACKEND, TEST_OBJECT_STORAGE_ENDPOINT_URL/ACCESS_KEY/SECRET_KEY và TEST_OBJECT_STORAGE_BUCKET của hạ tầng kiểm thử. Fixture phải dùng LABELX_TEST_NAMESPACE theo run/attempt; workflow serializes evaluation jobs để tránh chạy chung database/reference mutable. Raw logs nằm private, export-evidence chỉ publish counters/checksum/case IDs đã redacted. Credentials không đưa vào policy example hoặc source.

## Secrets và artifact

PR jobs không có CVAT/model credentials. GitHub token chỉ contents:read/actions:read khi cần tải evidence; không pull_request_target, không token write mặc định. Không upload .env, token, ảnh, held-out hay prompt chứa dữ liệu riêng. Cache npm/uv chỉ dependency, không dataset/model riêng. CI artifact retention theo setting repository; đây không thay policy giữ snapshot/evidence/reference của sản phẩm.

## Lệnh local

```bash
make check   # lint, typecheck, test, validate-kit (cần make infra-up)
uv run --no-project --with markdown --with pymdown-extensions python scripts/md2html.py docs .agent
python3 scripts/srs_tex2html.py && python3 scripts/srs_tex2md.py
node --test scripts/ci/tests/*.test.cjs
node scripts/ci/quality-gate.cjs validate-plan
node scripts/ci/render-plan.cjs --check
node scripts/ci/quality-gate.cjs run --phase scaffold
# Phase chưa triển khai phải trả BLOCKED, exit 2:
node scripts/ci/quality-gate.cjs run --phase p0_snapshot
```

make check vẫn là kiểm chuẩn scaffold (cần hạ tầng). CI không sửa .env local, không tạo tài khoản, không sửa CVAT hoặc khởi chạy load/recovery trên production.

## Nguồn

- [uv GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/): uv sync --frozen và setup action.
- [GitHub service PostgreSQL](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers): DB tạm và healthcheck.
- [GitHub environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments): required reviewers/prevent self-review phải cấu hình ngoài YAML.
- [Test strategy](../09-testing/test-strategy.md), [DEC-001](../../.agent/governance/decisions/DEC-001.md), SRS AC-01…AC-11 và NFR.
