'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { proposed, verify } = require('../production-images-ruleset.cjs');

function baseline() {
  return { id: 25297568, source: 'toilatrung/label-x', name: 'main-develop-protection',
    target: 'branch', enforcement: 'active',
    conditions: { ref_name: { exclude: [], include: ['refs/heads/main', 'refs/heads/develop'] } },
    bypass_actors: [], rules: [
      { type: 'deletion' }, { type: 'non_fast_forward' },
      { type: 'pull_request', parameters: { required_approving_review_count: 0,
        required_review_thread_resolution: true, allowed_merge_methods: ['merge'] } },
      { type: 'required_status_checks', parameters: { strict_required_status_checks_policy: true,
        do_not_enforce_on_create: false, required_status_checks:
          ['framework', 'backend', 'frontend', 'detector', 'bootstrap-windows'].map(context => ({ context, integration_id: 15368 })) } },
    ] };
}

test('adds one CI check without mutating baseline or other policy', () => {
  const before = baseline(), copy = structuredClone(before), change = proposed(before);
  verify(before, { ...before, ...change });
  assert.deepEqual(before, copy);
  assert.equal(change.rules[3].parameters.required_status_checks.length, 6);
  assert.deepEqual(change.rules.slice(0, 3), before.rules.slice(0, 3));
});

test('rejects stale context lists, wrong integration, inactive enforcement and wrong target', () => {
  for (const mutate of [
    s => { s.id++; }, s => { s.source = 'fork/label-x'; },
    s => { s.enforcement = 'disabled'; }, s => { s.target = 'tag'; },
    s => { s.conditions.ref_name.exclude.push('refs/heads/main'); },
    s => { s.rules[3].parameters.strict_required_status_checks_policy = false; },
    s => { s.rules[3].parameters.required_status_checks.pop(); },
    s => { s.rules[3].parameters.required_status_checks[0].integration_id = 1; },
    s => { s.rules.push(s.rules[3]); },
  ]) {
    const snapshot = baseline(); mutate(snapshot);
    assert.throws(() => proposed(snapshot));
  }
});

test('readback rejects missing check, wrong app, review loss, bypass addition and enforcement drift', () => {
  const before = baseline();
  for (const mutate of [
    s => { s.rules[3].parameters.required_status_checks.pop(); },
    s => { s.rules[3].parameters.required_status_checks[5].integration_id = 1; },
    s => { s.rules[2].parameters.required_review_thread_resolution = false; },
    s => { s.rules[3].parameters.strict_required_status_checks_policy = false; },
    s => { s.bypass_actors.push({ actor_id: 1, actor_type: 'User', bypass_mode: 'always' }); },
    s => { s.enforcement = 'disabled'; },
  ]) {
    const after = { ...before, ...proposed(before) }; mutate(after);
    assert.throws(() => verify(before, after));
  }
});
