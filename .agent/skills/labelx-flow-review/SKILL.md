---
name: labelx-flow-review
description: Review toàn luồng LabelX trên develop sau khi nhiều PR đã merge, trước khi PO merge develop vào main hoặc khi đóng một đợt task. Kiểm các PR ghép lại có khớp nhau không (contract, backend, frontend, worker, CVAT), đi hết luồng theo từng vai trò trên stack chạy thật, và đồng bộ .agent/planning với task board. Không dùng cho review một PR đơn lẻ; việc đó dùng skill labelx-pr-review.
---

# Review luồng LabelX

Review từng PR chỉ trả lời "PR này có đúng task của nó không". Review luồng trả lời "các PR đã merge ghép lại có chạy đúng không". Câu trả lời quyết định PO có merge `develop` → `main` (CR-104) hay có đóng đợt task được hay không.

Đợt 1 cho thấy những lỗi chỉ lộ ra khi nhìn cả luồng:
- Màn guideline (T-003) dùng quyền mà menu của app shell (T-002) không hiển thị cho reviewer.
- Bản ghi quyết định của hai task cùng lấy mã DEC-005.
- Planning (roadmap, milestones, epics, dependency-graph) đứng yên từ 06/10, trong khi task board đã đổi.
- Cả 5 task còn ở `review` dù PR đã merge.

## 0. Phạm vi và môi trường sạch

```bash
git fetch origin --prune
git worktree add ../flow-review origin/develop && cd ../flow-review
git log --oneline origin/main..origin/develop          # những gì sẽ lên main
gh pr list --state merged --base develop --limit 50 --json number,title,mergedAt,headRefName
gh run list --branch develop --limit 5                  # CI của commit mới nhất trên develop phải xanh
```

Lập bảng **PR → task → epic → milestone** cho mọi PR trong khoảng `origin/main..origin/develop`. Commit nào không thuộc PR hoặc task nào thì phải giải thích được.

Dựng stack thật từ đầu (không dùng DB hay `node_modules` cũ):

```bash
make setup            # hoặc: make backend-install frontend-install
make infra-up && make migrate
make cvat-up && make cvat-import-sample
make check
cd src/frontend && npm ci && npm run build && ! grep -rl 'password123' .next/static
```

Sau đó chạy `make dev-backend`, `make dev-worker`, `make dev-frontend` trong các terminal riêng.

## 1. Kiểm khớp giữa các PR

| Cặp cần khớp | Cách kiểm |
|---|---|
| `openapi.yaml` ↔ schema backend thật | Khi `dev-backend` chạy, so schema drf-spectacular với `docs/04-api/openapi.yaml` cho các endpoint đã có view: param, enum, mã lỗi |
| `openapi.yaml` ↔ `contract.d.ts` | `make gen-api` rồi `git diff --exit-code src/frontend/src/lib/api/contract.d.ts` |
| Ma trận RBAC ↔ backend ↔ frontend | Với mỗi vai trò: `docs/04-api/rbac-matrix.html` ↔ permission class backend ↔ `src/frontend/src/lib/auth/roles.ts` ↔ mục trên `TopBar`. Một vai trò có quyền thì phải vừa gọi được API vừa thấy lối vào |
| State machine ↔ code | Transition có trong code thì phải có trong `docs/04-api/state-machines.html`, và ngược lại khi đã implement |
| Frontend ↔ backend thật | Liệt kê màn nào còn chạy mock (`NEXT_PUBLIC_AUTH_MODE=mock`, route `src/frontend/src/app/api/**`). Ghi lại phần còn stub, không tính là xong |
| Quy ước dùng chung | Tên dataset, task, tag CVAT, hash annotation, class mapping detector có cùng một nguồn (DEC/BLOCKER) không, hay mỗi task tự đặt |

## 2. Đi hết luồng theo vai trò

Với từng vai trò trong 7 vai trò (`admin`, `qalead`, `qcadmin`, `reviewer`, `annotator`, `productowner`, `modelowner`):
1. Đăng nhập, rồi xem menu: mục nào hiện, mục nào ẩn, có khớp ma trận RBAC không.
2. Mở từng màn được phép: có dữ liệu thật không, phân trang, trạng thái rỗng và lỗi.
3. Gõ thẳng URL của màn bị cấm: phải bị chặn ở UI, và API phải trả 403.
4. Ghi kết quả thành bảng vai trò × màn: `đạt`, `lỗi` hoặc `stub`.

Luồng dữ liệu, ghi rõ khâu nào chạy thật và khâu nào còn giả:

```
CVAT (mẫu) → adapter chỉ đọc + hash → snapshot → detector JSON → QC run → issue → review → rework → báo cáo
```

Với mỗi khâu đã có code:
- Chạy một lần với dữ liệu mẫu và lưu đầu ra.
- Chạy lại lần hai: kết quả phải giống hệt (idempotent).
- Kiểm adapter không ghi gì sang CVAT.

## 3. Kiểm production build

- Build với `NODE_ENV=production`: mọi route mock trả 404, không có tài khoản mẫu trong bundle.
- `make detector-image` build được; checkpoint được kiểm checksum khi khởi động.
- Không có secret hay đường dẫn máy cá nhân trong repo: `git grep -nE '/home/|C:\\\\Users|password=|token='`.

## 4. Đồng bộ quản trị trước khi đóng

- [ ] Mọi task có PR đã merge đều ở `done` (có QA `passed`), `blocked` (có BLOCKER) hoặc `review` (có lý do). Không task nào bị bỏ quên ở `review`.
- [ ] Mỗi task có đủ implementation, review và QA report trong `.agent/reports/` (tên `T-xxx.html`, không còn `-@user`).
- [ ] `task-commit-map.html` có hash squash trên `develop` cho mọi task.
- [ ] Không còn file riêng của user: `find . -name '*-@*' -not -path '*/node_modules/*'` rỗng (CR-100, integrator gộp).
- [ ] Mã quản trị không trùng: `ls .agent/governance/*/ | grep -oE '^[A-Z]+-[0-9]+' | sort | uniq -d` rỗng.
- [ ] `.agent/planning/` (roadmap, milestones, epics, dependency-graph) khớp task board: trạng thái epic, milestone, cạnh phụ thuộc bị blocker chặn.
- [ ] `current-context.html` tăng revision, `sessions-history.html` có phiên này.
- [ ] Blocker đang mở có người chịu trách nhiệm và hạn; milestone có nguy cơ trễ thì ghi rõ cùng phương án (CR).
- [ ] `make validate-kit` đạt.

## 5. Kết luận và báo cáo

- Viết `.agent/reports/review/flow-<YYYY-MM-DD>.html` từ `.agent/templates/review-report-template.html`, `Review Type: release`. Khi merge lên `main` thì thêm `.agent/reports/releases/` theo `release-report-template.html`.
- Báo cáo gồm: bảng PR → task, bảng vai trò × màn, sơ đồ luồng đánh dấu khâu thật và khâu stub, finding theo mức độ như skill `labelx-pr-review`, danh sách việc chặn release.
- Kết luận chỉ là một trong hai: **Cho merge develop → main**, hoặc **Chưa** kèm danh sách finding `critical`/`major` phải xử lý. Finding phát sinh từ nhiều PR thì giao cho owner của task tạo ra phần lệch, hoặc mở task mới trên task board.

## Phối hợp khi nhiều phiên hoặc nhiều người cùng làm

- Mỗi phiên làm trong `git worktree` riêng; không đổi nhánh trong thư mục người khác đang dùng.
- Chỉ một integrator ghi file chính trong `.agent/`. Người khác ghi file `-@user` của mình.
- Commit theo đường dẫn (`git commit -m "..." -- <paths>`). Không `git add .` trên working tree dùng chung.
- Mỗi commit một việc: sửa theo review của task nào ghi `T-xxx`; việc gộp file của integrator đi commit riêng.
- Push, mở PR và merge cần PO đồng ý trực tiếp.
