'use strict';
const {test} = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const {parseApprovers, isApprovalText, evaluate} = require('../check-pr-approval.cjs');

const {approvers, selfApprovers} = parseApprovers('# comment\ntoilatrung self-approve\n@HaQc  # QC\n\n');
const T0 = '2026-10-07T08:00:00Z', BEFORE = '2026-10-07T07:00:00Z', AFTER = '2026-10-07T09:00:00Z';
const run = (author, comments, lastCommitDate = T0) =>
  evaluate({author, approvers, selfApprovers, comments, lastCommitDate});
const ok = (login, updatedAt = AFTER, body = 'Đã xem và duyệt') => ({login, body, updatedAt});

test('approver list ignores comments, @ and case; only flagged users self-approve', () => {
  assert.deepEqual([...approvers].sort(), ['haqc', 'toilatrung']);
  assert.deepEqual([...selfApprovers], ['toilatrung']);
});

test('repository approver file lets the PO self-approve', () => {
  const text = fs.readFileSync(path.resolve(__dirname, '../../../.github/pr-approvers.txt'), 'utf8');
  assert(parseApprovers(text).selfApprovers.has('toilatrung'));
});

test('PO pull request passes without any comment', () => {
  assert.equal(run('toilatrung', []).ok, true);
});

test('member pull request needs an approver comment', () => {
  assert.equal(run('dev1', []).ok, false);
  assert.equal(run('dev1', [ok('toilatrung')]).ok, true);
  assert.equal(run('dev1', [ok('HaQc')]).ok, true);
});

test('approval text tolerates spacing and case but not other wording', () => {
  assert.equal(isApprovalText('  đã xem  và DUYỆT \n'), true);
  assert.equal(isApprovalText('Đã xem và duyệt'.normalize('NFD')), true);
  assert.equal(isApprovalText('LGTM'), false);
  assert.equal(isApprovalText('Đã xem và duyệt, nhưng sửa lại test'), false);
});

test('comments by non-approvers or by the author do not count', () => {
  assert.equal(run('dev1', [ok('dev2')]).ok, false);
  assert.equal(run('haqc', [ok('haqc')]).ok, false);
  assert.equal(run('haqc', [ok('toilatrung')]).ok, true);
});

test('approval written before the last commit is stale', () => {
  const r = run('dev1', [ok('toilatrung', BEFORE)]);
  assert.equal(r.ok, false);
  assert.match(r.reason, /commit mới/);
});
