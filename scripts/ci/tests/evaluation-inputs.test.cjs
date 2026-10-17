'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { sha256, verifyInputs, validateSplit } = require('../evaluation-inputs.cjs');

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'labelx-policy-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const write = (name, bytes) => { const file = path.join(root, name); fs.writeFileSync(file, bytes); return file; };
  fs.mkdirSync(path.join(root, '.agent/governance/decisions'), { recursive: true });
  // Synthetic approval is only inside this disposable unit-test root.
  const decision = '.agent/governance/decisions/unit-fixture.html';
  write(decision, '**Status**: `accepted`\n**Decision Type**: `testing`');
  const referenceFile = write('reference.bin', Buffer.from([0, 255, 1, 3]));
  const modelFile = write('model.bin', Buffer.from([3, 255, 2, 0]));
  const split = { schema_version: 1, group_key: 'video_id', train: ['tr'], guideline: ['g'], calibration: ['c'], held_out: ['h'], provenance: { source: 'synthetic', license: 'test', authorized_use: 'unit test' } };
  const splitFile = write('split.json', JSON.stringify(split));
  const policy = { status: 'approved', approved_decision: decision, reference_version: 'fixture-v1', score_version: 'fixture-score', reference_sha256: sha256(referenceFile), model_sha256: sha256(modelFile), split_sha256: sha256(splitFile), minimum_reference_errors: 1, minimum_errors_per_group: 1, minimum_recall_at_20: 0.9, minimum_effort_reduction: 0.2, residual_non_inferiority_margin: 0.01, false_positive_non_inferiority_margin: 0.01, model_provenance: { source: 'synthetic', license: 'test', authorized_use: 'unit test' } };
  const policyFile = write('policy.json', JSON.stringify(policy));
  return { root, policy, split, write, policyFile, referenceFile, modelFile, splitFile };
}
test('checks exact binary bytes and reports verification separately from evaluation', t => {
  const f = fixture(t), result = verifyInputs(f);
  assert.equal(result.status, 'inputs_verified');
  assert.equal(result.evaluation_status, 'NOT VERIFIED');
  assert.deepEqual(result.group_counts, { train: 1, guideline: 1, calibration: 1, held_out: 1 });
  assert.equal(result.policy_sha256, sha256(f.policyFile));
  assert.ok(!JSON.stringify(result).includes(f.root));
});
for (const [input, expected] of [['referenceFile', /Reference bytes/], ['modelFile', /Model bytes/], ['splitFile', /Split bytes/]]) {
  test('rejects tampered ' + input, t => {
    const f = fixture(t);
    fs.appendFileSync(f[input], 'tampered');
    assert.throws(() => verifyInputs(f), expected);
  });
}
test('does not approve draft policy or replace its thresholds', t => {
  const f = fixture(t);
  f.policy.status = 'draft';
  f.write('policy.json', JSON.stringify(f.policy));
  const before = fs.readFileSync(f.policyFile);
  assert.throws(() => verifyInputs(f), /Approved numeric/);
  assert.deepEqual(fs.readFileSync(f.policyFile), before);
});
test('requires provenance and a genuine accepted decision path', t => {
  const f = fixture(t);
  delete f.policy.model_provenance;
  f.write('policy.json', JSON.stringify(f.policy));
  assert.throws(() => verifyInputs(f), /Model provenance/);
  f.policy.model_provenance = { source: 's', license: 'l', authorized_use: 'a' };
  f.write('policy.json', JSON.stringify(f.policy));
  f.write(f.policy.approved_decision, '**Status**: `proposed`\n**Decision Type**: `testing`');
  assert.throws(() => verifyInputs(f), /accepted governance/);
});
test('rejects contamination by any held-out video and calibration leakage', t => {
  const f = fixture(t);
  for (const name of ['train', 'guideline', 'calibration']) {
    assert.throws(() => validateSplit({ ...f.split, [name]: ['h'] }), /Held-out video leakage/);
  }
  assert.throws(() => validateSplit({ ...f.split, calibration: ['tr'] }), /Calibration video leakage/);
  assert.throws(() => validateSplit({ ...f.split, held_out: ['h', 'h'] }), /duplicate/);
  assert.throws(() => validateSplit({ ...f.split, held_out: [] }), /nonempty/);
  assert.throws(() => validateSplit({ ...f.split, group_key: 'frame_id' }), /video_id/);
});
