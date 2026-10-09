---
name: labelx-qc-integrate
description: QC (QA/QC) một task hoặc cả đợt LabelX sau khi review đã đạt, rồi gộp mọi file riêng của dev (-@user) vào file chính và xoá chúng (CR-100). Dùng khi được nhờ chạy QC sau review, đóng task/đợt, hoặc khi còn file .agent/**/*-@<user>.html trên develop. Chỉ integrator (.github/agent-integrators.txt) được ghi file chính và xoá file riêng.
---

# QC và gộp file riêng của dev

Quy trình đứng sau `labelx-pr-review` (review từng PR) và trước `labelx-flow-review` (review toàn luồng trước khi merge `develop` → `main`). Thứ tự bắt buộc: **review đạt → QC → gộp và xoá file `-@user` → đóng task**. Gộp file riêng là một phần của QC, không phải việc tuỳ chọn: file riêng còn tồn tại nghĩa là QC chưa xong (CR-100).

Việc audit M-01 (`.agent/reports/review/flow-2026-10-09.html`) cho thấy hai lỗi lặp lại: task `review` nhiều ngày không ai chạy QC, và 23 file `-@user` nằm lại trên `develop` trong khi board và context chính vẫn nói `pending`.

## 0. Ai được làm và chuẩn bị

- Chỉ người trong `.github/agent-integrators.txt` (PO và QC được PO giao) được sửa file chính hoặc xoá file riêng. Không phải integrator thì dừng và báo; `scripts/ci/check-agent-ownership.cjs` sẽ làm PR đỏ.
- Người QC **không phải** người đã viết implementation hay review của task đó.
- Tạo nhánh từ `develop` (CR-104) và làm trong worktree riêng, không đổi nhánh trong thư mục người khác đang dùng:

```bash
git fetch origin --prune
git worktree add ../qc-<tên-đợt> -b chore/qc-<tên-đợt> origin/develop
cd ../qc-<tên-đợt>
git log --oneline origin/main..origin/develop     # đã merge gì
find . -name '*-@*' -not -path '*/node_modules/*' -not -path '*/.venv/*'   # file riêng cần gộp
gh pr list --state open --base develop            # PR đang mở có thể đụng cùng file .agent/
```

- Nhiều phiên cùng làm: hỏi `ListAgents`, nhắn phiên khác trước khi sửa `task-board.html`, `current-context.html`, `epics.html`. Các file này chỉ một người ghi tại một thời điểm.
- Khi bắt đầu QC, ghi lại `git rev-parse origin/develop`. Kết luận QC chỉ áp dụng cho SHA đó.

## 1. Điều kiện vào QC (mỗi task)

Task chỉ vào QC khi đủ:

| Điều kiện | Cách kiểm |
|---|---|
| Trạng thái `review` | `task-board.html` và file `task-board-@user.html` của chủ task |
| Code đã nằm trên `develop` | `gh pr list --state merged --base develop`; code chỉ ở nhánh hoặc PR mở thì **không** tính |
| Có implementation report `complete` | `.agent/reports/implementation/T-xxx.html` hoặc bản `-@user` |
| Có review report `approved`, không còn `critical`/`major` mở | `.agent/reports/review/T-xxx.html` |

Thiếu review: dừng task đó, không tự viết review thay người khác. Ghi vào danh sách "chờ review" của báo cáo QC.

## 2. Chạy QC: hành vi thật, không đọc báo cáo

1. Dựng stack sạch rồi chạy kiểm tra:

```bash
make backend-install frontend-install
make infra-up && make migrate
make check                      # lint, typecheck, pytest, vitest, detector, validate-kit
cd src/frontend && npm run build && ! grep -rl 'password123' .next/static
```

2. Với từng task, lập bảng AC → bằng chứng như ở `labelx-pr-review` mục 1, nhưng bằng chứng phải do **QC tự chạy** trên SHA đang kiểm: lệnh kèm output, gọi API thật, mở màn thật bằng ít nhất một vai trò được phép và một vai trò bị chặn. Câu tự khai trong implementation report không thay thế được.
3. Kiểm quyền và từ chối, không chỉ đường thành công: 403 có bản ghi audit; thiếu CSRF bị chặn; vai trò ngoài ma trận RBAC bị từ chối.
4. Kiểm migration trên DB trống và nâng cấp từ `main`; backend và frontend đều được chạy trong `make check`.
5. Xem CI của đúng SHA: `gh run list --commit <sha>`. CI xanh của commit cũ không thay thế.
6. Ghi rõ test bị skip, mock, xfail. Bước không chạy được thì ghi `NOT VERIFIED` kèm lý do, không ghi đạt.
7. Phát hiện lỗi: ghi finding (mức độ, `file:dòng`, bước tái hiện, expected/actual), tạo issue trong `.agent/governance/issues/`, **không sửa mã sản phẩm trong lượt QC** và không đổi trạng thái để hồ sơ "đạt".

Kết quả mỗi task: `passed`, `failed` hoặc `blocked`. Viết `.agent/reports/qa/T-xxx.html` từ `.agent/templates/qa-report-template.html` (tên không có `-@user`). Báo cáo QC theo đợt nằm ở `.agent/reports/qa/<đợt>.html`. Báo cáo cuối là bất biến: sửa bằng báo cáo thay thế có liên kết bản cũ.

Chạy cả trường hợp `make check` đỏ: dừng gộp các task bị ảnh hưởng, ghi `failed`, báo cho owner.

## 3. Gộp file riêng vào file chính rồi xoá

Làm **sau** khi có kết quả QC để trạng thái ghi vào file chính phản ánh đúng bằng chứng. Mỗi commit một việc: gộp file riêng đi commit riêng (`chore(agent): integrator gộp ... (CR-100)`), tách khỏi commit viết báo cáo QC và khỏi commit sửa mã.

### 3.1 Bản đồ gộp

| File riêng | Gộp vào | Cách gộp |
|---|---|---|
| `execution/task-board-@u.html` | `execution/task-board.html` | Cập nhật hàng bảng theo `Task ID` (trạng thái, Evidence Links, ngày); sửa trường `Status` trong mục chi tiết của task; chép ghi chú và checkbox có bằng chứng. Hàng `done` không bị hạ về `review` |
| `execution/current-context-@u.html` | `execution/current-context.html` | Thêm vào mục "Wave n Integration" (bảng Task/Epic/Owner/Branch/Base/Status) và "Carried Notes" (một `h3` mỗi task); bỏ hướng dẫn quy trình đã lỗi thời. Tăng `Context Revision`, cập nhật `Last Updated`, `Updated By`, `In Review`, `Active Blocker IDs`, `Active Decision IDs` |
| `intelligence/git-nexus/task-commit-map-@u.html` | `.../task-commit-map.html` | Hàng trong "Implementation Commits on develop" dùng **hash squash trên `develop`** (từ `gh pr list --state merged`), hàng trong "Branch Commits" ghi `squash vào <hash>`. Không ghi hash nhánh vào bảng develop |
| `reports/implementation/T-xxx-@u.html`, `reports/review/T-xxx-@u.html` | `.../T-xxx.html` | Đổi tên (`git mv`), sửa `labelx:id` về dạng chuẩn (`implementation-t-xxx`, `review-t-xxx`), trường `Report ID`, tiêu đề, và mọi chuỗi `T-xxx-@u` thành `T-xxx` |
| `governance/decisions/DEC-nnn-@u.html` (và blocker/CR/risk) | `DEC-nnn.html` | Như trên; kiểm mã không trùng trước khi đổi tên |

Quy tắc xung đột (theo AGENT.html, không theo mốc thời gian của file):
- Đã có bản chính cùng tên (ví dụ `T-014.html` đã merge): **không ghi đè**. Giữ bản chính, thêm mục "Bổ sung từ báo cáo riêng" chứa thông tin còn thiếu (commit, kết quả kiểm), rồi xoá bản riêng. Báo cáo đã hoàn tất là bằng chứng bất biến.
- Hai bản ghi cùng mã (DEC/BLOCKER/RISK/CR): bản đã được duyệt thắng; bản còn lại đổi sang mã mới và ghi vào `sessions-history`.
- File riêng nói trạng thái cũ hơn file chính (ví dụ `review` trong khi chính là `done`): giữ file chính.
- **Không bịa dữ liệu.** Tên nhánh, base commit hay hash mà file riêng không ghi thì để `—`, không đoán.
- File riêng có hướng dẫn đã lỗi thời ("mở PR vào `main`") thì không chép sang.

### 3.2 Xoá và sửa liên kết

```bash
git rm .agent/execution/*-@*.html .agent/intelligence/git-nexus/*-@*.html     # sau khi đã gộp
# liên kết href trỏ tới file riêng -> trỏ tới file chính
grep -rn --include=*.html -E 'href="[^"]*-@[a-z0-9-]+\.html' .agent docs
find . -name '*-@*' -not -path '*/node_modules/*' -not -path '*/.venv/*'      # phải rỗng
make validate-kit                                                              # phải PASS
```

Đoạn văn mô tả lịch sử ("đã gộp từ `current-context-@u.html`") được giữ nguyên; chỉ sửa `href`.

### 3.3 Ghi nhận

- `execution/sessions-history.html`: thêm một dòng phiên (Session ID mới, owner, phạm vi, kết quả, file bằng chứng).
- `execution/current-context.html`: tăng revision; `Active Task IDs`, `In Review`, `Pending` khớp board.
- `planning/epics.html`, `milestones.html`, `roadmap.html`: cập nhật `Task IDs`, `Blocked By` và trạng thái khi có thay đổi thật; không tự đổi trạng thái epic/milestone nếu tiêu chí hoàn thành chưa đạt.

## 4. Đóng task

Chuyển `review` → `done` chỉ khi **đồng thời**: review `approved`, QA report `passed` trên SHA đã kiểm, hash squash có trong commit map, và không còn finding `critical`/`major`. Mọi trường hợp khác giữ nguyên trạng thái và ghi lý do. Epic chỉ `EPIC_DONE` khi mọi task con `done` hoặc đã huỷ có lý do và completion criteria của epic đạt. Không bao giờ đánh dấu `done` để làm hồ sơ "đạt".

## 5. Kết thúc

1. Đẩy nhánh và mở PR vào `develop` (CR-104). Mô tả nêu SHA đã kiểm, task `passed`/`failed`/chờ review, và file riêng đã gộp. Push và mở PR cần PO đồng ý.
2. Không tự comment `Đã xem và duyệt` (CR-102): chỉ người được giao duyệt.
3. Sau khi merge: `git pull` ở các checkout chung; nhắn các phiên khác đang giữ file riêng cũ để họ bỏ thay đổi cục bộ.
4. Trước khi merge `develop` → `main`: chạy `labelx-flow-review`.

## Lỗi đã gặp khi gộp (đợt M-01)

| Lỗi | Cách tránh |
|---|---|
| Bản `T-014-@user` mâu thuẫn bản `T-014.html` đã merge | 3.1: giữ bản chính, thêm mục bổ sung |
| Hash nhánh bị ghi như hash develop trong commit map | 3.1: lấy hash squash từ PR đã merge |
| Liên kết `href` tới file riêng gãy sau khi xoá (`validate-kit` báo `INTERNAL_LINK_BROKEN`) | 3.2: sửa `href` trước khi chạy validate |
| Tên nhánh/base commit điền theo trí nhớ | 3.1: để `—` nếu file riêng không ghi |
| Hai phiên cùng sửa `ci.yml`, `.agent/*` trong cùng working tree | 0: worktree riêng, báo nhau trước khi ghi |
| `labelx:id` của file đổi tên vẫn mang hậu tố người dùng | 3.1: sửa về id chuẩn, chạy `validate-kit` (id phải duy nhất) |
