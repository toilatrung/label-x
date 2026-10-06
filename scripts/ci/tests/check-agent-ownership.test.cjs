'use strict';
const {test} = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const {parseIntegrators, perUserOwner, evaluate, parseNameStatus} = require('../check-agent-ownership.cjs');

const integrators = parseIntegrators('# comment\ntoilatrung\n@QcUser  # QC\n\n');
const run = (author, changes) => evaluate({author, integrators, changes});

test('integrator list ignores comments, @ and case', () => {
  assert.deepEqual([...integrators].sort(), ['qcuser', 'toilatrung']);
});

test('repository integrator file lists the PO', () => {
  const text = fs.readFileSync(path.resolve(__dirname, '../../../.github/agent-integrators.txt'), 'utf8');
  assert(parseIntegrators(text).has('toilatrung'));
});

test('per-user owner is parsed from the file name suffix', () => {
  assert.equal(perUserOwner('.agent/execution/current-context-@Dev1.md'), 'dev1');
  assert.equal(perUserOwner('.agent/execution/current-context-@dev1.html'), 'dev1');
  assert.equal(perUserOwner('.agent/governance/blockers/BLOCKER-031-@dev-2.md'), 'dev-2');
  assert.equal(perUserOwner('.agent/execution/current-context.md'), null);
});

test('developer may add, modify and delete own per-user files', () => {
  assert.deepEqual(run('dev1', [
    {status: 'A', path: '.agent/execution/current-context-@dev1.md'},
    {status: 'M', path: '.agent/execution/current-context-@dev1.html'},
    {status: 'D', path: '.agent/planning/epics-@dev1.md'},
    {status: 'A', path: 'src/backend/tests/test_x.py'},
  ]), []);
});

test('developer cannot touch canonical .agent files', () => {
  const v = run('dev1', [{status: 'M', path: '.agent/execution/current-context.md'}]);
  assert.equal(v.length, 1);
  assert.match(v[0], /current-context-@dev1\.md/);
});

test('name without @ is rejected and the hint gives the correct name', () => {
  for (const name of ['current-context-dev1.md', 'current-context_dev1.md', 'current-context-DEV1.md']) {
    const v = run('dev1', [{status: 'A', path: '.agent/execution/' + name}]);
    assert.equal(v.length, 1);
    assert.match(v[0], /hãy ghi vào \.agent\/execution\/current-context-@dev1\.md/);
  }
});

test('developer cannot touch another user per-user file', () => {
  assert.equal(run('dev1', [{status: 'M', path: '.agent/execution/task-board-@dev2.md'}]).length, 1);
});

test('rename is checked on both old and new paths', () => {
  assert.equal(run('dev1', [{status: 'R', oldPath: '.agent/execution/task-board.md', path: '.agent/execution/task-board-@dev1.md'}]).length, 1);
});

test('developer cannot change AGENT.md, the integrator list or the PR approver list', () => {
  assert.equal(run('dev1', [{status: 'M', path: 'AGENT.md'}, {status: 'M', path: '.github/agent-integrators.txt'}, {status: 'M', path: '.github/pr-approvers.txt'}]).length, 3);
});

test('PO and assigned QC may change canonical files', () => {
  assert.deepEqual(run('toilatrung', [{status: 'M', path: '.agent/execution/current-context.md'}, {status: 'M', path: 'AGENT.md'}]), []);
  assert.deepEqual(run('QCUSER', [{status: 'D', path: '.agent/execution/current-context-@dev1.md'}]), []);
});

test('missing author fails closed', () => {
  assert.equal(run('', []).length, 1);
});

test('git name-status output with renames is parsed', () => {
  assert.deepEqual(parseNameStatus('M\ta.md\nR100\told.md\tnew.md\n'), [
    {status: 'M', path: 'a.md'}, {status: 'R', oldPath: 'old.md', path: 'new.md'}]);
});
