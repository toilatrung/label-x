'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { validateReceipt, render, digestOnly, FILES } = require('../gitops-update.cjs');
const sha = 'a'.repeat(40);
const current = { namespace: 'labelx', resources: ['applications.yaml', 'storage.yaml'],
  generatorOptions: { disableNameSuffixHash: true }, images: [],
  configMapGenerator: [{ name: 'labelx-ops', files: ['ops/smoke.py'] },
    { name: 'labelx-release', literals: ['SOURCE_SHA=' + sha] }] };
const receipt = { source_sha: sha, ci_run_id: '123', publish_run_id: '456', deployment_policy: 'CR-120',
  mvp_acceptance: 'unverified', images: Object.fromEntries(['backend', 'frontend'].map(component => {
    const repository = `ghcr.io/toilatrung/labelx-${component}`, digest = 'sha256:' + component[0].repeat(64);
    return [component, { repository, digest, tag: `sha-${sha}`, reference: `${repository}@${digest}` }];
  })) };

test('receipt requires exact SHA, both trusted repositories and digests; never MVP passed', () => {
  assert.equal(validateReceipt(receipt), receipt);
  for (const patch of [{ source_sha: 'main' }, { mvp_acceptance: 'passed' },
    { deployment_policy: 'other' }, { ci_run_id: '' }, { images: {} }]) {
    assert.throws(() => validateReceipt({ ...receipt, ...patch }));
  }
  for (const patch of [{ digest: 'latest' }, { tag: 'latest' }, { reference: 'other@sha256:' + 'a'.repeat(64) },
    { repository: 'ghcr.io/attacker/backend' }]) {
    assert.throws(() => validateReceipt({ ...receipt, images: { ...receipt.images, backend: { ...receipt.images.backend, ...patch } } }));
  }
});

test('automatic update is restricted to two image digests, source identity and receipt', () => {
  const updated = render(current, receipt);
  assert(digestOnly(current, updated, receipt, FILES));
  assert(!digestOnly(current, updated, receipt, [...FILES, 'src/backend/config/settings.py']));
  assert(!digestOnly(current, updated, receipt, []));
  for (const mutate of [value => { value.namespace = 'other'; },
    value => { value.resources.push('unreviewed.yaml'); },
    value => { value.configMapGenerator[0].files.push('/etc/passwd'); },
    value => { value.images[0].newTag = 'latest'; },
    value => { value.generatorOptions.disableNameSuffixHash = false; }]) {
    const tampered = structuredClone(updated); mutate(tampered);
    assert(!digestOnly(current, tampered, receipt, FILES));
  }
});

test('rollback renders an earlier verified pair without reverting infrastructure or generating mutable tags', () => {
  const next = render(current, receipt);
  const rollback = { ...receipt, source_sha: 'b'.repeat(40), images: structuredClone(receipt.images) };
  for (const entry of Object.values(rollback.images)) entry.tag = `sha-${rollback.source_sha}`;
  const result = render(next, rollback);
  assert.deepEqual(result.resources, current.resources);
  assert(digestOnly(next, result, rollback, FILES));
  assert(result.images.every(entry => entry.digest && !entry.newTag));
});
