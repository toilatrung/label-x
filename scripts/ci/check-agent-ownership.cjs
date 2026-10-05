'use strict';
// Kiểm quy tắc AGENT.md "Per-User Agent Files" (CR-100) trên pull request:
// người không thuộc .github/agent-integrators.txt chỉ được thêm/sửa/đổi tên/xoá file .agent/ của chính mình
// (<tên>-@<username>.<đuôi>) và không được sửa AGENT.md hay danh sách integrator.
// CLI (CI): PR_AUTHOR=<login> BASE_SHA=<sha> HEAD_SHA=<sha> node scripts/ci/check-agent-ownership.cjs
const fs = require('node:fs'), path = require('node:path'), {spawnSync} = require('node:child_process');

const ROOT = path.resolve(__dirname, '../..');
const INTEGRATORS_FILE = '.github/agent-integrators.txt';
const PROTECTED = new Set(['AGENT.md', INTEGRATORS_FILE]);

function parseIntegrators(text) {
  return new Set(text.split(/\r?\n/).map(l => l.replace(/#.*/, '').trim().replace(/^@/, '').toLowerCase()).filter(Boolean));
}

// Chủ sở hữu file riêng: phần sau "-@" cuối cùng của tên (bỏ đuôi); null nếu là file chính.
function perUserOwner(filePath) {
  const base = path.posix.basename(filePath);
  const m = base.match(/-@([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(\.[A-Za-z0-9]+)?$/);
  return m ? m[1].toLowerCase() : null;
}

// changes: [{status: 'A'|'M'|'D'|'R'|'C'|..., path, oldPath?}]
function evaluate({author, integrators, changes}) {
  const login = String(author || '').replace(/^@/, '').toLowerCase();
  if (!login) return ['Không xác định được tác giả pull request (PR_AUTHOR).'];
  if (integrators.has(login)) return [];
  const violations = [];
  for (const c of changes) {
    for (const p of [c.path, c.oldPath].filter(Boolean)) {
      if (PROTECTED.has(p)) {
        violations.push(`${p}: chỉ integrator được sửa (AGENT.md, CR-100).`);
      } else if (p === '.agent' || p.startsWith('.agent/')) {
        const owner = perUserOwner(p);
        if (owner === null) violations.push(`${p}: file chính trong .agent/ — hãy ghi vào ${suggest(p, login)} (chỉ integrator gộp vào file chính).`);
        else if (owner !== login) violations.push(`${p}: file riêng của @${owner}, @${login} không được sửa.`);
      }
    }
  }
  return [...new Set(violations)];
}

function suggest(p, login) {
  const ext = path.posix.extname(p);
  let stem = p.slice(0, p.length - ext.length);
  // Thiếu "@" (vd current-context-dev1, current-context_dev1): gợi ý đúng current-context-@dev1.
  const loose = new RegExp('[-_.]' + login.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$', 'i');
  stem = stem.replace(loose, '');
  return stem + '-@' + login + ext;
}

function parseNameStatus(out) {
  return out.split('\n').filter(Boolean).map(line => {
    const [status, a, b] = line.split('\t');
    return b ? {status: status[0], oldPath: a, path: b} : {status: status[0], path: a};
  });
}

function main(env = process.env) {
  const {PR_AUTHOR, BASE_SHA, HEAD_SHA} = env;
  if (!BASE_SHA || !HEAD_SHA) { console.error('Cần BASE_SHA và HEAD_SHA.'); return 2; }
  const integrators = parseIntegrators(fs.readFileSync(path.join(ROOT, INTEGRATORS_FILE), 'utf8'));
  const r = spawnSync('git', ['diff', '--name-status', '--find-renames', `${BASE_SHA}...${HEAD_SHA}`],
    {cwd: ROOT, encoding: 'utf8', shell: false});
  if (r.status !== 0) { console.error(r.stderr || 'git diff thất bại'); return 2; }
  const violations = evaluate({author: PR_AUTHOR, integrators, changes: parseNameStatus(r.stdout)});
  if (violations.length) {
    console.error(`AGENT_OWNERSHIP_FAIL cho @${PR_AUTHOR}:\n  ` + violations.join('\n  '));
    return 1;
  }
  console.log('AGENT_OWNERSHIP_PASS');
  return 0;
}

module.exports = {parseIntegrators, perUserOwner, evaluate, parseNameStatus, suggest};
if (require.main === module) process.exitCode = main();
