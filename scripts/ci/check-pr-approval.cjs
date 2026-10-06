'use strict';
// Kiểm quy tắc duyệt pull request (AGENT.html "Pull Request Approval", CR-102):
// - người có cờ self-approve trong .github/pr-approvers.txt (PO) được tự duyệt PR của mình;
// - PR của người khác cần comment "Đã xem và duyệt" của một approver khác tác giả,
//   viết sau commit cuối của PR (push thêm commit thì phải duyệt lại).
// - PR của thành viên phải nhắm nhánh develop; chỉ PO đưa develop vào main sau khi review toàn luồng (CR-104).
// Kết quả ghi thành commit status "pr-approval" trên head commit để đặt làm required check.
// CLI (CI): GITHUB_TOKEN=<token> REPO=<owner/repo> PR_NUMBER=<n> node scripts/ci/check-pr-approval.cjs
const fs = require('node:fs'), path = require('node:path');

const ROOT = path.resolve(__dirname, '../..');
const APPROVERS_FILE = '.github/pr-approvers.txt';
const APPROVAL_TEXT = 'Đã xem và duyệt';
const CONTEXT = 'pr-approval';
const INTEGRATION_BRANCH = 'develop', RELEASE_BRANCH = 'main';

// Mỗi dòng: <username> [self-approve]; bỏ comment (#), @ và phân biệt hoa thường.
function parseApprovers(text) {
  const approvers = new Set(), selfApprovers = new Set();
  for (const raw of text.split(/\r?\n/)) {
    const [name, flag] = raw.replace(/#.*/, '').trim().split(/\s+/);
    if (!name) continue;
    const login = name.replace(/^@/, '').toLowerCase();
    approvers.add(login);
    if (flag === 'self-approve') selfApprovers.add(login);
  }
  return {approvers, selfApprovers};
}

const norm = s => String(s || '').normalize('NFC').trim().replace(/\s+/g, ' ').toLocaleLowerCase('vi');
const isApprovalText = body => norm(body) === norm(APPROVAL_TEXT);

// comments: [{login, body, updatedAt}]; lastCommitDate: ISO string của commit cuối.
function evaluate({author, approvers, selfApprovers, comments, lastCommitDate, base = INTEGRATION_BRANCH}) {
  const login = String(author || '').replace(/^@/, '').toLowerCase();
  if (!login) return {ok: false, reason: 'Không xác định được tác giả pull request.'};
  if (selfApprovers.has(login)) return {ok: true, reason: `@${login} được tự duyệt (PO, CR-102).`};
  if (base === RELEASE_BRANCH) return {ok: false, reason: `PR phải nhắm nhánh ${INTEGRATION_BRANCH}, không vào ${RELEASE_BRANCH}; PO merge ${INTEGRATION_BRANCH} sang ${RELEASE_BRANCH} (CR-104).`};
  const since = Date.parse(lastCommitDate);
  const valid = comments.filter(c => {
    const by = String(c.login || '').toLowerCase();
    return approvers.has(by) && by !== login && isApprovalText(c.body)
      && !(Date.parse(c.updatedAt) < since);
  });
  if (valid.length) return {ok: true, reason: `Đã duyệt bởi @${valid[valid.length - 1].login}.`};
  const stale = comments.some(c => approvers.has(String(c.login || '').toLowerCase())
    && String(c.login).toLowerCase() !== login && isApprovalText(c.body));
  return {ok: false, reason: stale
    ? `Có commit mới sau lần duyệt; cần comment "${APPROVAL_TEXT}" lại.`
    : `Chờ approver (khác tác giả) comment "${APPROVAL_TEXT}".`};
}

async function api(token, url, init = {}) {
  const r = await fetch(`https://api.github.com${url}`, {
    ...init,
    headers: {Accept: 'application/vnd.github+json', Authorization: `Bearer ${token}`,
      'X-GitHub-Api-Version': '2022-11-28', ...(init.headers || {})},
  });
  if (!r.ok) throw new Error(`${init.method || 'GET'} ${url}: ${r.status} ${await r.text()}`);
  return r.json();
}

async function main(env = process.env) {
  const {GITHUB_TOKEN: token, REPO: repo, PR_NUMBER: pr} = env;
  if (!token || !repo || !pr) { console.error('Cần GITHUB_TOKEN, REPO và PR_NUMBER.'); return 2; }
  const {approvers, selfApprovers} = parseApprovers(fs.readFileSync(path.join(ROOT, APPROVERS_FILE), 'utf8'));
  const pull = await api(token, `/repos/${repo}/pulls/${pr}`);
  const head = await api(token, `/repos/${repo}/commits/${pull.head.sha}`);
  const comments = [];
  for (let page = 1; ; page++) {
    const batch = await api(token, `/repos/${repo}/issues/${pr}/comments?per_page=100&page=${page}`);
    comments.push(...batch.map(c => ({login: c.user && c.user.login, body: c.body, updatedAt: c.updated_at})));
    if (batch.length < 100) break;
  }
  const result = evaluate({author: pull.user.login, base: pull.base.ref, approvers, selfApprovers, comments,
    lastCommitDate: head.commit.committer.date});
  await api(token, `/repos/${repo}/statuses/${pull.head.sha}`, {
    method: 'POST',
    body: JSON.stringify({state: result.ok ? 'success' : 'failure', context: CONTEXT,
      description: result.reason.slice(0, 140)}),
  });
  console.log(`${result.ok ? 'PR_APPROVAL_PASS' : 'PR_APPROVAL_FAIL'}: ${result.reason}`);
  return result.ok ? 0 : 1;
}

module.exports = {parseApprovers, isApprovalText, evaluate, APPROVAL_TEXT};
if (require.main === module) main().then(code => { process.exitCode = code; }, err => { console.error(err); process.exitCode = 2; });
