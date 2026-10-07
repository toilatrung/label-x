---
name: labelx-pr-review
description: Review một pull request của LabelX vào develop trước khi comment "Đã xem và duyệt" (CR-102). Dùng khi được nhờ review PR, kiểm task trước khi merge, hoặc viết review report trong .agent/reports/review/. Đối chiếu từng acceptance criterion với bằng chứng chạy thật, không chỉ đọc diff.
---

# Review PR LabelX

Mục tiêu: chỉ comment `Đã xem và duyệt` khi mọi acceptance criterion của task có bằng chứng kiểm được và không còn finding `critical`/`major` mở. Đợt 1 (T-001…T-005) cả 5 PR đã được duyệt rồi merge, nhưng đợt đóng vẫn tìm ra 9 finding `major`/`critical`. Phần lớn chúng lọt vì người review đọc diff và mô tả PR, không chạy, không đối chiếu AC. Mục "Lỗi đã lọt" ở cuối liệt kê từng trường hợp và bước nào bắt được nó.

## 0. Chuẩn bị: review trên code chạy được, không trên giao diện GitHub

```bash
git fetch origin --prune
gh pr view <số> --json baseRefName,headRefName,headRefOid,commits,files,body
git worktree add ../review-pr-<số> origin/<headRefName>   # không đổi nhánh trong thư mục đang có người làm
cd ../review-pr-<số>
git log --oneline origin/develop..HEAD                      # commit nào thuộc PR
git merge-base --is-ancestor origin/develop HEAD || echo "Chưa cập nhật develop mới nhất"
```

- Base phải là `develop` (CR-104). PR vào `main` chỉ do PO mở.
- Ghi lại `headRefOid` đã review. Nếu có commit được đẩy sau khi duyệt thì lời duyệt mất hiệu lực và phải review lại phần mới.
- Nhiều phiên hoặc nhiều người dùng chung một checkout thì luôn làm trong worktree riêng.

## 1. Đọc task trước, đọc code sau

1. Mở bản ghi task trong `.agent/execution/task-board.html#t-xxx`: Objective, Scope (Included/Excluded), Acceptance Criteria, Verification Requirements, Expected Evidence.
2. Lập bảng AC → bằng chứng. Mỗi dòng AC phải trỏ tới **một thứ kiểm lại được**: test cụ thể, lệnh kèm output, file đầu ra đã commit, ảnh chụp màn hình.
   - Câu tự khai trong report ("đã chạy 10 ảnh, OK") **không phải bằng chứng** (T-005 F-1).
   - AC có chữ "mỗi"/"mọi" ("mỗi endpoint/transition có trích FR/BR/UC") phải được kiểm hết danh sách, không kiểm mẫu vài dòng (T-001 F-1).
3. Đối chiếu Scope: phần nào trong Included mà không có trong PR thì là thiếu; phần nằm trong Excluded mà PR lại làm thì phải có CR hoặc DEC.
4. Kiểm giả định dữ liệu đầu vào của task trên dữ liệu thật trước khi review code dựa trên nó (T-004 F-1: tệp người học có 0 ảnh BDD100K, `make cvat-audit-learner` cho thấy ngay).

## 2. Chạy, không đọc suông

```bash
make infra-up && make check          # lint, typecheck, pytest trên Postgres, vitest, detector, validate-kit
```

`make check` **không** build frontend và **không** sinh lại type. Tuỳ phần PR đụng tới, chạy thêm:

| PR đụng tới | Chạy thêm |
|---|---|
| `src/frontend/**` | `cd src/frontend && npm run build && ! grep -rl 'password123' .next/static`; mở màn bằng `make dev-frontend` |
| `docs/04-api/openapi.yaml` hoặc view/serializer | `make dev-backend` rồi `make gen-api`; `git diff --exit-code src/frontend/src/lib/api/contract.d.ts` |
| `src/detector_worker/**`, `infrastructure/detector-worker/**` | `make detector-lint detector-test`; `make detector-image` khi đổi Dockerfile |
| CVAT, `scripts/development/cvat*` | `make cvat-up`, `make cvat-import-sample`, `make cvat-hash` |
| `.agent/**`, `docs/**` | `make validate-kit`, rồi mở file HTML trong trình duyệt để xem có lỗi font/mojibake không |

- Test chỉ pass trên SQLite chưa đủ; QA phải ghi kết quả trên Postgres.
- Thành phần mới (thư mục, worker, script) phải có job CI chạy nó (T-005 F-2). Kiểm trong `.github/workflows/ci.yml`.
- Xem CI của đúng `headRefOid`: `gh pr checks <số>`.

## 3. Checklist theo phần

### Contract và API
- [ ] Query param và field dùng enum đúng như `components.schemas` trong `openapi.yaml` (T-003 F-2: `family` để kiểu `str` trong khi contract là enum `IssueFamily`).
- [ ] Mọi mã lỗi view có thể trả về (400/403/404/409/422) đều được khai báo trong contract; body lỗi có `code`, `message`, `request_id`.
- [ ] `contract.d.ts` được sinh lại và commit cùng PR.
- [ ] Trích dẫn FR/BR/UC phải có trong `docs/label-x_system-requirement-specification/sections/*.tex` **và đúng nghĩa**. Test chỉ kiểm mã có tồn tại, người review phải đọc câu yêu cầu (T-001: `run.fail` từng trích FR-RWK-08 là sai nghĩa).
- [ ] Transition mới phải có trong `docs/04-api/state-machines.html`.

### Backend
- [ ] Quyền kiểm ở API theo ma trận RBAC (`docs/04-api/rbac-matrix.html`); có test cho từng vai trò bị từ chối, không chỉ test vai trò được phép.
- [ ] Adapter CVAT chỉ đọc: `git diff origin/develop -- src/backend/cvat_adapter | grep -nE '\.(post|put|patch|delete)\('` phải rỗng. Sửa annotation chỉ qua deep link.
- [ ] Celery task idempotent: chạy lại cùng input không tạo bản ghi trùng; có test retry.
- [ ] Migration có trong PR và áp dụng được trên Postgres sạch (`make migrate`).
- [ ] Không dùng tạm cơ chế khác với contract mà không ghi lại (T-003 F-5: lấy vai trò từ Django groups thay vì role assignment).

### Frontend
- [ ] Mọi trang được bọc `AuthGuard` và `AppShell` (T-003 F-1).
- [ ] Mỗi vai trò được phép vào trang đều thấy lối vào trên điều hướng. Test TopBar chạy đủ 7 vai trò `admin, qalead, qcadmin, reviewer, annotator, productowner, modelowner` (T-003 F-7: reviewer có quyền nhưng không có link).
- [ ] Không có dữ liệu giả hiển thị như dữ liệu thật (bảng phiên bản "Mới nhất" cố định ở T-003).
- [ ] Danh sách có phân trang thì xem được quá trang đầu (T-003: chỉ tải 50 rule đầu).
- [ ] Không có tài khoản mẫu, mật khẩu hay token nào trong bundle client. Đọc `import` ở các file `'use client'`; build rồi grep `.next/static` (T-002 F-1: `MOCK_USERS` lọt vào bundle production).
- [ ] Mỗi màn có trạng thái loading, rỗng và lỗi; UI dùng `lx-*`, đúng Design System (skill `labelx-design`).
- [ ] Mở màn thật bằng `make dev-frontend` với ít nhất một vai trò được phép và một vai trò bị chặn.

### Worker và ML
- [ ] Có đầu ra thật được commit (JSON, số detection theo lớp, SHA-256 của file), không chỉ log tự khai.
- [ ] Checkpoint được kiểm checksum theo `model-manifest.json`; có bằng chứng file hỏng bị từ chối.
- [ ] Ghi rõ môi trường chạy (GPU/CPU, Docker hay không, phiên bản Python) và chỗ lệch so với pin.

### Bằng chứng và quản trị (`.agent/`)
- [ ] Mã DEC/BLOCKER/RISK/CR mới không trùng với mã đã có, kể cả trong file `-@user` của người khác: `ls .agent/governance/*/ | grep -oE '^[A-Z]+-[0-9]+' | sort | uniq -d` phải rỗng (T-001 F-2: hai bản ghi cùng mã DEC-005).
- [ ] Implementation report không còn `draft`; mở được và đọc được tiếng Việt (T-003 F-3: report bị mã hoá UTF-8 hai lần).
- [ ] Commit map trỏ tới commit có thật trên `develop`. Sau squash merge phải ghi hash squash, không ghi hash nhánh (T-001 F-3, T-002 F-2, T-004 F-4).
- [ ] Ghi đúng file `-@user` theo CR-100; chỉ integrator gộp vào file chính.
- [ ] Context và report ghi PR vào `develop`, không phải `main` (T-003 F-4).
- [ ] Không có secret: `git diff origin/develop --stat`, rồi xem kỹ `.env*`, token CVAT, đường dẫn máy cá nhân.

## 4. Ghi finding

Mỗi finding gồm: mã `F-n`, mức độ, `file:dòng`, tình huống lỗi cụ thể (input hoặc vai trò → kết quả sai), việc cần làm.

| Mức | Nghĩa | Duyệt được không |
|---|---|---|
| `critical` | Sai mục tiêu task, mất dữ liệu, lộ bảo mật, giả định dữ liệu sai | Không. Sửa xong, hoặc PO quyết định ghi blocker |
| `major` | Một AC chưa đạt hoặc chưa có bằng chứng; lỗi người dùng gặp phải | Không |
| `minor` | Lệch quy ước, thiếu bản ghi phụ | Được, nếu có issue theo dõi |
| `observation` | Nợ kỹ thuật, việc cho đợt sau | Được |

Không viết "LGTM" khi chưa có bảng AC → bằng chứng. Nếu không chạy được một bước, ghi rõ bước đó là `skipped` kèm lý do; không đánh dấu là đạt.

## 5. Kết thúc

1. Viết `.agent/reports/review/T-xxx.html` từ `.agent/templates/review-report-template.html`, gồm bảng finding và `headRefOid` đã review.
2. Còn finding `critical`/`major` mở: comment danh sách cần sửa, không duyệt.
3. Đạt: comment đúng câu `Đã xem và duyệt`. Có commit mới sau đó thì quay lại bước 0.
4. Sau khi merge: task chưa sang `done` cho tới khi QA report (`.agent/reports/qa/`) ở `passed` và commit map có hash squash.

## Lỗi đã lọt ở đợt 1 và bước bắt được

| Finding | Lỗi | Bước bắt được |
|---|---|---|
| T-001 F-1 | 6 transition không trích FR/BR/UC | 1.2 kiểm hết danh sách "mỗi" |
| T-001 F-2, T-005 F-3 | Trùng mã DEC-005 | 3, quản trị: lệnh `uniq -d` |
| T-002 F-1 | Mật khẩu mẫu trong bundle production | 2, `npm run build` + grep |
| T-003 F-1, F-7 | Màn không có guard, reviewer không có lối vào | 3, frontend: AuthGuard, test 7 vai trò, mở màn thật |
| T-003 F-2 | Param không theo enum, 400 không khai báo | 3, contract |
| T-003 F-3 | Report mojibake | 2, mở file HTML |
| T-004 F-1 | Dữ liệu người học có 0 ảnh BDD100K | 1.4 kiểm giả định dữ liệu |
| T-005 F-1 | Bằng chứng inference chỉ là câu tự khai | 1.2 và 3, worker |
| T-005 F-2 | CI không chạy detector | 2, job CI cho thành phần mới |
